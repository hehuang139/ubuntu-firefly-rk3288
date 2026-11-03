#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify a completed Firefly Ubuntu image using regular files and debugfs only."""
from pathlib import Path
import argparse
import configparser
import gzip
import hashlib
import json
import posixpath
import re
import stat
import struct
import subprocess
import sys
import tempfile
import zlib
import uuid

TASK = Path('/build')
RELEASE = '6.6.161-firefly'
SECTOR = 512
BOOT_START = 32768
BOOT_SECTORS = 524288
ROOT_START = BOOT_START + BOOT_SECTORS
IMAGE_BYTES = 8 * 1024**3
REPORT = TASK / 'validation.json'
report = {'image': None, 'checks': {}, 'result': 'incomplete'}

class AuditError(Exception):
    pass

def check(condition, name, detail=None):
    report['checks'][name] = {'pass': bool(condition)}
    if detail is not None:
        report['checks'][name]['detail'] = detail
    if not condition:
        raise AuditError(name)

def run(*args, accepted=(0,)):
    p = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode not in accepted:
        raise AuditError('Command failed: ' + ' '.join(str(x) for x in args) + '\n' + p.stderr.decode(errors='replace')[-2000:])
    return p

def regular(path):
    return not path.is_symlink() and stat.S_ISREG(path.stat().st_mode)

def digest(path, offset=0, length=None):
    h = hashlib.sha256()
    with path.open('rb') as f:
        f.seek(offset)
        left = length
        while left is None or left:
            b = f.read(4 * 1024**2 if left is None else min(left, 4 * 1024**2))
            if not b:
                if left:
                    raise AuditError('Unexpected end of file: ' + str(path))
                break
            h.update(b)
            if left is not None:
                left -= len(b)
    return h.hexdigest()

def debug(part, command):
    p = run('debugfs', '-R', command, part)
    err = p.stderr.decode(errors='replace')
    if 'File not found' in err:
        raise FileNotFoundError(command)
    if any(s in err for s in ('Filesystem not open', 'Bad magic number', 'Ext2 inode is not a directory')):
        raise AuditError(err)
    return p.stdout

def raw_inode(part, path):
    text = debug(part, 'stat ' + path).decode(errors='replace')
    m = re.search(r'Type:\s*(\S+)\s+Mode:\s*([0-7]+)', text)
    own = re.search(r'User:\s*(\d+)\s+Group:\s*(\d+)', text)
    if not m or not own:
        raise AuditError('Cannot parse inode metadata: ' + path)
    return {'type': m[1], 'mode': int(m[2], 8), 'uid': int(own[1]), 'gid': int(own[2]), 'text': text}

def resolve(part, path, follow_final=False):
    # debugfs does not consistently follow intermediate symlinks across versions.
    queue = posixpath.normpath('/' + path.lstrip('/')).strip('/').split('/')
    current = '/'
    followed = 0
    while queue:
        component = queue.pop(0)
        if not component:
            continue
        candidate = posixpath.join(current, component)
        meta = raw_inode(part, candidate)
        if meta['type'] == 'symlink' and (queue or follow_final):
            match = re.search(r'Fast link dest:\s*"([^"]+)"', meta['text'])
            if not match:
                raise AuditError('Unsupported long symlink while resolving ' + candidate)
            target = match[1]
            destination = target if target.startswith('/') else posixpath.join(current, target)
            destination = posixpath.normpath(destination)
            queue = destination.strip('/').split('/') + queue
            current = '/'
            followed += 1
            if followed > 40:
                raise AuditError('Symlink loop: ' + path)
        else:
            current = candidate
    return current

def read(part, path):
    return debug(part, 'cat ' + resolve(part, path, follow_final=True))

def inode(part, path):
    return raw_inode(part, resolve(part, path))

def exists(part, path):
    try:
        inode(part, path)
        return True
    except FileNotFoundError:
        return False

def link(part, path, suffix):
    meta = inode(part, path)
    m = re.search(r'Fast link dest:\s*"([^"]+)"', meta['text'])
    check(meta['type'] == 'symlink' and m is not None and m[1].endswith(suffix), 'symlink:' + path, m[1] if m else meta['type'])

def mode(part, path, expected):
    meta = inode(part, path)
    check(meta['uid'] == 0 and meta['gid'] == 0 and meta['mode'] == expected,
          'owner-mode:' + path, {'uid': meta['uid'], 'gid': meta['gid'], 'mode': oct(meta['mode'])})

