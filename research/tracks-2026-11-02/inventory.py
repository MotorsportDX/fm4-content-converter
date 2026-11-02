"""Inventaris track FM3 -> FM4: layout, sumber aset, benturan ID dan header format.

Hanya membaca: SQLite dibuka mode=ro, ZIP/STFS dibaca lewat pembaca arsip project.
Hasil ditulis ke outputs/track-research-2026-11-02/inventory.json (diabaikan Git).
"""
from pathlib import Path
import argparse, collections, json, os, re, sqlite3, sys, zipfile

from fm4_converter.archives import forza_zip
from fm4_converter.archives.stfs_reader import STFS
from fm4_converter.archives.stfs_zip_io import STFSFile
from fm4_converter.paths import PROJECT_ROOT

FM3 = Path(r'D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)\Media')
FM3UC = Path(r'D:\Data\FM3\USA Ultimate Collection\Forza Motorsport 3 - Ultimate Collection (USA) (Disc 1) (Play Disc)\Media')
FM3UC2 = Path(r'D:\Data\FM3\USA Ultimate Collection\Forza Motorsport 3 - Ultimate Collection (USA) (Disc 2) (Content Install Disc)\Content\0000000000000000\4D53084D\00000002')
FM4 = Path(r'D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)\Media')
LTP = Path(r'D:\Data\forza-motorsport-4\DLC\Forza Motorsport 4 - Launch Track Pack (World) (Addon)\4D530910\00000002\94C659329A894CFA993A7812251D576B679DA1894D')
FM3_PACKS = {'0060': 'Road Racing Track Pack (Disc 2)', '0045': 'Forza Ultimate Track Pack'}
OUT = PROJECT_ROOT / 'outputs/track-research-2026-11-02/inventory.json'


def db_rows(path, sql):
    con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql)]
    finally:
        con.close()


def pack_merge_ids(pkg, pri):
    """Track ID di patch merge.slt sebuah paket DLC FM4."""
    import tempfile
    with STFS(pkg) as s:
        e = next(x for x in s.entries if x['name'].lower() == f'media/dlczips/{pri}_pri_65.zip')
        z = zipfile.ZipFile(STFSFile(s, e))
        ids = set()
        for i in z.infolist():
            if i.filename.lower().endswith('_merge.slt'):
                with tempfile.TemporaryDirectory() as d:
                    p = Path(d) / 'm.slt'
                    p.write_bytes(forza_zip.read(z, i))
                    ids |= {r['id'] for r in db_rows(p, 'select id from Tracks')}
        return ids


def file_kind(name):
    b = name.rsplit('/', 1)[-1].lower()
    for pat, k in [(r'.*\.rmb\.bin$', 'rmb'), (r'.*\.stx\.bin$', 'stx'), (r'_0x[0-9a-f]{8}_b\.bix$', 'bix_B'),
                   (r'_0x[0-9a-f]{8}\.bix$', 'bix'), (r'_0x[0-9a-f]{8}\.bin$', 'caff_bin'),
                   (r'.*_track_\d+\.col$', 'col'), (r'.*\.pvs$', 'pvs'), (r'.*\.crowd$', 'crowd'),
                   (r'.*_ribbon\d+\.sh$', 'sh'), (r'.*\.xpr$', 'xpr'), (r'.*\.fxobj$', 'fxobj')]:
        if re.match(pat, b):
            return k
    return None


def header_word(kind, data):
    """Penanda versi yang terlihat pada header (bukan bukti loader menerimanya)."""
    if kind in ('rmb', 'crowd'):
        return str(int.from_bytes(data[0:4], 'big'))
    if kind in ('sh', 'col'):
        return f'{int.from_bytes(data[0:4], "big")}/{int.from_bytes(data[4:8], "big")}'
    if kind == 'pvs':
        return f'{data[:4].decode("latin1")}/{int.from_bytes(data[4:8], "big"):#x}'
    if kind in ('stx', 'caff_bin'):
        return data[:17].decode('latin1')
    if kind in ('bix', 'xpr'):
        return data[:4].decode('latin1')
    return data[:4].hex()


