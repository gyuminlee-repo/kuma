#!/usr/bin/env python3
"""Fetch only the two licensed public ProteinGym pilot members with bounded HTTP ranges.

No credentials or model inference. Roughly 44 MB transferred, not the 1.9 GB archive.
Output is caller-owned; raw large sources need not be committed. Fails if the server
ignores ranges, bytes change mid-read, or fixed size guards are exceeded.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

VERSION_ROOT='https://marks.hms.harvard.edu/proteingym/ProteinGym_v1.3/'
COMMIT='144fe22b07dfaeec2b366f2346203a9838a55b4c'
GITHUB_ROOT=f'https://raw.githubusercontent.com/OATML-Markslab/ProteinGym/{COMMIT}/'
ASSAYS=('GFP_AEQVI_Sarkisyan_2016','RL40A_YEAST_Roscoe_2013')


class RemoteZip(io.RawIOBase):
    def __init__(self,url: str):
        self.url=url; self.position=0; self.transferred=0
        with urllib.request.urlopen(urllib.request.Request(url,headers={'Range':'bytes=-1'}),timeout=60) as response:
            if response.status!=206: raise ValueError('server does not support bounded ranges')
            self.size=int(response.headers['Content-Range'].split('/')[-1])
            self.etag=response.headers.get('ETag')
    def seekable(self) -> bool: return True
    def seek(self,offset: int,whence: int=0) -> int:
        if whence not in (0,1,2): raise ValueError('invalid whence')
        self.position=offset+(0 if whence==0 else self.position if whence==1 else self.size)
        if not 0<=self.position<=self.size: raise ValueError('seek outside archive')
        return self.position
    def tell(self) -> int: return self.position
    def read(self,size: int=-1) -> bytes:
        size=min(self.size-self.position if size<0 else size,self.size-self.position)
        if size==0:return b''
        if size>64_000_000 or self.transferred+size>80_000_000:raise ValueError('archive transfer guard exceeded')
        start=self.position;end=start+size-1
        headers={'Range':f'bytes={start}-{end}'}
        if self.etag: headers['If-Match']=self.etag
        with urllib.request.urlopen(urllib.request.Request(self.url,headers=headers),timeout=60) as response:
            if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{self.size}':
                raise ValueError('unexpected range response')
            if self.etag and response.headers.get('ETag')!=self.etag:raise ValueError('archive changed during transfer')
            data=response.read(size+1)
        if len(data)!=size:raise ValueError('incorrect range length')
        self.position+=size;self.transferred+=size
        return data


def fetch(destination: Path) -> None:
    destination.mkdir(parents=True,exist_ok=True)
    for name,remote in [('ref.txt','reference_files/DMS_substitutions.csv'),('config.json','config.json'),('license.txt','LICENSE')]:
        with urllib.request.urlopen(GITHUB_ROOT+remote,timeout=60) as response:data=response.read(2_000_001)
        if len(data)>2_000_000:raise ValueError('metadata size guard exceeded')
        (destination/name).write_bytes(data)
    manifest=[]
    for archive in ('zero_shot_substitutions_scores.zip','DMS_ProteinGym_substitutions.zip','ProteinGym_AF2_structures.zip'):
        source=RemoteZip(VERSION_ROOT+archive)
        with zipfile.ZipFile(source) as zipped:
            names=zipped.namelist()
            expected=[a+'.csv' for a in ASSAYS] if 'structures' not in archive else ['GFP_AEQVI.pdb','RL40A_YEAST.pdb']
            for filename in expected:
                matches=[n for n in names if Path(n).name==filename]
                if len(matches)!=1:raise ValueError('expected exactly one declared archive member')
                member=matches[0];info=zipped.getinfo(member)
                if info.file_size>128_000_000:raise ValueError('member expansion guard exceeded')
                data=zipped.read(member)  # verifies member CRC
                parent=destination/('scores_' if archive.startswith('zero') else 'measurements_' if archive.startswith('DMS_') else '')
                parent.mkdir(exist_ok=True);(parent/filename).write_bytes(data)
                manifest.append({'url':VERSION_ROOT+archive,'member':member,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'local':str(parent/filename)})
        print(f'{archive}: {source.transferred} bytes transferred')
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    fetch(parser.parse_args().output_dir)