def parse_newc(data):
    names = set()
    pos = 0
    while pos + 110 <= len(data):
        if data[pos:pos + 6] not in (b'070701', b'070702'):
            if data[pos:].strip(b'\0'):
                raise AuditError('Unexpected initramfs CPIO data')
            break
        fields = [int(data[pos + 6 + i * 8:pos + 14 + i * 8], 16) for i in range(13)]
        size, namesize = fields[6], fields[11]
        start = pos + 110
        name = data[start:start + namesize - 1].decode(errors='replace').lstrip('./')
        payload = (start + namesize + 3) & ~3
        if payload + size > len(data):
            raise AuditError('Truncated initramfs CPIO member')
        pos = (payload + size + 3) & ~3
        if name == 'TRAILER!!!':
            while pos < len(data) and data[pos] == 0:
                pos += 1
            return names, pos
        names.add(name)
    return names, pos

def initramfs_members(data):
    names, formats, pos = set(), [], 0
    while pos < len(data):
        while pos < len(data) and data[pos] == 0:
            pos += 1
        if pos == len(data):
            break
        if data[pos:pos + 6] in (b'070701', b'070702'):
            members, used = parse_newc(data[pos:])
            if used == 0:
                raise AuditError('Empty initramfs archive')
            names.update(members)
            formats.append('cpio')
            pos += used
        elif data[pos:pos + 2] == b'\x1f\x8b':
            members, nested = initramfs_members(gzip.decompress(data[pos:]))
            names.update(members)
            formats.append('gzip')
            formats.extend(nested)
            break
        else:
            raise AuditError('Unsupported initramfs encoding at byte ' + str(pos))
    return names, formats

