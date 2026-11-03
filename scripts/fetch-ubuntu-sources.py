#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Plan/download exact Ubuntu source archives using authenticated Sources indexes.

Only Python's standard library and gpgv are required. All generated files stay
under --output-dir (cache/ubuntu-sources in this checkout by default).
"""
from __future__ import annotations
import argparse
import concurrent.futures
import csv
import datetime as dt
import email.utils
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_MIRRORS = ["https://mirrors.ustc.edu.cn/ubuntu-ports", "https://ports.ubuntu.com/ubuntu-ports"]
POCKETS = ["jammy", "jammy-updates", "jammy-security", "jammy-backports"]
COMPONENTS = ["main", "restricted", "universe", "multiverse"]
HEX256 = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_base(value: str) -> str:
    u = urllib.parse.urlsplit(value)
    if u.scheme != "https" or not u.netloc or u.username or u.password or u.query or u.fragment:
        raise ValueError("Mirror URLs must use HTTPS and contain no credentials/query/fragment")
    return value.rstrip("/")


def relative_path(value: str) -> str:
    p = PurePosixPath(value)
    if not value or p.is_absolute() or ".." in p.parts or "\\" in value or urllib.parse.urlsplit(value).scheme:
        raise ValueError(f"Unsafe repository path: {value!r}")
    return str(p)


def url_join(base: str, relative: str) -> str:
    return base + "/" + urllib.parse.quote(relative_path(relative), safe="/+-._~")


def paragraphs(lines):
    fields = {}
    current = None
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line:
            if fields:
                yield fields
                fields = {}
                current = None
        elif line[0].isspace():
            if current is None:
                raise ValueError("Deb822 continuation without a field")
            fields[current] += "\n" + line[1:]
        else:
            if ":" not in line:
                raise ValueError("Invalid Deb822 field")
            current, value = line.split(":", 1)
            fields[current] = value.lstrip()
    if fields:
        yield fields


def checksums(field: str) -> dict:
    entries = {}
    for line in field.splitlines():
        if not line.strip():
            continue
        digest, size, path = line.split()
        if not HEX256.fullmatch(digest):
            raise ValueError("Invalid SHA256 entry")
        path = relative_path(path)
        if path in entries:
            raise ValueError(f"Duplicate checksum path: {path}")
        n = int(size)
        if n < 0:
            raise ValueError("Negative file size")
        entries[path] = {"sha256": digest, "size": n}
    return entries


class Downloader:
    def __init__(self, proxy: str | None, timeout: float = 90):
        handlers = [] if proxy is None else [urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {})]
        self.opener = urllib.request.build_opener(*handlers)
        self.timeout = timeout

    def fetch(self, urls: list[str], dest: Path, expected: dict | None = None, max_bytes=8*1024*1024):
        dest.parent.mkdir(parents=True, exist_ok=True)
        if expected and dest.exists() and dest.stat().st_size == expected["size"] and sha256(dest) == expected["sha256"]:
            return {"url": urls[0], "cached": True, "sha256": expected["sha256"], "size": expected["size"]}
        partial = dest.with_name(dest.name + ".part")
        errors = []
        for url in urls:
            for attempt in range(3):
                try:
                    offset = partial.stat().st_size if partial.exists() and expected else 0
                    if expected and offset >= expected["size"]:
                        if offset == expected["size"] and sha256(partial) == expected["sha256"]:
                            os.replace(partial, dest)
                            return {"url": url, "cached": True, **expected}
                        partial.unlink()
                        offset = 0
                    headers = {"User-Agent": "Firefly-Ubuntu-Source-Archive/1.0"}
                    if offset:
                        headers["Range"] = f"bytes={offset}-"
                    with self.opener.open(urllib.request.Request(url, headers=headers), timeout=self.timeout) as response:
                        final = urllib.parse.urlsplit(response.geturl())
                        if final.scheme != "https" or final.username or final.password:
                            raise ValueError("Unexpected insecure or credentialed redirect")
                        append = offset > 0 and response.status == 206
                        if append:
                            cr = response.headers.get("Content-Range", "")
                            if not cr.startswith(f"bytes {offset}-"):
                                raise ValueError("Invalid resume Content-Range")
                        else:
                            offset = 0
                        count = offset
                        with partial.open("ab" if append else "wb") as out:
                            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                                count += len(chunk)
                                if count > (expected["size"] if expected else max_bytes):
                                    raise ValueError("Response exceeds authenticated/allowed size")
                                out.write(chunk)
                    actual = {"size": partial.stat().st_size, "sha256": sha256(partial)}
                    if expected and actual != expected:
                        if actual["size"] >= expected["size"]:
                            partial.unlink(missing_ok=True)
                        raise ValueError(f"Size/SHA256 mismatch for {url}")
                    os.replace(partial, dest)
                    return {"url": url, "cached": False, **actual}
                except Exception as exc:
                    errors.append(f"{url}: {type(exc).__name__}: {exc}")
                    if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 404, 410):
                        break
                    if attempt < 2:
                        time.sleep(min(2 ** attempt, 4))
        raise RuntimeError("All download attempts failed:\n" + "\n".join(errors[-8:]))


def read_requirements(path: Path):
    needed = {}
    rows = 0
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            if not row:
                continue
            if len(row) != 4:
                raise ValueError(f"Expected 4 TSV columns, got {len(row)} at row {rows+1}")
            binary, binary_version, source, source_version = row
            if binary.lower() in ("binary", "binary_package", "package") and source.lower() in ("source", "source_package"):
                continue
            if not all(row):
                raise ValueError(f"Empty source metadata at row {rows+1}")
            needed.setdefault((source, source_version), []).append({"package": binary, "version": binary_version})
            rows += 1
    return rows, needed


def verify_release(downloader, pocket, mirrors, output, keyring, allow_expired):
    temp_dir = output / "temporary"
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=pocket+"-", dir=temp_dir) as td:
        td = Path(td)
        fetched = downloader.fetch([url_join(m, f"dists/{pocket}/InRelease") for m in mirrors], td/"InRelease")
        release = td / "Release"
        command = ["gpgv", "--keyring", str(keyring), "--status-fd", "1", "--output", str(release), str(td/"InRelease")]
        result = subprocess.run(command, capture_output=True, text=True)
        valid = [line.split()[2] for line in result.stdout.splitlines() if line.startswith("[GNUPG:] VALIDSIG ")]
        if result.returncode or not valid:
            raise RuntimeError(f"{pocket}: InRelease signature verification failed\n{result.stderr}")
        fields = next(paragraphs(release.read_text(encoding="utf-8").splitlines()))
        if fields.get("Origin") != "Ubuntu" or fields.get("Codename") != "jammy" or fields.get("Suite") != pocket:
            raise ValueError(f"Unexpected signed Release identity: {pocket}")
        now = dt.datetime.now(dt.timezone.utc)
        released = email.utils.parsedate_to_datetime(fields["Date"])
        if released > now + dt.timedelta(days=1):
            raise ValueError(f"{pocket}: Release Date is in the future")
        valid_until = fields.get("Valid-Until")
        expired = bool(valid_until and email.utils.parsedate_to_datetime(valid_until) < now)
        if expired and not allow_expired:
            raise ValueError(f"{pocket}: signed Release expired at {valid_until}; use --allow-expired only for an intentional historical archive")
        digest = fetched["sha256"]
        meta = output / "metadata" / pocket
        meta.mkdir(parents=True, exist_ok=True)
        inrelease_dest = meta / f"{digest}.InRelease"
        release_dest = meta / f"{digest}.Release"
        shutil.copyfile(td/"InRelease", inrelease_dest)
        shutil.copyfile(release, release_dest)
        (meta/f"{digest}.gpgv.log").write_text(result.stdout + result.stderr)
        proof = {"pocket": pocket, "url": fetched["url"], "inrelease_sha256": digest, "release_sha256": sha256(release_dest), "signer_fingerprints": valid, "date": fields["Date"], "valid_until": valid_until, "expired": expired, "inrelease_path": str(inrelease_dest.relative_to(output)), "release_path": str(release_dest.relative_to(output))}
        return fields, checksums(fields["SHA256"]), proof


def source_index(downloader, pocket, component, release_checksums, mirrors, output):
    prefix = f"{component}/source/"
    candidate = next((prefix+"Sources"+suffix for suffix in (".xz", ".gz", "") if prefix+"Sources"+suffix in release_checksums), None)
    if candidate is None:
        raise ValueError(f"No signed Sources index for {pocket}/{component}")
    expected = release_checksums[candidate]
    suffix = ".xz" if candidate.endswith(".xz") else ".gz" if candidate.endswith(".gz") else ""
    dest = output / "metadata" / pocket / f"{component}-{expected['sha256']}.Sources{suffix}"
    by_hash = f"dists/{pocket}/{component}/source/by-hash/SHA256/{expected['sha256']}"
    urls = [url_join(m, by_hash) for m in mirrors] + [url_join(m, "dists/"+pocket+"/"+candidate) for m in mirrors]
    fetched = downloader.fetch(urls, dest, expected)
    proof = {"pocket": pocket, "component": component, "release_entry": candidate, "url": fetched["url"], "sha256": expected["sha256"], "size": expected["size"], "path": str(dest.relative_to(output))}
    return dest, proof


def parse_index(path, proof, requested, mirrors):
    opener = lzma.open if str(path).endswith(".xz") else gzip.open if str(path).endswith(".gz") else open
    matches = {}
    available = {}
    names = {name for name, version in requested}
    with opener(path, "rt", encoding="utf-8", errors="strict") as f:
        for fields in paragraphs(f):
            name, version = fields.get("Package"), fields.get("Version")
            if name not in names:
                continue
            available.setdefault(name, set()).add(version)
            if (name, version) not in requested:
                continue
            directory = relative_path(fields["Directory"])
            if not directory.startswith("pool/"):
                raise ValueError(f"Unexpected source Directory: {directory}")
            files = []
            for filename, values in checksums(fields["Checksums-Sha256"]).items():
                if "/" in filename:
                    raise ValueError("Source filename must be a basename")
                remote_path = directory + "/" + filename
                files.append({"filename": filename, "repository_path": remote_path, "archive_path": "archives/"+remote_path, "urls": [url_join(m, remote_path) for m in mirrors], **values})
            if not any(x["filename"].endswith(".dsc") for x in files):
                raise ValueError(f"{name} {version}: signed Sources entry has no .dsc")
            files.sort(key=lambda x: x["filename"])
            matches[(name, version)] = {"package": name, "version": version, "directory": directory, "files": files, "source_indexes": [proof]}
    return matches, available


def verify_dsc(package, output):
    dscs = [x for x in package["files"] if x["filename"].endswith(".dsc")]
    if len(dscs) != 1:
        raise ValueError(f"{package['package']}: expected exactly one .dsc")
    lines = (output/dscs[0]["archive_path"]).read_text(encoding="utf-8").splitlines()
    if lines and lines[0] == "-----BEGIN PGP SIGNED MESSAGE-----":
        start = lines.index("") + 1
        end = lines.index("-----BEGIN PGP SIGNATURE-----")
        lines = [line[2:] if line.startswith("- ") else line for line in lines[start:end]]
    fields = next(paragraphs(lines))
    if fields.get("Source") != package["package"] or fields.get("Version") != package["version"]:
        raise ValueError(f".dsc source/version mismatch for {package['package']}")
    indexed = {f["filename"]:{"size":f["size"],"sha256":f["sha256"]} for f in package["files"]}
    referenced = checksums(fields["Checksums-Sha256"])
    if not referenced:
        raise ValueError(f"Empty .dsc archive list for {package['package']}")
    for filename, expected in referenced.items():
        if indexed.get(filename) != expected:
            raise ValueError(f".dsc references an absent or different archive: {package['package']} {filename}")
    return {"package":package["package"], "version":package["version"], "dsc":dscs[0]["archive_path"], "referenced_archive_count":len(referenced), "complete":True}


def write_tsv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("packages_tsv", type=Path, help="binary/version/source/sourceversion TSV")
    ap.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent.parent/"cache/ubuntu-sources")
    ap.add_argument("--mirror", action="append", help="HTTPS Ubuntu mirror root; repeat for fallbacks")
    proxy_args = ap.add_mutually_exclusive_group()
    proxy_args.add_argument("--proxy", help="Optional HTTP(S) proxy URL")
    proxy_args.add_argument("--no-proxy", action="store_true", help="Connect directly, ignoring environment proxy settings")
    ap.add_argument("--keyring", type=Path, default=Path("/usr/share/keyrings/ubuntu-archive-keyring.gpg"))
    ap.add_argument("--pocket", action="append", choices=POCKETS)
    ap.add_argument("--component", action="append", choices=COMPONENTS)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--plan-only", action="store_true", help="Authenticate indexes and write manifests; do not fetch source archives")
    ap.add_argument("--allow-expired", action="store_true", help="Permit expired, correctly signed historical Release metadata; recorded in manifest")
    args = ap.parse_args(argv)
    if args.jobs < 1 or args.jobs > 16:
        ap.error("--jobs must be between 1 and 16")
    if not args.keyring.is_file() or not shutil.which("gpgv"):
        ap.error("gpgv and the supplied Ubuntu archive keyring are required")
    mirrors = [clean_base(x) for x in (args.mirror or DEFAULT_MIRRORS)]
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    downloader = Downloader("" if args.no_proxy else args.proxy)
    binary_count, requested = read_requirements(args.packages_tsv)
    print(f"Input: {binary_count} binary packages; {len(requested)} exact source package/version pairs", flush=True)
    releases, all_indexes = [], []
    matches, available = {}, {}
    jobs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        release_jobs = {executor.submit(verify_release, downloader, pocket, mirrors, output, args.keyring.resolve(), args.allow_expired): pocket for pocket in (args.pocket or POCKETS)}
        for future in concurrent.futures.as_completed(release_jobs):
            fields, hashes, proof = future.result()
            releases.append(proof)
            pocket = proof["pocket"]
            print(f"Verified signature: {pocket}; {proof['signer_fingerprints'][0]}", flush=True)
            for component in (args.component or COMPONENTS):
                if component not in fields["Components"].split():
                    raise ValueError(f"{component} absent from signed {pocket} Release")
                jobs.append(executor.submit(source_index, downloader, pocket, component, hashes, mirrors, output))
        for future in concurrent.futures.as_completed(jobs):
            path, proof = future.result()
            all_indexes.append(proof)
            found, versions = parse_index(path, proof, requested, mirrors)
            for key, entry in found.items():
                if key in matches:
                    old = matches[key]
                    if old["files"] != entry["files"]:
                        raise ValueError(f"Conflicting authenticated source file lists for {key}")
                    old["source_indexes"].extend(entry["source_indexes"])
                else:
                    matches[key] = entry
            for name, values in versions.items():
                available.setdefault(name, set()).update(values)
            print(f"Verified Sources: {proof['pocket']}/{proof['component']}; matched {len(found)} requested versions", flush=True)
    missing = [{"package": name, "version": version, "available_versions": sorted(available.get(name, [])), "binary_packages": requested[(name, version)]} for name, version in sorted(requested) if (name, version) not in matches]
    packages, files_by_path = [], {}
    for key in sorted(matches):
        entry = matches[key]
        entry["binary_packages"] = requested[key]
        packages.append(entry)
        for file in entry["files"]:
            remote = file["repository_path"]
            existing = files_by_path.get(remote)
            if existing and (existing["sha256"], existing["size"]) != (file["sha256"], file["size"]):
                raise ValueError(f"Conflicting file digest: {remote}")
            if not existing:
                files_by_path[remote] = dict(file, source_packages=[])
            files_by_path[remote]["source_packages"].append({"package": key[0], "version": key[1]})
    archive_files = [files_by_path[k] for k in sorted(files_by_path)]
    total_bytes = sum(f["size"] for f in archive_files)
    manifest = {"schema_version": 1, "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "plan_only": args.plan_only, "input_tsv": args.packages_tsv.name, "input_tsv_sha256": sha256(args.packages_tsv), "keyring_sha256": sha256(args.keyring), "mirrors": mirrors, "binary_package_count": binary_count, "requested_source_package_count": len(requested), "matched_source_package_count": len(packages), "missing_source_package_count": len(missing), "archive_file_count": len(archive_files), "total_archive_bytes": total_bytes, "total_archive_gib": round(total_bytes/1024**3, 3), "authenticated_releases": sorted(releases, key=lambda x:x["pocket"]), "authenticated_source_indexes": sorted(all_indexes,key=lambda x:(x["pocket"],x["component"])), "packages": packages, "archive_files": archive_files, "missing": missing}
    (output/"ubuntu-source-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+"\n")
    write_tsv(output/"ubuntu-source-packages.tsv", ["source_package", "source_version", "file_count", "source_archive_bytes", "binary_packages"], ((e["package"],e["version"],len(e["files"]),sum(f["size"] for f in e["files"]),",".join(x["package"] for x in e["binary_packages"])) for e in packages))
    write_tsv(output/"ubuntu-source-files.tsv", ["repository_path", "size_bytes", "sha256", "url", "archive_path", "source_packages"], ((f["repository_path"],f["size"],f["sha256"],f["urls"][0],f["archive_path"],";".join(x["package"]+"="+x["version"] for x in f["source_packages"])) for f in archive_files))
    write_tsv(output/"ubuntu-source-missing.tsv", ["source_package", "requested_version", "available_signed_versions", "binary_packages"], ((e["package"],e["version"],";".join(e["available_versions"]),",".join(x["package"] for x in e["binary_packages"])) for e in missing))
    print(f"Plan: {len(packages)}/{len(requested)} source versions; {len(archive_files)} files; {total_bytes:,} bytes ({total_bytes/1024**3:.3f} GiB); {len(missing)} missing", flush=True)
    if missing:
        for entry in missing:
            print(f"MISSING {entry['package']} {entry['version']} (signed indexes contain: {', '.join(entry['available_versions']) or 'none'})", flush=True)
    if args.plan_only:
        return 2 if missing else 0
    if missing:
        print("Refusing incomplete source download; resolve missing exact versions or use --plan-only.", file=sys.stderr)
        return 2
    def download_source(file):
        result = downloader.fetch(file["urls"], output/file["archive_path"], {"size":file["size"],"sha256":file["sha256"]})
        return {"repository_path":file["repository_path"], **result}
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = [executor.submit(download_source, f) for f in archive_files]
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            results.append(future.result())
            print(f"Verified archive {i}/{len(archive_files)}", flush=True)
    source_verification = [verify_dsc(package, output) for package in packages]
    (output/"ubuntu-source-download-verification.json").write_text(json.dumps({"verified_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"manifest_sha256":sha256(output/"ubuntu-source-manifest.json"),"file_count":len(results),"source_package_count":len(source_verification),"total_archive_bytes":total_bytes,"source_packages":source_verification,"files":sorted(results,key=lambda x:x["repository_path"])},indent=2)+"\n")
    print("All exact source archives downloaded and SHA256 verified.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
