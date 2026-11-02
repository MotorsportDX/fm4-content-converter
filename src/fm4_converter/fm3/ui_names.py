"""CPU-only, bounded LSB2 car-name repair using the native localization path.

FM4 CRecordSet slot 124 (8284D0B0) calls 829AC560, which parses a decimal
reference after its first two bytes. A literal ModelShort therefore becomes
key zero. Keep the source keys and install their actual string-table entries.
No executable patch or game process is involved.
"""
import io
from pathlib import Path
import re
import struct
import zipfile


class NameError(ValueError):
    pass


def reference(value):
    if not isinstance(value, str) or not re.fullmatch(r"_&[0-9]+", value):
        raise NameError("Expected an _&decimal localization reference")
    key = int(value[2:])
    if not 0 < key < 2**32 or key & 65535 == 65535:
        raise NameError("Unsupported localization key")
    return key


class StringTable:
    """Retail LSB2 big-endian text, symbolic-name and ordinal tables.

The optional third section is opaque metadata and is preserved byte-for-byte.
Offsets in each section are relative to that section, not the whole file.
"""
    def __init__(self, data):
        self.data = data
        if len(data) < 36 or data[:20] != b"LSB2\x01\0\0\0\x02\0\0\0\0\0\0$\0\0\0\x04":
            raise NameError("Unsupported LSB2 header")
        offsets = struct.unpack_from(">4I", data, 20)
        self.sections = []
        cursor = 36
        for number, at in enumerate(offsets):
            if at == 0 and number == 2:
                self.sections.append(b"")
                continue
            if at != cursor or at + 8 > len(data):
                raise NameError("Invalid LSB2 section offset")
            size = struct.unpack_from(">I", data, at)[0]
            if size < 8 or at + size > len(data):
                raise NameError("Invalid LSB2 section length")
            self.sections.append(data[at:at+size])
            cursor += size
        if cursor != len(data):
            raise NameError("Trailing LSB2 data")
        text, names, _, ordinals = self.sections
        n = struct.unpack_from(">I", text, 4)[0]
        if n == 0 or n >= 65535 or 8 + (n+1)*6 > len(text):
            raise NameError("Invalid LSB2 text count")
        records = [struct.unpack_from(">HI", text, 8+j*6) for j in range(n+1)]
        keys = [r[0] for r in records]
        if keys != sorted(set(keys)) or keys[-1] != 65535:
            raise NameError("Unsorted or duplicate LSB2 text keys")
        blob = text[8+(n+1)*6:]
        if (records[0][1] != 0 or records[-1][1]*2+2 != len(blob)
                or blob[-2:] != b"\0\0"):
            raise NameError("Invalid LSB2 text sentinel")
        self.texts = {}
        for (key, start), (_, end) in zip(records, records[1:]):
            raw = blob[start*2:end*2]
            if end <= start or end*2 > len(blob) or not raw.endswith(b"\0\0"):
                raise NameError("Invalid LSB2 string bounds")
            try:
                value = raw[:-2].decode("utf-16-be")
            except UnicodeError as error:
                raise NameError("Invalid UTF16 string") from error
            if "\0" in value:
                raise NameError("Embedded string terminator")
            self.texts[key] = value
        if struct.unpack_from(">I", names, 4)[0] != n or 8+n*8 > len(names):
            raise NameError("Invalid LSB2 name count")
        names_blob = names[8+n*8:]
        self.names, indexes = {}, {}
        name_records = [struct.unpack_from(">HHI", names, 8+j*8) for j in range(n)]
        if [r[0] for r in name_records] != keys[:-1]:
            raise NameError("Symbolic-name keys disagree with text")
        for key, index, at in name_records:
            end = names_blob.find(b"\0", at)
            if not 1 <= index <= n or index in indexes or end < at:
                raise NameError("Invalid LSB2 symbolic-name reference")
            try:
                name = names_blob[at:end].decode("ascii")
            except UnicodeError as error:
                raise NameError("Invalid symbolic-name encoding") from error
            if not name or name in self.names.values():
                raise NameError("Empty or duplicate symbolic name")
            self.names[key], indexes[index] = name, key
        if len(ordinals) != 8+2*n or struct.unpack_from(">I", ordinals, 4)[0] != n:
            raise NameError("Invalid LSB2 ordinal count")
        self.order = list(struct.unpack_from(">"+str(n)+"H", ordinals, 8))
        if self.order != [indexes[j] for j in range(1,n+1)]:
            raise NameError("LSB2 ordinal/name index mismatch")

    def add(self, additions):
        """Append new identities; reject collisions instead of replacing cars."""
        if not additions:
            return self.data
        texts, names, order = dict(self.texts), dict(self.names), list(self.order)
        for full_key, name, value in additions:
            key = full_key & 65535
            if key == 65535 or key in texts or name in names.values():
                raise NameError("Localization identity collision")
            if not value.strip() or "\0" in value or not name.isascii():
                raise NameError("Invalid new name")
            texts[key], names[key] = value, name
            order.append(key)
        if len(order) >= 65535:
            raise NameError("LSB2 ordinal overflow")
        def section(body):
            return struct.pack(">II", len(body)+8, len(order))+body
        blob, records = bytearray(), bytearray()
        for key in sorted(texts):
            records += struct.pack(">HI", key, len(blob)//2)
            blob += texts[key].encode("utf-16-be")+b"\0\0"
        records += struct.pack(">HI", 65535, len(blob)//2)
        text_section = section(records+blob+b"\0\0")
        blob, positions = bytearray(), {}
        for key in order:
            positions[key] = len(blob)
            blob += names[key].encode("ascii")+b"\0"
        indexes = {key:j+1 for j,key in enumerate(order)}
        records = b"".join(struct.pack(">HHI",key,indexes[key],positions[key]) for key in sorted(names))
        sections = [text_section, section(records+blob), self.sections[2],
                    section(struct.pack(">"+str(len(order))+"H",*order))]
        header, result = bytearray(self.data[:36]), bytearray()
        for j, part in enumerate(sections):
            struct.pack_into(">I",header,20+j*4,36+len(result) if part else 0)
            result += part
        encoded = bytes(header+result)
        checked = StringTable(encoded)
        if (checked.texts != texts or checked.names != names or checked.order != order
                or checked.sections[2] != self.sections[2]):
            raise NameError("LSB2 output roundtrip failed")
        return encoded


def plan(source_car, label):
    result = {}
    for field in ("DisplayName", "ModelShort"):
        key = reference(source_car[field])
        result[field] = {"reference":source_car[field], "key":key,
                         "symbol":f"IDS_{field}_{source_car['Id']}",
                         "text":label[field] if isinstance(label, dict) else label}
    if len({v["key"] for v in result.values()}) != 2:
        raise NameError("Car name keys must be distinct")
    return result


# The mount resolver serves each guest path from the highest-priority ZIP. Disc
# 2 and every DLC pack ship a cumulative <lang>/Data_Car.str (priority 151 to
# 25039 on the test profile) over the disc's (80), so names added to the disc
# table never show (Cobalt v7 in Motorsport DX, 1 November 2026). A ZIP named
# `media\stringtables.zip` mounts its `<lang>/` members at media\stringtables\
# like DLCZips\StringTables_pri_N.zip; above the winning table it overrides
# only Data_Car.str and leaves every other table to its current provider.
OVERRIDE = Path("Media/stringtables.zip")
_PRIORITY = re.compile(r"_pri_(\d+)\.zip$", re.IGNORECASE)


def winning_tables(target_root, content_root, archive_read, sha):
    """Per language, the Data_Car.str the game reads now, with its priority."""
    import xml.etree.ElementTree as ET
    mounts = {z.attrib["path"].casefold():int(z.attrib["priority"])
              for z in ET.fromstring((target_root/"zipmanifest.xml").read_bytes()).findall("Zip")}
    inputs, tables = {}, {}
    for path in sorted((target_root/"StringTables").glob("*.zip")):
        priority = mounts.get(("game:\\media\\stringtables\\"+path.name).casefold())
        if priority is None:
            raise NameError(f"Unmounted language archive: {path.name}")
        inputs[str(path)] = sha(path)
        with zipfile.ZipFile(path) as z:
            matches = [m for m in z.namelist() if m.casefold()=="data_car.str"]
            if len(matches)!=1:
                raise NameError("Missing or ambiguous native car string table")
            tables[path.stem.casefold()] = (priority,path.stem,str(path),archive_read(z,matches[0]))
    packs = sorted(Path(content_root).glob("*/Media/DLCZips/StringTables_pri_*.zip")) if content_root else []
    for path in packs:
        priority = int(_PRIORITY.search(path.name).group(1))
        inputs[str(path)] = sha(path)
        with zipfile.ZipFile(path) as z:
            for member in z.namelist():
                language, _, name = member.replace("\\","/").partition("/")
                if name.casefold()!="data_car.str":
                    continue
                current = tables.get(language.casefold())
                if current and current[0]==priority:
                    raise NameError(f"Two {language} car tables share priority {priority}")
                if not current or priority>current[0]:
                    tables[language.casefold()] = (priority,language,f"{path}:{member}",archive_read(z,member))
    if "en" not in tables:
        raise NameError("No native English car string table")
    return tables, inputs


def rekey(bindings, taken):
    """Move bindings whose key a target table already uses to the highest free key.

    FM4 DLC packs reuse some FM3 Data_Car keys for other cars (FM3 Aston Martin
    DBR9's DisplayName is FM4's Lotus Eleven); `taken` holds every key of every
    winning language table plus keys already handed out, and is updated."""
    moved = {}
    for field, row in bindings.items():
        key = reference(row["reference"])
        if key & 65535 not in taken:
            taken.add(key & 65535)
            continue
        free = next((k for k in range(65534, 0, -1) if k not in taken), None)
        if free is None:
            raise NameError("No free Data_Car string key")
        taken.add(free)
        row["source_reference"], row["reference"] = row["reference"], f"_&{(key & ~65535) | free}"
        row["key"] = reference(row["reference"])
        moved[field] = row["reference"]
    return moved


def build_archives(source_root, target_root, bindings, archive_read, sha, content_root=None):
    source_path = source_root/"StringTables/EN.zip"
    inputs = {str(source_path):sha(source_path)}
    with zipfile.ZipFile(source_path) as z:
        source = StringTable(archive_read(z,"Data_Car.str"))
    additions = []
    for row in bindings.values():
        # A rekeyed binding (see rekey) is still checked against its FM3 key.
        key = reference(row.get("source_reference", row["reference"]))
        if key >> 16 != 0xCD49 or source.names.get(key & 65535) != row["symbol"]:
            raise NameError("Source key does not identify the expected Data_Car symbol")
        additions.append((reference(row["reference"]),row["symbol"],row["text"]))
    tables, found = winning_tables(target_root,content_root,archive_read,sha)
    inputs.update(found)
    stream, reports = io.BytesIO(), []
    with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_STORED) as output:
        for _,(priority,language,origin,data) in sorted(tables.items()):
            table = StringTable(data)
            encoded = table.add(additions)
            checked = StringTable(encoded)
            if any(checked.texts[k]!=v for k,v in table.texts.items()):
                raise NameError("Existing localized text changed")
            output.writestr(zipfile.ZipInfo(f"{language}/Data_Car.str",(1980,1,1,0,0,0)),encoded)
            reports.append({"language":language,"winning_table":origin,"winning_priority":priority,
                            "original_names_preserved":len(table.texts),"new_entries":bindings,
                            "optional_metadata_preserved":True})
    priority = max(r["winning_priority"] for r in reports)+1
    return {OVERRIDE:stream.getvalue()}, {
        "passed":True,"cpu_only":True,"runtime_tested":False,"inputs":inputs,"languages":reports,
        "mount":{"path":"game:\\media\\stringtables.zip","priority":priority},
        "content_root":str(content_root) if content_root else None,
        "scope":("Per-file Data_Car.str override above the winning table of the given disc and "
                 "content set; a pack installed later with a higher priority hides these names again")}
