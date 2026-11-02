"""Pembaca kontainer CAFF (`CAFF21.11.05.0034`) berkas track `bin.zip`.

Layout dari FM4-PC docs/analysis/texture-replacement.md ("The CAFF container"); semua
big-endian. Header: jumlah nama N (+0x18), jumlah chunk M (+0x1c), offset tabel nama di
`.data` (+0x44), ukuran header (+0x48, `.data` mulai di sini), section 0x28 byte mulai
+0x50 (nama 8 byte, align log2 +0x08, ukuran +0x10). Tabel nama: ukuran blob, N offset,
nama; lalu satu word nol dan M entri chunk 14 byte (id, offset, ukuran, section 1=.data
2=.gpu, align log2).

Dijalankan langsung: ringkasan jenis record (tag + string versi) per kontainer, untuk
membandingkan `bin.zip` FM3 dan FM4 satu track.

    python research/tracks-2026-11-02/caff.py <bin.zip> [<bin.zip> ...]
"""
from pathlib import Path
import collections, re, struct, sys, zipfile

from fm4_converter.fm3.integration import archive_read

MAGIC = b'CAFF21.11.05.0034'


class Caff:
    def __init__(self, data):
        if not data.startswith(MAGIC):
            raise ValueError('Not a CAFF21.11.05.0034 container')
        self.data = data
        n_names, n_chunks = struct.unpack_from('>II', data, 0x18)
        names_at, header = struct.unpack_from('>II', data, 0x44)
        self.sections = []
        at = 0x50
        while len(self.sections) < 8 and at + 0x28 <= header:
            name = data[at:at+8].rstrip(b'\0')
            if not name.startswith(b'.'):
                break
            self.sections.append((name.decode(), data[at+8], struct.unpack_from('>I', data, at+0x10)[0]))
            at += 0x28
        self.header = header
        base = {}
        cursor = header
        for name, align, size in self.sections:
            base[name] = cursor
            cursor += size
        self.base = base
        blob = header + names_at
        self.names = []
        offs = struct.unpack_from(f'>{n_names}I', data, blob+4)
        start = blob + 4 + 4*n_names
        for o in offs:
            end = data.index(b'\0', start+o)
            self.names.append(data[start+o:end].decode('latin1'))
        blob_size = struct.unpack_from('>I', data, blob)[0]  # name bytes only
        chunk_at = start + blob_size + 4
        self.chunks = []
        for i in range(n_chunks):
            cid, off, size = struct.unpack_from('>III', data, chunk_at + 14*i)
            section, align = data[chunk_at + 14*i + 12], data[chunk_at + 14*i + 13]
            self.chunks.append((cid, off, size, section, align))

    def payload(self, chunk):
        cid, off, size, section, align = chunk
        name = self.sections[section-1][0]
        start = self.base[name] + off
        return self.data[start:start+size]

    def records(self):
        """(id, tag, version) of every .data chunk that starts with an ASCII tag."""
        out = []
        for chunk in self.chunks:
            if chunk[3] != 1:
                continue
            body = self.payload(chunk)
            m = re.match(rb'([A-Za-z_][A-Za-z0-9_ ]{2,30})\0', body)
            ver = re.search(rb'\d\d\.\d\d\.\d\d\.\d{4}', body[:64])
            out.append((chunk[0], m.group(1).decode() if m else body[:8].hex(),
                        ver.group(0).decode() if ver else ''))
        return out


def summary(path):
    kinds = collections.Counter()
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if not n.lower().endswith('.bin') or n.lower().endswith('.rmb.bin'):
                continue
            data = archive_read(z, n)
            if not data.startswith(MAGIC):
                kinds[('non-CAFF .bin', data[:4].hex(), '')] += 1
                continue
            c = Caff(data)
            role = 'stx' if n.lower().endswith('.stx.bin') else '_0x'
            for _, tag, ver in c.records():
                kinds[(role, tag, ver)] += 1
    return kinds


if __name__ == '__main__':
    results = [summary(p) for p in sys.argv[1:]]
    keys = sorted(set().union(*results))
    for k in keys:
        print(' | '.join(f'{r.get(k, 0):6}' for r in results), '|', *k)