def folder_headers(track_dir, limit=3):
    seen = collections.defaultdict(collections.Counter)
    for p in sorted(track_dir.rglob('*')):
        k = file_kind(p.name) if p.is_file() else None
        if k and sum(seen[k].values()) < limit:
            seen[k][header_word(k, p.read_bytes()[:32])] += 1
    z = zipfile.ZipFile(track_dir / 'bin.zip')
    for i in z.infolist():
        k = file_kind(i.filename)
        if k and k != 'bix_B' and sum(seen[k].values()) < limit:
            seen[k][header_word(k, forza_zip.read(z, i)[:32])] += 1
    return {k: dict(v) for k, v in sorted(seen.items())}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=OUT)
    ap.add_argument('--anchor', default='Tsukuba', help='track yang ada di kedua disc untuk pembanding header')
    a = ap.parse_args()

    q = 'select t.*, e.MediaName EnvMedia from Tracks t left join Environments e on e.Id=t.EnvironmentId'
    fm3 = {r['id']: r for r in db_rows(FM3 / 'DB/gamedb.slt', q)}
    fm3 |= {r['id']: r for r in db_rows(FM3UC / 'DB/gamedb.slt', q) if r['id'] not in fm3}
    fm4 = {r['id']: r for r in db_rows(FM4 / 'db/gamedb.slt', q)}
    fm4_ids = set(fm4) | pack_merge_ids(LTP, '0015')
    fm4_layouts = {(r['MediaName'].lower(), r['RibbonIndex']) for r in fm4.values()}
    fm4_layouts |= {('physicstrack', i) for i in range(16)} | {('soccer', i) for i in range(2)}

    disc_tracks = {p.name.lower() for p in (FM3 / 'Tracks').iterdir() if p.is_dir()}
    pack_tracks = {}
    for suffix in FM3_PACKS:
        with STFS(FM3UC2 / f'4D53084D0CCF{suffix}') as s:
            for e in s.entries:
                m = re.match(r'media/dlczips/(\w+)_pri_65\.zip$', e['name'].lower())
                if m and not m.group(1).isdigit():
                    pack_tracks[m.group(1)] = f'4D53084D0CCF{suffix} {FM3_PACKS[suffix]}'

    layouts = []
    for r in sorted(fm3.values(), key=lambda r: r['id']):
        media = r['MediaName']
        if media.lower().startswith('ui'):
            continue
        status = 'ada_di_fm4' if (media.lower(), r['RibbonIndex']) in fm4_layouts else 'fm3_only'
        source = 'FM3 Disc 1 Media/Tracks' if media.lower() in disc_tracks else pack_tracks.get(media.lower(), 'tidak ditemukan')
        layouts.append({'id': r['id'], 'media': media, 'ribbon': r['RibbonIndex'], 'reverse_index': r['ReverseIndex'],
                        'length': r['Length'], 'content_id': r['ContentId'], 'status': status, 'source': source,
                        'id_free_in_fm4': r['id'] not in fm4_ids})
    only = [x for x in layouts if x['status'] == 'fm3_only']
    by_media = collections.defaultdict(list)
    for x in only:
        by_media[x['media']].append(x['id'])

    result = {
        'fm3_layouts': len(layouts), 'fm3_only_layouts': len(only),
        'fm3_only_by_media': dict(by_media),
        'fm3_only_id_collisions': [x['id'] for x in only if not x['id_free_in_fm4']],
        'layouts': layouts,
        'anchor': a.anchor,
        'headers': {'FM3': folder_headers(FM3 / 'Tracks' / a.anchor), 'FM4': folder_headers(FM4 / 'tracks' / a.anchor)},
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'layouts'}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
