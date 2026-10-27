"""Read Forza method-21 ZIP files using local libmspack. Verify exact ZIP CRC32."""
from ..paths import PHYSICS_RESEARCH_OUTPUT
import ctypes, struct, zlib, zipfile
_dll=None
def decode21(data,size,crc):
    global _dll
    if _dll is None:
        _dll=ctypes.CDLL(str(PHYSICS_RESEARCH_OUTPUT / 'shared/lzx_bridge.dll'))
        _dll.decode_lzx.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]
        _dll.decode_lzx.restype=ctypes.c_int
    pos=0; raw=bytearray(); declared=0
    while pos<len(data):
        if data[pos]==255:
            if pos+5>len(data): raise ValueError('Truncated LZX frame')
            outsize=int.from_bytes(data[pos+1:pos+3],'big'); n=int.from_bytes(data[pos+3:pos+5],'big');pos+=5
        else:
            if pos+2>len(data): raise ValueError('Truncated LZX frame')
            outsize=32768;n=int.from_bytes(data[pos:pos+2],'big');pos+=2
        if not n: break
        if pos+n>len(data):raise ValueError('Frame length exceeds stream')
        raw.extend(data[pos:pos+n]);pos+=n;declared+=outsize
    if declared!=size:raise ValueError(f'LZX declared size {declared} != ZIP {size}')
    buf=ctypes.create_string_buffer(bytes(raw));out=ctypes.create_string_buffer(size)
    # Xbox XMem normally uses a 128 KiB window. CRC is the final authority.
    errors=[]
    for bits in [17,15,16,18,19,20,21]:
        status=_dll.decode_lzx(buf,len(raw),out,size,bits)
        if status==0 and zlib.crc32(out.raw)==crc:return out.raw
        errors.append((bits,status))
    raise ValueError(f'LZX decode/CRC failed {errors}')
def read(z,member):
    info=z.getinfo(member) if isinstance(member,str) else member
    if info.compress_type!=21:return z.read(info)
    f=z.fp;f.seek(info.header_offset);h=f.read(30)
    if h[:4]!=b'PK\x03\x04':raise ValueError('Not a ZIP local header')
    namesize,extrasize=struct.unpack_from('<HH',h,26)
    f.seek(namesize+extrasize,1);data=f.read(info.compress_size)
    return decode21(data,info.file_size,info.CRC)
