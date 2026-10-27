"""Regressions for native localized name readers and the two-slot UI atlas.

Fixtures are read from the user's local games; none are embedded in source.
"""
import io
from pathlib import Path
import struct
import unittest
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from PIL import Image, ImageDraw
import converter as c
import integration as integration
import ui_names as names
import ui_thumbnail as thumbs
from texture_audit import Texture


class BoundaryTests(unittest.TestCase):
    def test_literal_zero_overflow_and_malformed_name_keys_rejected(self):
        for value in ("Cobalt SS (FM3)", "_&0", "_&4294967296", "_&-1", "_&1junk", "_&65535", None):
            with self.subTest(value=value), self.assertRaises(names.NameError):
                names.reference(value)
        self.assertEqual(names.reference("_&3444127938"),0xCD4938C2)

    def test_white_car_details_survive_matte_removal(self):
        im = Image.new("RGBA",(160,80),"white")
        d = ImageDraw.Draw(im)
        d.rectangle((20,15,140,70),fill=(20,50,100,255))
        d.rectangle((45,25,65,40),fill="white")
        d.ellipse((30,50,45,65),fill="white")
        # A broad white ground gap below the body is distinct from wheel detail.
        d.rectangle((65,62,125,68),fill="white")
        out, report = thumbs.remove_white_matte(im)
        self.assertEqual(out.getpixel((0,0)),(0,0,0,0))
        self.assertEqual(out.getpixel((55,33)),(255,255,255,255))
        self.assertEqual(out.getpixel((37,57)),(255,255,255,255))
        self.assertEqual(out.getpixel((95,65)),(0,0,0,0))
        self.assertEqual(report["enclosed_ground_matte_islands_removed"],1)

    def test_unknown_matte_is_not_silently_keyed_out(self):
        with self.assertRaisesRegex(thumbs.ThumbnailError,"white border"):
            thumbs.remove_white_matte(Image.new("RGBA",(160,80),"blue"))
        with self.assertRaisesRegex(thumbs.ThumbnailError,"empty"):
            thumbs.remove_white_matte(Image.new("RGBA",(160,80),"white"))

    def test_only_explicit_existing_zip_mount_can_be_replaced(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream,"w") as z:
            z.writestr("Data_Car.str",b"test")
        path = Path("Media/StringTables/EN.zip")
        original = b'<ZipFiles version="3"><Zip version="1" path="game:\\media\\stringtables\\en.zip" priority="37" dirstart="1" dirsize="2" direntries="3"/><Zip path="game:\\keep.zip" priority="12"/></ZipFiles>'
        with self.assertRaisesRegex(c.MappingError,"already exists"):
            integration.extend_zip_manifest(original,{path:stream.getvalue()})
        updated = ET.fromstring(integration.extend_zip_manifest(original,{path:stream.getvalue()},[path]))
        self.assertEqual(len(updated),2)
        self.assertEqual(updated[0].get("priority"),"37")
        self.assertEqual(updated[0].get("direntries"),"1")
        self.assertEqual(updated[1].attrib,ET.fromstring(original)[1].attrib)
        with self.assertRaisesRegex(c.MappingError,"existing mount"):
            integration.extend_zip_manifest(b'<ZipFiles version="3"/>',{path:stream.getvalue()},[path])


