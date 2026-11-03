#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Download the pinned build inputs and verify every archive before use."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024**2), b''):
            result.update(block)
    return result.hexdigest()


def fetch(item):
    target = ROOT / item['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file() or digest(target) != item['sha256']:
            raise ValueError('Existing input failed SHA-256 verification: ' + item['path'])
        print('Verified ' + item['path'], flush=True)
        return
    for attempt in range(3):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name + '.', suffix='.partial', delete=False) as output:
                temporary = Path(output.name)
                print('Downloading ' + item['url'], flush=True)
                with urllib.request.urlopen(item['url'], timeout=90) as response:
                    while block := response.read(4 * 1024**2):
                        output.write(block)
            if digest(temporary) != item['sha256']:
                raise ValueError('Downloaded input failed SHA-256 verification: ' + item['path'])
            temporary.chmod(0o644)
            temporary.replace(target)
            print('Verified ' + item['path'], flush=True)
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', choices=['ubuntu-base', 'linux', 'u-boot'])
    args = parser.parse_args()
    for item in json.loads((ROOT / 'sources.json').read_text()):
        if args.component is None or args.component == item['name']:
            fetch(item)


if __name__ == '__main__':
    main()
