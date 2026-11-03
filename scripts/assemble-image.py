#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create a Firefly SD image in a new regular file. Never writes a block device."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,struct,subprocess,uuid
TASK=Path('/build')
SECTOR=512
BOOT_START=32768
BOOT_SECTORS=524288
ROOT_START=BOOT_START+BOOT_SECTORS
IMAGE_BYTES=8*1024**3
ROOT_SECTORS=IMAGE_BYTES//SECTOR-ROOT_START

def run(*args):subprocess.run([str(x) for x in args],check=True)
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('output',type=Path);a=ap.parse_args()
    image=a.output
    if image.exists() or image.is_symlink() or image.suffix!='.img':ap.error('Output must be a new .img file')
    # Finalize must unmount its chroot before the filesystem is copied.
    rootfs_path=str((TASK/'rootfs').resolve())
    for entry in Path('/proc/self/mountinfo').read_text().splitlines():
        mountpoint=entry.split()[4]
        if mountpoint==rootfs_path or mountpoint.startswith(rootfs_path+'/'):
            raise RuntimeError('Root filesystem still has active mounts; finish finalization first')
    scratch=TASK/'image-parts';scratch.mkdir(exist_ok=True)
    boot=scratch/'boot.fat';root=scratch/'root.ext4'
    with boot.open('wb') as f:f.truncate(BOOT_SECTORS*SECTOR)
    run('mkfs.vfat','-F','32','-n','FIREFLYBOOT',boot)
    for p in sorted((TASK/'boot-files').iterdir()):run('mcopy','-s','-i',boot,p,'::/')
    with root.open('wb') as f:f.truncate(ROOT_SECTORS*SECTOR)
    root_uuid=str(uuid.uuid4())
    run('mkfs.ext4','-F','-b','4096','-m','1','-L','FIREFLY_ROOT','-U',root_uuid,'-d',TASK/'rootfs',root)
    run('e2fsck','-f','-n',root)
    with image.open('xb') as f:f.truncate(IMAGE_BYTES)
    layout=f'label: dos\nunit: sectors\n\nstart={BOOT_START},size={BOOT_SECTORS},type=c,bootable\nstart={ROOT_START},size={ROOT_SECTORS},type=83\n'
    subprocess.run(['sfdisk',str(image)],input=layout,text=True,check=True)
    with image.open('r+b') as out:
        for name,offset in [('idbloader.img',32768),('u-boot-dtb.img',8388608)]:
            data=(TASK/'bootloader'/name).read_bytes()
            if offset+len(data)>=16*1024**2:raise ValueError('Loader boundary invalid')
            out.seek(offset);out.write(data)
        for part,offset in [(boot,BOOT_START*SECTOR),(root,ROOT_START*SECTOR)]:
            out.seek(offset)
            with part.open('rb') as f:shutil.copyfileobj(f,out,4*1024*1024)
    # Check MBR and all inserted low-level loader bytes.
    with image.open('rb') as f:
        mbr=f.read(512);assert mbr[510:]==b'\x55\xaa'
        p1=struct.unpack('<B3sB3sII',mbr[446:462]);p2=struct.unpack('<B3sB3sII',mbr[462:478])
        assert (p1[2],p1[4],p1[5])==(12,BOOT_START,BOOT_SECTORS)
        assert (p2[2],p2[4],p2[5])==(131,ROOT_START,ROOT_SECTORS)
        for name,offset in [('idbloader.img',32768),('u-boot-dtb.img',8388608)]:
            data=(TASK/'bootloader'/name).read_bytes();f.seek(offset);assert f.read(len(data))==data
    result={'image_bytes':IMAGE_BYTES,'image_sha256':digest(image),'root_uuid':root_uuid,'boot_label':'FIREFLYBOOT','root_label':'FIREFLY_ROOT','partitions':{'boot_start':BOOT_START,'boot_sectors':BOOT_SECTORS,'root_start':ROOT_START,'root_sectors':ROOT_SECTORS},'boot_files':{str(p.relative_to(TASK/'boot-files')):digest(p) for p in sorted((TASK/'boot-files').rglob('*')) if p.is_file()}}
    (TASK/'image-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
