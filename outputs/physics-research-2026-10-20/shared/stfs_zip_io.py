import sys,io,hashlib,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'shared'))
from stfs_reader import STFS
class STFSFile(io.RawIOBase):
 def __init__(self,p,entry):
  self.p=p;self.entry=entry;self.pos=0;self.blocks=[];self.cache={};block=entry['start'];seen=set()
  while len(self.blocks)*4096<entry['size']:
   if block==0xffffff or block in seen: raise ValueError('Invalid block chain')
   seen.add(block);self.blocks.append(block);block=p.next_block(block)
  if len(self.blocks)!=entry['blocks']:raise ValueError('Allocation count mismatch')
 def seekable(self):return True
 def readable(self):return True
 def tell(self):return self.pos
 def seek(self,offset,whence=0):
  pos=offset if whence==0 else self.pos+offset if whence==1 else self.entry['size']+offset
  if pos<0:raise ValueError('Negative seek')
  self.pos=pos;return pos
 def read(self,size=-1):
  size=min(self.entry['size']-self.pos,size if size>=0 else self.entry['size'])
  out=bytearray()
  while len(out)<size:
   idx=self.pos//4096;off=self.pos%4096;block=self.blocks[idx]
   if idx not in self.cache:
    b=self.p.read_at(self.p.offset(block),4096)
    if hashlib.sha1(b).digest()!=self.p.hash_record(block)[:20]:raise ValueError('Block SHA1 mismatch')
    if len(self.cache)>2048:self.cache.clear()
    self.cache[idx]=b
   n=min(4096-off,size-len(out));out.extend(self.cache[idx][off:off+n]);self.pos+=n
  return bytes(out)