@unittest.skipUnless(c.FM3_DEFAULT.exists() and c.FM4_DEFAULT.exists(),"Local games required")
class LocalUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = {}
        for p in (c.FM4_DEFAULT.parents[1]/"StringTables").glob("*.zip"):
            with zipfile.ZipFile(p) as z:
                cls.tables[p.stem.upper()] = integration.archive_read(z,"Data_Car.str")
        with zipfile.ZipFile(c.FM3_DEFAULT.parents[1]/"StringTables/EN.zip") as z:
            cls.source_table = names.StringTable(integration.archive_read(z,"Data_Car.str"))
        with zipfile.ZipFile(c.FM3_DEFAULT.parents[1]/"UI/Textures.zip") as z:
            cls.source_thumb = integration.archive_read(z,"Thumbnails/Thumbnail_305.xds")
        with zipfile.ZipFile(c.FM4_DEFAULT.parents[1]/"UI/Textures.zip") as z:
            cls.template = integration.archive_read(z,"Thumbnails/Thumbnail_1305.xds")
        cls.additions = [(0xCD49B0CD,"IDS_DisplayName_305","Cobalt SS (FM3)"),
                         (0xCD4938C2,"IDS_ModelShort_305","Cobalt SS (FM3)")]

    def test_all_language_tables_preserve_native_entries_and_ordinals(self):
        self.assertEqual(len(self.tables),18)
        for language, raw in self.tables.items():
            with self.subTest(language=language):
                before = names.StringTable(raw)
                self.assertEqual(before.add([]),raw)
                encoded = before.add(self.additions)
                after = names.StringTable(encoded)
                self.assertEqual(len(after.texts),len(before.texts)+2)
                self.assertEqual(after.order[:len(before.order)],before.order)
                self.assertEqual(after.sections[2],before.sections[2])
                for key in before.texts:
                    self.assertEqual((after.texts[key],after.names[key]),(before.texts[key],before.names[key]))
                # Independent address arithmetic used by the native lookup:
                # sorted 16-bit key + 32-bit UTF16-unit offset, followed by text.
                offset = struct.unpack_from(">I",encoded,20)[0]
                count = struct.unpack_from(">I",encoded,offset+4)[0]
                text_base = offset+8+(count+1)*6
                for full_key,symbol,label in self.additions:
                    self.assertEqual(self.source_table.names[full_key & 65535],symbol)
                    lo,hi = 0,count
                    while lo < hi:
                        mid = (lo+hi)//2
                        key = struct.unpack_from(">H",encoded,offset+8+mid*6)[0]
                        if key < (full_key & 65535):lo=mid+1
                        else:hi=mid
                    key,pos = struct.unpack_from(">HI",encoded,offset+8+lo*6)
                    self.assertEqual(key,full_key & 65535)
                    expected = label.encode("utf-16-be")+b"\0\0"
                    self.assertEqual(encoded[text_base+pos*2:text_base+pos*2+len(expected)],expected)

    def test_existing_localization_identity_cannot_be_overwritten(self):
        table = names.StringTable(self.tables["EN"])
        key = next(iter(table.texts))
        with self.assertRaisesRegex(names.NameError,"collision"):
            table.add([(0xCD490000|key,"new_name","replacement")])
        with self.assertRaisesRegex(names.NameError,"collision"):
            table.add([(0xCD4938C2,table.names[key],"replacement")])

    def test_truncation_offsets_count_and_index_corruption_rejected(self):
        raw = self.tables["EN"]
        variants = [raw[:20],raw[:-1]]
        for offset,value in [(20,0xFFFFFFFF),(40,0xFFFFFFFF),(46,0xFFFFFFFF)]:
            modified=bytearray(raw);struct.pack_into(">I",modified,offset,value);variants.append(bytes(modified))
        section=struct.unpack_from(">I",raw,24)[0]
        modified=bytearray(raw);struct.pack_into(">H",modified,section+10,0);variants.append(bytes(modified))
        for variant in variants:
            with self.assertRaises(names.NameError):names.StringTable(variant)

    def test_cobalt_atlas_has_two_visible_upright_views_and_no_white_background(self):
        encoded,report = thumbs.convert(self.source_thumb,self.template)
        texture = Texture(encoded)
        self.assertEqual((texture.width,texture.height,texture.levels),(768,288,1))
        self.assertEqual(encoded[:52],self.template[:52])
        raw = np.array(thumbs.decode(encoded))
        self.assertTrue((raw[:,:,:3] <= raw[:,:,3:4]).all())
        self.assertTrue((raw[raw[:,:,3]==0,:3]==0).all())
        decoded = thumbs.decode(encoded,True)
        views = [decoded.crop((0,0,608,288)),decoded.crop((608,0,768,288)).transpose(Image.Transpose.ROTATE_270)]
        for view in views:
            self.assertEqual(view.getpixel((0,0)),(0,0,0,0))
            x0,y0,x1,y1 = view.getbbox()
            self.assertGreater(x1-x0,view.width*0.7)
            self.assertLess(y1,view.height)
            # Roof is above the centre; tyres/ground extend near the bottom.
            self.assertGreater(y1,view.height*0.9)
        self.assertGreater(report["transparent_background_pixels"],50000)
        self.assertEqual(report["enclosed_ground_matte_islands_removed"],2)

    def test_wrong_native_header_or_source_layout_rejected(self):
        modified=bytearray(self.template);modified[35]=0x94
        with self.assertRaises(thumbs.ThumbnailError):
            thumbs.encode(Image.new("RGBA",(768,288)),bytes(modified))
        with self.assertRaises(thumbs.ThumbnailError):
            thumbs.convert(self.template,self.template)


if __name__ == "__main__":
    unittest.main()
