"""Offline, read-only STFS metadata/payload reader.

Layout independently implemented from locally available ReXGlue/Xenia structures:
work/rexglue-sdk/include/rex/filesystem/devices/stfs_xbox.h and
work/rexglue-sdk/src/filesystem/devices/stfs_container_device.cpp.
Does not mount, install, execute, or modify a package. Block SHA1 can be checked;
this is not verification of the Microsoft signature or authenticity.
"""
from pathlib import Path
import hashlib, json, sys

def uint(b, start, size, endian='big'):
    return int.from_bytes(b[start:start+size], endian)

class STFS:
    def __init__(self, path):
        self.path = Path(path)
        self.f = self.path.open('rb')
        h = self.f.read(0xA000)
        if h[:4] not in (b'LIVE', b'PIRS', b'CON '):
            raise ValueError('Not an STFS content package')
        if uint(h, 0x3A9, 4) != 0:
            raise ValueError('SVOD unsupported')
        self.header_size = uint(h, 0x340, 4)
        self.base = (self.header_size + 4095) & ~4095
        self.flags = h[0x37B]
        self.nhash = 1 if self.flags & 1 else 2
        self.table_count = uint(h, 0x37C, 2, 'little')
        self.table_start = uint(h, 0x37E, 3, 'little')
        self.total_blocks = uint(h, 0x395, 4)
        self.cache = {}
        self.meta = {'path':str(self.path),'size':self.path.stat().st_size,
          'magic':h[:4].decode(), 'header_size':self.header_size,
          'content_type':f'{uint(h,0x344,4):08X}', 'title_id':f'{uint(h,0x360,4):08X}',
          'version':f'{uint(h,0x358,4):08X}', 'base_version':f'{uint(h,0x35C,4):08X}',
          'media_id':f'{uint(h,0x354,4):08X}',
          'display_name':h[0x411:0x511].decode('utf-16-be',errors='replace').split('\0')[0],
          'description':h[0xD11:0xE11].decode('utf-16-be',errors='replace').split('\0')[0],
          'flags':self.flags,'file_table_blocks':self.table_count, 'total_blocks':self.total_blocks}
        self.entries = []
        block = self.table_start
        for n in range(self.table_count):
            if block == 0xFFFFFF: raise ValueError('Short directory chain')
            data = self.read_at(self.offset(block),4096)
            for j in range(64):
                r = data[j*64:(j+1)*64]
                if not r[0]: break
                length = r[40] & 63
                if length > 40: raise ValueError('Invalid entry name')
                name = r[:length].decode('utf-8',errors='replace')
                parent = uint(r,50,2)
                if parent != 0xFFFF and parent >= len(self.entries): raise ValueError('Invalid parent index')
                full = name if parent == 0xFFFF else self.entries[parent]['name']+'/'+name
                self.entries.append({'index':len(self.entries),'name':full,
                    'directory':bool(r[40]&128),'contiguous':bool(r[40]&64),
                    'blocks':uint(r,44,3,'little'), 'start':uint(r,47,3,'little'),
                    'size':uint(r,52,4)})
            block = self.next_block(block)
        self.meta['entry_count'] = len(self.entries)
        self.meta['file_count'] = sum(not x['directory'] for x in self.entries)

    def close(self): self.f.close()
    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    def read_at(self,offset,size):
        if offset < 0 or offset+size > self.meta['size']: raise ValueError('Read out of range')
        self.f.seek(offset); b=self.f.read(size)
        if len(b)!=size: raise ValueError('Truncated read')
        return b
    def offset(self,block):
        if not 0 <= block < self.total_blocks: raise ValueError('Block out of range')
        n=block; level=170
        for _ in range(3):
            n += ((block+level)//level)*self.nhash
            if block < level: break
            level *= 170
        return self.base+n*4096
    def hash_offset(self,block,level):
        step0=170+self.nhash; step1=28900+171*self.nhash
        if level==0:
            n=0 if block<170 else (block//170)*step0+((block//28900)+1)*self.nhash+(self.nhash if block>=28900 else 0)
        elif level==1: n=step0 if block<28900 else (block//28900)*step1+self.nhash
        else: n=step1
        return self.base+n*4096
    def table(self,offset,secondary=0):
        key=(offset,secondary)
        if key not in self.cache: self.cache[key]=self.read_at(offset+secondary,4096)
        return self.cache[key]
    def hash_record(self,block):
        secondary=4096 if self.flags&2 else 0
        if self.nhash==1: secondary=0
        elif self.total_blocks>170:
            if self.total_blocks>28900:
                t=self.table(self.hash_offset(block,2),secondary)
                info=uint(t,(block//28900%170)*24+20,4)
                secondary=4096 if info&0x40000000 else 0
            t=self.table(self.hash_offset(block,1),secondary)
            info=uint(t,(block//170%170)*24+20,4)
            secondary=4096 if info&0x40000000 else 0
        t=self.table(self.hash_offset(block,0),secondary)
        return t[(block%170)*24:(block%170+1)*24]
    def next_block(self,block): return uint(self.hash_record(block),21,3)
    def read(self,entry,verify=True,limit=128*1024*1024):
        if isinstance(entry,str): entry=next(e for e in self.entries if e['name'].lower()==entry.lower())
        if entry['directory']: raise ValueError('Cannot read a directory')
        if entry['size']>limit: raise ValueError('Selected file exceeds read limit')
        out=bytearray(); block=entry['start']; seen=set()
        while len(out)<entry['size']:
            if block==0xFFFFFF or block in seen: raise ValueError('Broken/cyclic block chain')
            seen.add(block); data=self.read_at(self.offset(block),4096); rec=self.hash_record(block)
            if verify and hashlib.sha1(data).digest()!=rec[:20]: raise ValueError(f'Block SHA1 mismatch: {block}')
            out.extend(data[:min(4096,entry['size']-len(out))]); block=uint(rec,21,3)
        if len(seen)!=entry['blocks']: raise ValueError('Allocation count mismatch')
        return bytes(out)

if __name__=='__main__':
    with STFS(sys.argv[1]) as package:
        print(json.dumps({'metadata':package.meta,'entries':package.entries},ensure_ascii=False,indent=2))
