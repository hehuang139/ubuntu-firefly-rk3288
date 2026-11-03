#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prefetch apt-selected, hash-verified packages using concurrent downloads."""
import concurrent.futures,hashlib,pathlib,re,subprocess,sys,time,urllib.request
root=pathlib.Path('/build/rootfs')
# Use apt's own dependency resolution and authenticated package index metadata.
script=pathlib.Path('/build/scripts/install-rootfs.sh').read_text()
block=script.split('apt-get install -y --no-install-recommends \\\n',1)[1].split('\nlocale-gen',1)[0]
packages=block.replace('\\\n',' ').split()
raw=subprocess.check_output(['chroot',str(root),'/usr/bin/apt-get','-o','Debug::NoLocking=1','--print-uris','--yes','--no-install-recommends','install',*packages],text=True)
pathlib.Path('/build/package-uris.txt').write_text(raw)
items=[]
for line in raw.splitlines():
    m=re.fullmatch(r"'([^']+)' (\S+) (\d+) (\S+)",line)
    if m: items.append(m.groups())
cache=root/'var/cache/apt/archives'
def get(item):
    url,name,size,digest=item;size=int(size); target=cache/name
    algo,hexhash=digest.split(':',1)
    def valid(path):
        if not path.is_file() or path.stat().st_size!=size:return False
        h=hashlib.new(('md5' if algo.lower()=='md5sum' else algo.lower()))
        with path.open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
        return h.hexdigest()==hexhash
    if valid(target): return
    temp=cache/(name+'.prefetch')
    for n in range(5):
        try:
            with urllib.request.urlopen(url,timeout=90) as r,temp.open('wb') as out:
                while b:=r.read(1024*1024):out.write(b)
            if not valid(temp):raise ValueError('package hash mismatch')
            temp.replace(target)
            print('fetched',name,flush=True);return
        except Exception as e:
            print('retry',name,str(e),flush=True)
            if n==4:raise
            time.sleep(1)
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:list(ex.map(get,items))
print('Verified packages',len(items),flush=True)