def audit_root(part, temp):
    sb = part.open('rb')
    with sb:
        sb.seek(1024)
        superblock = sb.read(1024)
    check(superblock[56:58] == b'\x53\xef', 'ext4-superblock-magic')
    label = superblock[120:136].split(b'\0', 1)[0].decode()
    check(label == 'FIREFLY_ROOT', 'ext4-label', label)
    root_uuid = str(uuid.UUID(bytes=superblock[104:120]))
    check(root_uuid == json.loads((TASK / 'image-manifest.json').read_text())['root_uuid'], 'ext4-uuid-matches-manifest', root_uuid)
    fsck = run('e2fsck', '-f', '-n', part, accepted=(0, 1, 2, 4, 8, 16, 32, 128))
    check(fsck.returncode == 0, 'e2fsck-readonly', {
        'returncode': fsck.returncode,
        'output': (fsck.stdout + fsck.stderr).decode(errors='replace')[-4000:]})

    # Read dpkg's actual on-image database rather than a build-side package list.
    package_status = {}
    for paragraph in read(part, '/var/lib/dpkg/status').decode().split('\n\n'):
        fields = {}
        for line in paragraph.splitlines():
            if line and not line[0].isspace() and ':' in line:
                key, value = line.split(':', 1)
                fields[key] = value.strip()
        if 'Package' in fields:
            package_status[fields['Package']] = fields
    incomplete = {name: fields.get('Status', '') for name, fields in package_status.items()
                  if fields.get('Status') not in ('install ok installed', 'deinstall ok config-files')}
    check(bool(package_status) and not incomplete, 'dpkg-no-incomplete-packages', {
        'package_records': len(package_status), 'incomplete': incomplete})
    installed = {name: fields for name, fields in package_status.items()
                 if fields.get('Status') == 'install ok installed'}
    architectures = sorted({fields.get('Architecture', '') for fields in installed.values()})
    check(set(architectures) <= {'armhf', 'all'}, 'installed-package-architectures', architectures)
    critical = {}
    for name in ('gdm3', 'gnome-initial-setup', 'gnome-shell', 'gnome-session',
                 'libgl1-mesa-dri', 'cloud-guest-utils'):
        fields = installed.get(name, {})
        details = {key.lower(): fields.get(key) for key in ('Version', 'Architecture', 'Status')}
        check(bool(fields.get('Version')) and fields.get('Architecture') in ('armhf', 'all'),
              'installed-package:' + name, details)
        critical[name] = details
    report['critical_packages'] = critical
    check(exists(part, '/usr/share/wayland-sessions/gnome.desktop'), 'gnome-wayland-session-desktop')
    check(any(exists(part, path) for path in ('/usr/share/xsessions/gnome.desktop',
          '/usr/share/xsessions/gnome-xorg.desktop')), 'gnome-xorg-session-desktop')
    check(exists(part, '/usr/lib/arm-linux-gnueabihf/dri/panfrost_dri.so'), 'mesa-panfrost-dri-library')

    passwd = read(part, '/etc/passwd').decode().splitlines()
    users = [row.split(':') for row in passwd]
    check(not any(1000 <= int(row[2]) < 65534 for row in users), 'no-precreated-ordinary-user')
    check(all(any(row[0] == name for row in users) for name in ('root', 'gdm', 'gnome-initial-setup')), 'setup-system-accounts')
    shadow = [row.split(':') for row in read(part, '/etc/shadow').decode().splitlines()]
    root = [row for row in shadow if row[0] == 'root']
    check(len(root) == 1 and root[0][1].startswith(('!', '*')), 'root-password-locked')
    check(read(part, '/etc/machine-id').strip() == b'', 'machine-id-empty')
    link(part, '/var/lib/dbus/machine-id', '/etc/machine-id')
    check(not exists(part, '/var/lib/systemd/random-seed'), 'no-build-random-seed')
    check(not exists(part, '/usr/bin/qemu-arm-static'), 'no-build-emulator')

    gdm = configparser.ConfigParser()
    gdm.read_string(read(part, '/etc/gdm3/custom.conf').decode())
    check(gdm.getboolean('daemon', 'InitialSetupEnable') and gdm.getboolean('daemon', 'WaylandEnable'), 'gdm-initial-setup-wayland')
    check(not gdm.getboolean('daemon', 'AutomaticLoginEnable', fallback=False), 'gdm-no-shared-autologin')
    check(read(part, '/etc/X11/default-display-manager').strip() == b'/usr/sbin/gdm3', 'default-display-manager')
    link(part, '/etc/systemd/system/display-manager.service', '/gdm3.service')
    link(part, '/etc/systemd/system/default.target', '/graphical.target')
    for unit in ('firefly-resize.service', 'NetworkManager.service', 'systemd-resolved.service'):
        link(part, '/etc/systemd/system/multi-user.target.wants/' + unit, '/' + unit)
    link(part, '/etc/systemd/system/sysinit.target.wants/systemd-timesyncd.service', '/systemd-timesyncd.service')
    link(part, '/etc/systemd/system/getty.target.wants/serial-getty@ttyS2.service', '/serial-getty@.service')
    for path in ('/etc/systemd/system/multi-user.target.wants/ssh.service', '/etc/systemd/system/sockets.target.wants/ssh.socket'):
        check(not exists(part, path), 'ssh-disabled:' + path)
    ssh_files = debug(part, 'ls -p /etc/ssh').decode()
    check(not re.search(r'/ssh_host_[^/]+_key(?:\.pub)?/', ssh_files), 'no-shared-ssh-host-keys')
    ssh_dropin = read(part, '/etc/systemd/system/ssh.service.d/10-host-keys.conf').decode()
    pre = re.findall(r'^ExecStartPre=(.*)$', ssh_dropin, re.M)
    check(pre == ['', '/usr/bin/ssh-keygen -A', '/usr/sbin/sshd -t'], 'ssh-first-start-key-order')
    ssh_conf = read(part, '/etc/ssh/sshd_config.d/10-firefly.conf').decode()
    check(re.search(r'^PermitRootLogin\s+no\s*$', ssh_conf, re.M) is not None, 'ssh-root-login-disabled')

    expected_modes = {
        '/etc/gdm3/custom.conf': 0o644,
        '/etc/systemd/system/firefly-resize.service': 0o644,
        '/usr/local/sbin/firefly-resize': 0o755,
        '/etc/netplan/01-network-manager.yaml': 0o600,
        '/etc/NetworkManager/conf.d/10-firefly.conf': 0o644,
        '/etc/systemd/system/ssh.service.d/10-host-keys.conf': 0o644,
        '/etc/ssh/sshd_config.d/10-firefly.conf': 0o644,
    }
    for path, value in expected_modes.items():
        mode(part, path, value)
    fstab = read(part, '/etc/fstab').decode()
    entries = [line.split() for line in fstab.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    check(any(x[:3] == ['LABEL=FIREFLY_ROOT', '/', 'ext4'] for x in entries), 'fstab-root-label')
    check(any(x[:3] == ['LABEL=FIREFLYBOOT', '/boot/firmware', 'vfat'] for x in entries), 'fstab-boot-label')
    link(part, '/etc/resolv.conf', '/run/systemd/resolve/stub-resolv.conf')
    mode(part, '/etc/dconf/db/local', 0o644)
    check(len(read(part, '/etc/dconf/db/local')) > 0, 'dconf-defaults-compiled')

    dep = read(part, '/lib/modules/' + RELEASE + '/modules.dep').decode()
    module_paths = [line.split(':', 1)[0] for line in dep.splitlines() if ':' in line]
    check(len(module_paths) > 0, 'depmod-generated', {'release': RELEASE, 'module_count': len(module_paths)})
    for suffix in ('/panfrost.ko', '/zram.ko'):
        found = [p for p in module_paths if p.endswith(suffix)]
        check(len(found) == 1, 'module-present:' + suffix)
        dest = temp / Path(found[0]).name
        run('debugfs', '-R', 'dump ' + resolve(part, '/lib/modules/' + RELEASE + '/' + found[0], follow_final=True) + ' ' + str(dest), part)
        vermagic = run('modinfo', '-F', 'vermagic', dest).stdout.decode().strip()
        check(vermagic.split()[0] == RELEASE, 'module-vermagic:' + suffix, vermagic)
    kernel = read(part, '/boot/vmlinuz-' + RELEASE)
    initrd = read(part, '/boot/initrd.img-' + RELEASE)
    check(hashlib.sha256(kernel).hexdigest() == digest(TASK / 'boot-files/boot/zImage'), 'rootfs-kernel-matches-fat-input')
    check(hashlib.sha256(initrd).hexdigest() == digest(TASK / 'boot-files/boot/initrd.img'), 'rootfs-initrd-matches-fat-input')
    check(not exists(part, '/var/lib/firefly/root-expanded'), 'first-boot-resize-not-marked-complete')

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('image', type=Path)
    args = ap.parse_args()
    image = args.image
    report['image'] = str(image)
    check(regular(image), 'regular-image-file')
    check(image.stat().st_size == IMAGE_BYTES, 'image-length', image.stat().st_size)
    manifest = json.loads((TASK / 'image-manifest.json').read_text())
    root_sectors = IMAGE_BYTES // SECTOR - ROOT_START
    with image.open('rb') as f:
        mbr = f.read(512)
        check(mbr[510:] == b'\x55\xaa', 'mbr-signature')
        parts = [struct.unpack('<B3sB3sII', mbr[446 + i * 16:462 + i * 16]) for i in range(4)]
        check((parts[0][0], parts[0][2], parts[0][4], parts[0][5]) == (128, 12, BOOT_START, BOOT_SECTORS), 'mbr-boot-partition')
        check((parts[1][2], parts[1][4], parts[1][5]) == (131, ROOT_START, root_sectors), 'mbr-root-partition')
        check(all(p[2] == 0 and p[4] == 0 and p[5] == 0 for p in parts[2:]), 'no-extra-partitions')
        check(BOOT_START * SECTOR + BOOT_SECTORS * SECTOR == ROOT_START * SECTOR and (ROOT_START + root_sectors) * SECTOR == IMAGE_BYTES, 'partition-boundaries')
        previous_end = 512
        for name, offset, limit in [('idbloader.img', 32768, 8388608), ('u-boot-dtb.img', 8388608, 16 * 1024**2)]:
            expected = (TASK / 'bootloader' / name).read_bytes()
            check(previous_end <= offset and offset + len(expected) <= limit, 'loader-boundary:' + name)
            f.seek(offset)
            check(f.read(len(expected)) == expected, 'loader-byte-match:' + name, {'offset': offset, 'bytes': len(expected), 'sha256': hashlib.sha256(expected).hexdigest()})
            previous_end = offset + len(expected)
            if name == 'u-boot-dtb.img':
                header = bytearray(expected[:64])
                check(struct.unpack('>I', header[:4])[0] == 0x27051956, 'uboot-uimage-magic')
                stored = struct.unpack('>I', header[4:8])[0]
                header[4:8] = bytes(4)
                size = struct.unpack('>I', expected[12:16])[0]
                data_crc = struct.unpack('>I', expected[24:28])[0]
                check(zlib.crc32(header) == stored and zlib.crc32(expected[64:64 + size]) == data_crc, 'uboot-header-payload-crc')
        f.seek(BOOT_START * SECTOR)
        bpb = f.read(512)
        check(bpb[71:82].decode().strip() == 'FIREFLYBOOT', 'fat-boot-label')
    actual_image_hash = digest(image)
    check(actual_image_hash == manifest['image_sha256'], 'whole-image-sha256', actual_image_hash)
    check(manifest['image_bytes'] == IMAGE_BYTES, 'manifest-image-size')
    drive = str(image) + '@@' + str(BOOT_START * SECTOR)
    fat_contents = {}
    expected_paths = {str(p.relative_to(TASK / 'boot-files')): p for p in (TASK / 'boot-files').rglob('*') if p.is_file()}
    check(set(expected_paths) == set(manifest['boot_files']), 'manifest-boot-file-set')
    for relative, source in sorted(expected_paths.items()):
        data = run('mtype', '-i', drive, '::/' + relative).stdout
        value = hashlib.sha256(data).hexdigest()
        check(value == digest(source) == manifest['boot_files'][relative], 'fat-file:' + relative, value)
        fat_contents[relative] = data
    kernel = fat_contents['boot/zImage']
    check(len(kernel) >= 48 and struct.unpack('<I', kernel[36:40])[0] == 0x016F2818, 'arm-zimage-header')
    dtb = fat_contents['boot/rk3288-firefly.dtb']
    check(len(dtb) >= 40 and struct.unpack('>I', dtb[:4])[0] == 0xD00DFEED and struct.unpack('>I', dtb[4:8])[0] == len(dtb), 'dtb-header-length')
    initrd = fat_contents['boot/initrd.img']
    members, formats = initramfs_members(initrd)
    check('gzip' in formats, 'initramfs-gzip-format', formats)
    check({'init', 'scripts/local', 'conf/initramfs.conf'} <= members, 'initramfs-core-members', {'member_count': len(members)})
    extlinux = fat_contents['extlinux/extlinux.conf'].decode()
    for directive, value in [('LINUX', '/boot/zImage'), ('INITRD', '/boot/initrd.img'), ('FDT', '/boot/rk3288-firefly.dtb')]:
        check(re.search(r'^\s*' + directive + r'\s+' + re.escape(value) + r'\s*$', extlinux, re.M) is not None, 'extlinux:' + directive)
    append = next((line.strip()[7:] for line in extlinux.splitlines() if line.strip().startswith('APPEND ')), '')
    check({'root=LABEL=FIREFLY_ROOT', 'rootfstype=ext4', 'rootwait', 'rw'} <= set(append.split()), 'extlinux-root-options')
    check('nomodeset' not in append.split(), 'kernel-modesetting-enabled')
    root_bytes = root_sectors * SECTOR
    image_root_hash = digest(image, ROOT_START * SECTOR, root_bytes)
    with tempfile.TemporaryDirectory(prefix='firefly-verify-', dir=TASK) as tempname:
        temp = Path(tempname)
        candidate = TASK / 'image-parts/root.ext4'
        if candidate.exists():
            check(regular(candidate) and candidate.stat().st_size == root_bytes, 'root-partition-source-file')
            check(digest(candidate) == image_root_hash, 'root-partition-byte-hash-match', image_root_hash)
            part = candidate
        else:
            part = temp / 'root.ext4'
            with image.open('rb') as source, part.open('xb') as target:
                source.seek(ROOT_START * SECTOR)
                left = root_bytes
                while left:
                    data = source.read(min(left, 4 * 1024**2))
                    if not data:
                        raise AuditError('Truncated image root partition')
                    target.write(data)
                    left -= len(data)
            check(digest(part) == image_root_hash, 'extracted-root-partition-hash', image_root_hash)
        audit_root(part, temp)
    report['result'] = 'pass'

if __name__ == '__main__':
    status = 0
    try:
        main()
    except Exception as e:
        status = 1
        report['result'] = 'fail'
        report['error'] = str(e)
    finally:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'result': report['result'], 'checks': len(report['checks']), 'report': str(REPORT), 'error': report.get('error')}, ensure_ascii=False))
    sys.exit(status)
