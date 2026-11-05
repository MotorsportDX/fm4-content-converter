"""Read-only reader for Xbox 360 disc images (XDVDFS / "XISO").

A Redump image starts with the video partition; the game partition follows at a fixed
offset that depends on the disc layout (XGD1/XGD2/XGD3). A rebuilt image ("xiso") starts
with the game partition. Sector 32 of the game partition holds the volume descriptor:
the magic "MICROSOFT*XBOX*MEDIA", then the root directory's sector and size.

A directory is a binary tree of entries, each 4-byte aligned and never crossing a
sector: left and right subtree offsets (in dwords), start sector, size, attributes,
name length and the name. An offset of 0xFFFF ends a branch.
"""
from pathlib import Path, PurePosixPath
import struct

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"
# Game partition offsets: rebuilt image, XGD2 (most 360 games), XGD3, XGD1 (original Xbox).
PARTITIONS = (0, 0xFD90000, 0x2080000, 0x18300000)
DIRECTORY = 0x10
END = 0xFFFF


class FormatError(ValueError):
    pass


def is_iso(path):
    return Path(path).is_file() and Path(path).suffix.casefold() == ".iso"


class XISO:
    """Files of an Xbox 360 disc image by their disc path, e.g. Media/DB/gamedb.slt."""

    def __init__(self, path):
        self.path = Path(path)
        self.file = self.path.open("rb")
        try:
            self.base = self._partition()
            self.file.seek(self.base + 32*SECTOR + len(MAGIC))
            root_sector, root_size = struct.unpack("<II", self.file.read(8))
            self.entries = {}
            self._walk(root_sector, root_size, PurePosixPath())
        except BaseException:
            self.file.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.file.close()

    def _partition(self):
        size = self.path.stat().st_size
        for base in PARTITIONS:
            if base + 33*SECTOR > size:
                continue
            self.file.seek(base + 32*SECTOR)
            head = self.file.read(SECTOR)
            if head.startswith(MAGIC) and head[0x7EC:0x7EC+len(MAGIC)] == MAGIC:
                return base
        raise FormatError(f"Not an Xbox 360 disc image: {self.path}")

    def _walk(self, sector, size, parent):
        if size == 0:
            return
        self.file.seek(self.base + sector*SECTOR)
        table = self.file.read(size)
        if len(table) != size:
            raise FormatError("Directory table runs past the end of the image")
        pending, seen = [0], set()
        while pending:
            offset = pending.pop()
            if offset in seen or offset + 14 > size:
                continue
            seen.add(offset)
            left, right, start, length, attributes, name_length = struct.unpack_from("<HHIIBB", table, offset)
            if left == END and right == END and start == 0xFFFFFFFF:
                continue   # sector padding
            name = table[offset+14:offset+14+name_length].decode("latin-1")
            if not name or name in (".", "..") or "/" in name or "\\" in name:
                raise FormatError(f"Unsafe directory entry {name!r} in {parent}")
            path = parent/name
            if path.as_posix().casefold() in self.entries:
                raise FormatError(f"Duplicate entry {path}")
            directory = bool(attributes & DIRECTORY)
            self.entries[path.as_posix().casefold()] = (path, start, length, directory)
            if directory:
                self._walk(start, length, path)
            for child in (left, right):
                if child not in (0, END):
                    pending.append(child*4)

    def files(self, prefix=""):
        """Disc paths (with their case) of the files under `prefix`."""
        key = PurePosixPath(prefix).as_posix().casefold().rstrip("/") if prefix else ""
        return sorted(path for name, (path, _, _, directory) in self.entries.items()
                      if not directory and (not key or key == "." or name == key or name.startswith(key+"/")))

    def exists(self, path):
        return PurePosixPath(path).as_posix().casefold() in self.entries

    def size(self, path):
        return self._entry(path)[2]

    def _entry(self, path):
        found = self.entries.get(PurePosixPath(path).as_posix().casefold())
        if found is None or found[3]:
            raise FileNotFoundError(f"{path} is not a file in {self.path}")
        return found

    def read(self, path):
        _, start, length, _ = self._entry(path)
        self.file.seek(self.base + start*SECTOR)
        data = self.file.read(length)
        if len(data) != length:
            raise FormatError(f"{path} runs past the end of the image")
        return data

    def extract(self, prefixes, out, progress=None):
        """Copy the files under each prefix to `out`, keeping disc paths. Files already there with
        the right size are kept, so an interrupted extraction resumes. Returns the bytes copied."""
        out = Path(out)
        selected = sorted({p for prefix in prefixes for p in self.files(prefix)})
        total = sum(self.size(p) for p in selected)
        done = copied = 0
        for path in selected:
            _, start, length, _ = self._entry(path)
            target = out.joinpath(*path.parts)
            if not (target.is_file() and target.stat().st_size == length):
                target.parent.mkdir(parents=True, exist_ok=True)
                partial = target.with_name(target.name + ".partial")
                self.file.seek(self.base + start*SECTOR)
                with partial.open("wb") as f:
                    remaining = length
                    while remaining:
                        chunk = self.file.read(min(remaining, 8 << 20))
                        if not chunk:
                            raise FormatError(f"{path} runs past the end of the image")
                        f.write(chunk)
                        remaining -= len(chunk)
                partial.replace(target)
                copied += length
            done += length
            if progress:
                progress(path.as_posix(), done, total)
        return copied
