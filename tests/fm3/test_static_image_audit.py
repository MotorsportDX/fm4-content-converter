"""Bounds and identity checks for address provenance, without guest execution."""
from pathlib import Path
import struct
import tempfile
import unittest

from fm4_converter.fm3 import static_image_audit as a


def fixtures():
    xex=bytearray(128)
    xex[:4]=b"XEX2"
    struct.pack_into(">I",xex,20,2)
    struct.pack_into(">IIII",xex,24,0x10201,0x82000000,0x10100,0x82000200)
    pe=bytearray(0x400)
    pe[:2]=b"MZ"
    struct.pack_into("<I",pe,0x3c,0x80)
    pe[0x80:0x84]=b"PE\0\0"
    struct.pack_into("<H",pe,0x86,1)
    struct.pack_into("<H",pe,0x94,0xe0)
    struct.pack_into("<H",pe,0x98,0x10b)
    struct.pack_into("<I",pe,0xa8,0x200)
    struct.pack_into("<I",pe,0xb4,0x82000000)
    struct.pack_into("<I",pe,0xd0,0x400)
    sec=0x178
    pe[sec:sec+5]=b".text"
    struct.pack_into("<II",pe,sec+8,0x100,0x200)
    struct.pack_into("<I",pe,sec+36,0x20000000)
    return xex,pe


class StaticImageAuditTests(unittest.TestCase):
    def test_bounds_and_unsupported_format_fail(self):
        xex,pe=fixtures()
        for data in (xex[:26],b"NOPE",xex[:20]):
            with self.assertRaises(ValueError):
                a.xex_metadata(data)
        for data in (pe[:100],b"NOPE",pe[:0x180]):
            with self.assertRaises(ValueError):
                a.pe_metadata(data)

    def test_image_range_and_base_are_read_from_headers(self):
        xex,pe=fixtures()
        self.assertEqual(a.xex_metadata(xex)["image_base"],0x82000000)
        self.assertEqual(a.pe_metadata(pe)["sections"][0]["start"],0x82000200)
        struct.pack_into("<I",pe,0x180,0x10000)
        with self.assertRaises(ValueError):
            a.pe_metadata(pe)

    def test_mismatched_source_and_decoder_metadata_fail(self):
        xex,pe=fixtures()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"source.xex").write_bytes(xex)
            (root/"image.bin").write_bytes(pe)
            (root/"sections.tsv").write_text(".text\t2181038592\t256\t2\n")
            args=(root/"source.xex",root/"image.bin",root/"sections.tsv")
            self.assertEqual(a.audit(*args)["pe"]["entry_point"],0x82000200)
            with self.assertRaises(ValueError):
                a.audit(*args,expected_sha="0"*64)
            struct.pack_into(">I",xex,28,0x81000000)
            (root/"source.xex").write_bytes(xex)
            with self.assertRaises(ValueError):
                a.audit(*args)

    def test_unavailable_noncode_tail_is_explicit_not_fabricated(self):
        _,pe=fixtures()
        pe[0x178:0x180]=b".reloc\0\0"
        struct.pack_into("<I",pe,0x180,0x1000)
        struct.pack_into("<I",pe,0x19c,0)
        result=a.pe_metadata(pe)
        self.assertEqual(result["incomplete_sections"][0]["name"],".reloc")
        self.assertEqual(result["incomplete_sections"][0]["unavailable_tail_bytes"],0xe00)


if __name__=="__main__":
    unittest.main()
