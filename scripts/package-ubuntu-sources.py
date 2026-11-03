#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create independent, root-owned Ubuntu source tar archives from verified files."""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import tarfile


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024*1024), b""):
            h.update(b)
    return h.hexdigest()


class HashingReader:
    def __init__(self, file):
        self.file = file
        self.sha = hashlib.sha256()
        self.count = 0
    def read(self, size=-1):
        chunk = self.file.read(size)
        self.sha.update(chunk)
        self.count += len(chunk)
        return chunk


def write_tsv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", type=Path, default=Path(__file__).resolve().parent.parent/"cache/ubuntu-sources")
    ap.add_argument("--binary-source-tsv", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--group-source-limit", type=int, default=1400*1024*1024)
    args = ap.parse_args()
    work = args.work_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = work/"ubuntu-source-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    verification_path = work/"ubuntu-source-download-verification.json"
    verification = json.loads(verification_path.read_text())
    if manifest["missing"]:
        raise ValueError("Cannot package an incomplete source plan")
    if verification["manifest_sha256"] != digest(manifest_path):
        raise ValueError("Download verification does not match this manifest")
    if digest(args.binary_source_tsv) != manifest["input_tsv_sha256"]:
        raise ValueError("Binary/source input differs from the verified manifest")
    if verification["file_count"] != manifest["archive_file_count"] or verification["source_package_count"] != manifest["matched_source_package_count"]:
        raise ValueError("Incomplete verification report")
    by_path = {f["repository_path"]:f for f in manifest["archive_files"]}
    verified_paths = {f["repository_path"] for f in verification["files"]}
    if verified_paths != set(by_path):
        raise ValueError("Verified archive set mismatch")
    packages = sorted(manifest["packages"], key=lambda x:(x["package"],x["version"]))
    groups = []
    current, paths, size = [], set(), 0
    for package in packages:
        package_paths = {f["repository_path"] for f in package["files"]}
        extra = sum(by_path[p]["size"] for p in package_paths-paths)
        if sum(by_path[p]["size"] for p in package_paths) > args.group_source_limit:
            raise ValueError(f"One source package exceeds grouping limit: {package['package']}")
        if current and size+extra > args.group_source_limit:
            groups.append((current, paths))
            current, paths, size = [], set(), 0
            extra = sum(by_path[p]["size"] for p in package_paths)
        current.append(package)
        paths.update(package_paths)
        size += extra
    if current:
        groups.append((current, paths))
    proof_paths = set()
    for release in manifest["authenticated_releases"]:
        proof_paths.update([release["inrelease_path"],release["release_path"]])
        proof_paths.add(str(Path(release["inrelease_path"]).with_suffix(".gpgv.log")))
    for index in manifest["authenticated_source_indexes"]:
        proof_paths.add(index["path"])
    mtime = int(dt.datetime.fromisoformat(manifest["generated_at_utc"]).timestamp())
    archive_reports = []
    group_dir = work/"archive-groups"
    group_dir.mkdir(exist_ok=True)
    for n, (selected, selected_paths) in enumerate(groups, 1):
        stem = f"ubuntu22.04-jammy-corresponding-sources-{n:02d}-of-{len(groups):02d}"
        local = group_dir/stem
        local.mkdir(exist_ok=True)
        selected_files = [by_path[p] for p in sorted(selected_paths)]
        source_keys = {(p["package"],p["version"]) for p in selected}
        part_manifest = {"schema_version":1,"archive_part":n,"archive_part_count":len(groups),"complete_manifest_sha256":digest(manifest_path),"binary_source_tsv_sha256":manifest["input_tsv_sha256"],"source_package_count":len(selected),"source_archive_file_count":len(selected_files),"source_archive_bytes":sum(f["size"] for f in selected_files),"authenticated_releases":manifest["authenticated_releases"],"authenticated_source_indexes":manifest["authenticated_source_indexes"],"packages":selected,"archive_files":selected_files}
        (local/"source-manifest.json").write_text(json.dumps(part_manifest,indent=2,ensure_ascii=False)+"\n")
        part_verification = {"verified_at_utc":verification["verified_at_utc"],"source_package_count":len(selected),"source_archive_file_count":len(selected_files),"source_packages":[p for p in verification["source_packages"] if (p["package"],p["version"]) in source_keys],"files":[f for f in verification["files"] if f["repository_path"] in selected_paths]}
        (local/"source-download-verification.json").write_text(json.dumps(part_verification,indent=2)+"\n")
        write_tsv(local/"source-packages.tsv",["source_package","source_version","binary_packages"],((p["package"],p["version"],",".join(b["package"] for b in p["binary_packages"])) for p in selected))
        write_tsv(local/"source-files.tsv",["repository_path","size_bytes","sha256"],((f["repository_path"],f["size"],f["sha256"]) for f in selected_files))
        shutil.copyfile(args.binary_source_tsv,local/"image-binary-to-source.tsv")
        (local/"README.txt").write_text(f"""Ubuntu 22.04 Jammy corresponding source archives, part {n} of {len(groups)}

This part is an independently extractable tar archive. It contains all source
files for {len(selected)} exact source package versions ({len(selected_files)} files).
A source package is never split between parts. Files shared across source
packages are repeated in another part when necessary for completeness.

The full set corresponds to {manifest['binary_package_count']} installed binary
packages from the Firefly-RK3288 Ubuntu 22.04 GNOME image. Together, all parts
contain {manifest['matched_source_package_count']} source packages at the exact
versions in image-binary-to-source.tsv. Custom Linux and U-Boot sources are
provided separately in the project's release source/build materials.

Source paths: archives/pool/...
Package and file inventory: source-manifest.json, source-packages.tsv,
source-files.tsv. Original Ubuntu .dsc, orig and packaging archives are kept
unchanged. Upstream licenses and Ubuntu/Debian packaging copyright files are
contained in those original archives.

Integrity verification after extraction, from this directory:
    sha256sum -c SHA256SUMS

Ubuntu authenticity evidence is under metadata/. The InRelease signatures
were verified with Ubuntu's archive keyring. Signing fingerprint:
    F6ECB3762474EDA9D21B7022871920D1991BC93C
The SHA256 of each compressed Sources index is authenticated by its signed
Release; each source archive SHA256 and size comes from that Sources index.
Each .dsc's archive references were also checked for matching files/checksums.
The .Release and .gpgv.log files record the verified cleartext and result.

Original download URLs and checksums are in source-manifest.json. The full
manifest SHA256 is {part_manifest['complete_manifest_sha256']}.
This archive uses numeric owner/group 0 and relative member paths.
""")
        inputs = {}
        for name in ["README.txt","source-manifest.json","source-download-verification.json","source-packages.tsv","source-files.tsv","image-binary-to-source.tsv"]:
            inputs[name] = (local/name, (local/name).stat().st_size, digest(local/name))
        for relative in sorted(proof_paths):
            path = work/relative
            inputs[relative] = (path,path.stat().st_size,digest(path))
        for file in selected_files:
            inputs[file["archive_path"]] = (work/file["archive_path"],file["size"],file["sha256"])
        (local/"SHA256SUMS").write_text("".join(f"{value[2]}  {name}\n" for name,value in sorted(inputs.items())))
        inputs["SHA256SUMS"] = (local/"SHA256SUMS",(local/"SHA256SUMS").stat().st_size,digest(local/"SHA256SUMS"))
        destination = output/(stem+".tar")
        partial = destination.with_suffix(".tar.part")
        member_count = 0
        with tarfile.open(partial,"w",format=tarfile.PAX_FORMAT) as archive:
            directories = {stem}
            for name in inputs:
                parent = Path(stem)/name
                directories.update(str(p) for p in parent.parents if str(p) != ".")
            for name in sorted(directories):
                info = tarfile.TarInfo(name+"/")
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                info.mtime = mtime
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                archive.addfile(info)
                member_count += 1
            for relative,(path,size,expected) in sorted(inputs.items()):
                info = tarfile.TarInfo(stem+"/"+relative)
                info.size = size
                info.mode = 0o644
                info.mtime = mtime
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                with path.open("rb") as f:
                    reader = HashingReader(f)
                    archive.addfile(info,reader)
                if reader.count != size or reader.sha.hexdigest() != expected:
                    raise ValueError(f"File changed or checksum mismatched during packaging: {relative}")
                member_count += 1
        if partial.stat().st_size >= int(1.5*1024**3):
            raise ValueError(f"Archive exceeds 1.5 GiB: {partial.name}")
        os.replace(partial,destination)
        report = {"file":destination.name,"bytes":destination.stat().st_size,"sha256":digest(destination),"source_package_count":len(selected),"source_archive_file_count":len(selected_files),"source_archive_bytes":sum(f["size"] for f in selected_files),"tar_member_count":member_count,"first_package":selected[0]["package"],"last_package":selected[-1]["package"],"independently_extractable":True,"numeric_uid":0,"numeric_gid":0,"source_bytes_reverified_while_packaging":True}
        with tarfile.open(destination,"r:") as check:
            actual_members = 0
            for member in check:
                if member.uid or member.gid or member.name.startswith("/") or ".." in Path(member.name).parts or member.issym() or member.islnk():
                    raise ValueError("Unexpected tar ownership/path/type")
                actual_members += 1
            if actual_members != member_count:
                raise ValueError("Tar member count mismatch")
        archive_reports.append(report)
        print(json.dumps(report),flush=True)
    total_packages = sum(r["source_package_count"] for r in archive_reports)
    if total_packages != manifest["matched_source_package_count"]:
        raise ValueError("Package grouping coverage mismatch")
    summary = {"schema_version":1,"packaged_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"binary_package_count":manifest["binary_package_count"],"source_package_count":total_packages,"unique_source_archive_file_count":manifest["archive_file_count"],"unique_source_archive_bytes":manifest["total_archive_bytes"],"missing_source_package_count":0,"full_manifest_sha256":digest(manifest_path),"download_verification_sha256":digest(verification_path),"archives":archive_reports}
    (output/"ubuntu-source-archive-report.json").write_text(json.dumps(summary,indent=2)+"\n")
    exported = ["ubuntu-source-manifest.json","ubuntu-source-packages.tsv","ubuntu-source-files.tsv","ubuntu-source-missing.tsv","ubuntu-source-download-verification.json"]
    for name in exported:
        shutil.copyfile(work/name,output/name)
    all_files = [output/r["file"] for r in archive_reports] + [output/n for n in exported] + [output/"ubuntu-source-archive-report.json"]
    (output/"UBUNTU-SOURCE-SHA256SUMS").write_text("".join(f"{digest(p)}  {p.name}\n" for p in sorted(all_files)))
    print(f"Complete: {total_packages} source packages in {len(archive_reports)} independent archives",flush=True)


if __name__ == "__main__":
    main()
