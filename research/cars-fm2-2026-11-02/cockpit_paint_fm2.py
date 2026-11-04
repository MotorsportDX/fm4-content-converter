"""Kalibrasi kecerahan kokpit FM2 -> FM4 pada mobil yang ada di FM2 dan disc FM4 (nama sama).

FM2 tidak punya kokpit; interiornya mesh bermaterial `interior` yang membaca atlas bodi
(`Nodamage.xds`). Paket uji menggambarnya di kokpit FM4 sebagai `cockpit_plastic` dengan atlas itu
sebagai `Interior_LOD0.xds` (REPORT bagian 8.2). Script ini mengukur, per mobil:

- FM2: median luminans linear atlas `Nodamage.xds` di UV LOD1 semua mesh `interior`;
- FM4: median luminans linear `Interior_LOD0.xds` di UV LOD0 mesh kokpit bertekstur, dikali paint
  scale tekniknya (`shadersettings.xml` mobil, default `Shared.zip ShaderSettings/Normal.xml`, atau 1).
  `plastic` = hanya `cockpit_plastic`; `all` = semua teknik kokpit dengan satu paint scale, per vertex.

Rasio FM4/FM2 adalah paint scale `cockpit_plastic` yang membuat interior FM2 tampil seterang
interior FM4 mobil yang sama, dengan cara ukur yang sama seperti kalibrasi FM3 (`appearance_audit
.COCKPIT_PAINT_SCALES`). Hasil di outputs/car-fm2-research-2026-11-02/cockpit_paint_fm2.json.
"""
from pathlib import Path
import collections, json, struct, sys, zipfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import survey_carbin as sv
from fm4_converter.fm2 import carbin as carbin_fm2
from fm4_converter.fm3 import appearance_audit, carbin_audit, effect_audit
from fm4_converter.fm3.integration import archive_read
from fm4_converter.fm3.texture_audit import Texture
from fm4_converter.paths import PROJECT_ROOT

FM4 = Path(r'D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)\Media')
OUT = PROJECT_ROOT / 'outputs/car-fm2-research-2026-11-02/cockpit_paint_fm2.json'
KEYS = ('PaintScale', 'CockpitPaintScale', 'CockpitPlasticPaintScale')
LUMA = np.array([0.2126, 0.7152, 0.0722])


def linear(rgb):
    c = rgb / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4) @ LUMA


def image(data):
    t = Texture(data)
    mode = {'DXT1': 1, 'DXT3': 2, 'DXT5': 3}[t.codec]
    rgb = np.asarray(Image.frombytes('RGBA', (t.width, t.height), t.read_level(0), 'bcn', mode).convert('RGB'))
    return linear(rgb.astype(float))


def sample(lum, u, v):
    h, w = lum.shape
    x = np.clip((np.asarray(u) % 1.0) * w, 0, w - 1).astype(int)
    y = np.clip((np.asarray(v) % 1.0) * h, 0, h - 1).astype(int)
    return lum[y, x]


def fm2_interior(path):
    with zipfile.ZipFile(path) as z:
        names = {n.lower(): n for n in z.namelist()}
        model = carbin_fm2.parse(z.read(names[Path(path).stem.lower() + '.carbin']))
        lum = image(z.read(names['nodamage.xds']))
    values = []
    for s in model.sections:
        pool = model.glass if s.buffer == 'glass' else model.body
        for sub in s.subsections:
            if sub.name != 'interior' or sub.lod != 1:
                continue
            idx = sorted({i for i in sub.indices if i >= 0})
            uv = np.array([pool[i][1] for i in idx])
            values += list(sample(lum, uv[:, 0], uv[:, 1]))
    return values


def fm4_cockpit(path, keys, defaults):
    with zipfile.ZipFile(path) as z:
        names = {n.lower(): n for n in z.namelist()}
        cockpit = [n for n in names if n.endswith('_cockpit.carbin')]
        if not cockpit or 'interior_lod0.xds' not in names:
            return None
        lum = image(archive_read(z, names['interior_lod0.xds']))
        model = carbin_audit.parse(archive_read(z, names[cockpit[0]]), 'FM4')
        settings = {}
        if 'shadersettings.xml' in names:
            root = appearance_audit.xml(archive_read(z, names['shadersettings.xml']))
            settings = {(e.tag, k.tag): float(k.get('value')) for e in root for k in e if k.get('value') is not None}
    shown = collections.defaultdict(list)
    for s in model['sections']:
        for mesh in s['meshes']:
            tech = appearance_audit.technique(s['name'], mesh['name'], mesh['lod'])
            if mesh['lod'] != 0 or tech not in keys:
                continue
            pool = s['lod0']
            idx = sorted(set(carbin_audit.index_values(mesh)))
            raw = np.array([struct.unpack_from('>2H', pool['data'], i * 32 + 8) for i in idx], float) / 65535
            u = mesh['uv'][0] + mesh['uv'][1] * raw[:, 0]
            v = mesh['uv'][2] + mesh['uv'][3] * raw[:, 1]
            scale = settings.get((tech, keys[tech]), defaults[tech])
            shown[tech] += list(sample(lum, u, v) * scale)
    return shown


def main():
    lib = effect_audit.read_effect((FM4 / 'Shaders/Cars/shaders_v16.fxobj').read_bytes())
    keys = {t: [k for k in KEYS if k in v['constants']] for t, v in lib.items() if t.startswith('cockpit_')}
    keys = {t: k[0] for t, k in keys.items() if len(k) == 1}
    with zipfile.ZipFile(FM4 / 'Cars/Shared.zip') as shared:
        normal = ET.fromstring(archive_read(shared, 'ShaderSettings/Normal.xml'))
    defaults = {t: float(normal.find(f'{t}/{k}').get('value')) if normal.find(f'{t}/{k}') is not None else 1.0
                for t, k in keys.items()}
    fm2 = sv.zips(sv.FM2)
    cars, failures = [], {}
    for path in sorted((FM4 / 'Cars').glob('*.zip')):
        key = path.stem.lower()
        if key not in fm2:
            continue
        try:
            shown = fm4_cockpit(path, keys, defaults)
            source = fm2_interior(fm2[key])
        except Exception as error:
            failures[path.stem] = f'{type(error).__name__}: {error}'[:200]
            continue
        if not shown or not source or np.median(source) < 1e-3:
            continue
        everything = [x for v in shown.values() for x in v]
        row = dict(car=path.stem, fm2_interior=float(np.median(source)), fm2_vertices=len(source),
                   fm4_all=float(np.median(everything)))
        if shown.get('cockpit_plastic'):
            row['fm4_plastic'] = float(np.median(shown['cockpit_plastic']))
        for k in ('all', 'plastic'):
            if f'fm4_{k}' in row:
                row[f'ratio_{k}'] = row[f'fm4_{k}'] / row['fm2_interior']
        cars.append(row)
    summary = {}
    for k in ('all', 'plastic'):
        r = sorted(c[f'ratio_{k}'] for c in cars if f'ratio_{k}' in c)
        summary[k] = dict(n=len(r), p25=r[len(r) // 4], median=r[len(r) // 2], p75=r[3 * len(r) // 4])
    fm2_levels = sorted(c['fm2_interior'] for c in cars)
    result = dict(cockpit_plastic_default=defaults['cockpit_plastic'], summary=summary,
                  fm2_interior_median=fm2_levels[len(fm2_levels) // 2], cars=cars, failures=failures)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('cockpit_plastic_default', 'summary', 'fm2_interior_median')}, indent=1),
          'failures', len(failures))


if __name__ == '__main__':
    main()
