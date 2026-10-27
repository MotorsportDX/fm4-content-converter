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
                         "symbol":f"IDS_{field}_{source_car['Id']}", "text":label}
    if len({v["key"] for v in result.values()}) != 2:
        raise NameError("Car name keys must be distinct")
    return result


def build_archives(source_root, target_root, bindings, archive_read, sha):
    source_path = source_root/"StringTables/EN.zip"
    inputs = {str(source_path):sha(source_path)}
    with zipfile.ZipFile(source_path) as z:
        source = StringTable(archive_read(z,"Data_Car.str"))
    additions = []
    for row in bindings.values():
        key = reference(row["reference"])
        if key >> 16 != 0xCD49 or source.names.get(key & 65535) != row["symbol"]:
            raise NameError("Source key does not identify the expected Data_Car symbol")
        additions.append((key,row["symbol"],row["text"]))
    archives, reports = {}, []
    for path in sorted((target_root/"StringTables").glob("*.zip")):
        inputs[str(path)] = sha(path)
        stream = io.BytesIO()
        with zipfile.ZipFile(path) as original, zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_STORED) as output:
            members = original.infolist()
            if len({m.filename.casefold() for m in members}) != len(members):
                raise NameError("Duplicate string archive member")
            matches = [m.filename for m in members if m.filename.casefold()=="data_car.str"]
            if len(matches)!=1:
                raise NameError("Missing or ambiguous native car string table")
            preserved = 0
            for member in members:
                data = archive_read(original, member)
                if member.filename == matches[0]:
                    table = StringTable(data)
                    data = table.add(additions)
                    checked = StringTable(data)
                    if any(checked.texts[k]!=v for k,v in table.texts.items()):
                        raise NameError("Existing localized text changed")
                else:
                    preserved += 1
                info = zipfile.ZipInfo(member.filename,(1980,1,1,0,0,0))
                output.writestr(info,data)
        archives[Path("Media/StringTables")/path.name] = stream.getvalue()
        reports.append({"language":path.stem,"original_names_preserved":len(table.texts),
                        "other_members_preserved":preserved,"new_entries":bindings,
                        "optional_metadata_preserved":True})
    if not reports or not any(r["language"].upper()=="EN" for r in reports):
        raise NameError("No native language archives")
    return archives, {"passed":True,"cpu_only":True,"runtime_tested":False,
                      "inputs":inputs,"languages":reports,
                      "scope":"LSB2 references and preservation; runtime display still requires a game test"}
