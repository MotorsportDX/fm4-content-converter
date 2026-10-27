"""CRC-checked CPU fallback for local XMem streams unsupported by libmspack.

The proprietary decoder is supplied locally, never bundled into a package.
No graphics or game entry point is called.
"""
import ctypes
import hashlib
import os
from pathlib import Path
import struct
import zlib


DECODER_SHA256 = "2bccb9b52a82ec400c8451e22451a95fb6fbb8472ab65a03a2bd511a4353a35a"
DEFAULT_DECODER = Path(__file__).resolve().parents[2]/(
    "outputs/fm-car-converter/import-v1/references/ForzaTechStudio/"
    "ForzaTechStudio/Native/xcompress64.dll")


def decoder_path():
    return Path(os.environ.get("FM_XCOMPRESS_DLL", str(DEFAULT_DECODER))).resolve()


def read_xmem(archive, info):
    if info.compress_type != 21 or not 0 < info.file_size <= 128*1024*1024:
        raise ValueError("Unsupported method or oversized XMem entry")
    decoder = decoder_path()
    if hashlib.sha256(decoder.read_bytes()).hexdigest() != DECODER_SHA256:
        raise ValueError("Unreviewed XMem decoder")
    archive.fp.seek(info.header_offset)
    header = archive.fp.read(30)
    if len(header) != 30 or header[:4] != b"PK\x03\x04":
        raise ValueError("Invalid XMem ZIP local header")
    name_size, extra_size = struct.unpack_from("<HH", header, 26)
    archive.fp.seek(name_size+extra_size, 1)
    source = archive.fp.read(info.compress_size)
    if len(source) != info.compress_size:
        raise ValueError("Truncated XMem ZIP entry")
    dll = ctypes.CDLL(str(decoder))
    pointer = ctypes.c_void_p
    integer = ctypes.c_uint32
    dll.XMemCreateDecompressionContext.argtypes = [integer, pointer, integer, ctypes.POINTER(pointer)]
    dll.XMemCreateDecompressionContext.restype = ctypes.c_int32
    dll.XMemDecompress.argtypes = [pointer, pointer, ctypes.POINTER(integer), pointer, integer]
    dll.XMemDecompress.restype = ctypes.c_int32
    dll.XMemDestroyDecompressionContext.argtypes = [pointer]
    dll.XMemDestroyDecompressionContext.restype = None
    context = pointer()
    if dll.XMemCreateDecompressionContext(1, None, 0, ctypes.byref(context)) != 0:
        raise ValueError("Cannot create XMem decompression context")
    try:
        output = ctypes.create_string_buffer(info.file_size)
        size = integer(info.file_size)
        compressed = ctypes.create_string_buffer(source)
        status = dll.XMemDecompress(context, output, ctypes.byref(size), compressed, len(source))
        if status != 0 or size.value != info.file_size or zlib.crc32(output.raw) != info.CRC:
            raise ValueError(f"XMem output size/CRC check failed: {info.filename}")
        return output.raw
    finally:
        dll.XMemDestroyDecompressionContext(context)
