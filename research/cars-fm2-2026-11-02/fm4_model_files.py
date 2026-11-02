"""Sampel file model mobil disc FM4: keberadaan .carbin/_lod0/_cockpit/_s dan section kokpit.

Hanya membaca. Mengambil setiap ZIP ke-N (default 6) dari Media/cars FM4 Disc 1, lalu
membaca _cockpit.carbin dengan carbin_audit project. Hasil dicetak sebagai JSON.
"""
from pathlib import Path
import argparse, collections, json, re, zipfile

from fm4_converter.archives import forza_zip
from fm4_converter.fm3 import carbin_audit

FM4 = Path(r'D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)\Media\cars')
SUFFIXES = ('.carbin', '_lod0.carbin', '_cockpit.carbin', '_s_lod0.carbin', '_cockpit_s.carbin')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--step', type=int, default=6)
    a = p.parse_args()
    sample = sorted(FM4.glob('*.zip'), key=lambda x: x.name)[::a.step]
    present, sections, failures, parsed = collections.Counter(), collections.Counter(), {}, 0
    for path in sample:
        car = path.stem.lower()
        with zipfile.ZipFile(path) as z:
            members = {i.filename.lower() for i in z.infolist()}
            for suffix in SUFFIXES:
                present[suffix] += car + suffix in members
            if car + '_cockpit.carbin' not in members:
                continue
            try:
                model = carbin_audit.parse(forza_zip.read(z, car + '_cockpit.carbin'), 'FM4')
            except (carbin_audit.FormatError, ValueError) as e:
                failures[path.name] = str(e)
                continue
        parsed += 1
        sections.update({re.sub(r'_(min|mid|max)$', '_*', s['name']) for s in model['sections']})
    print(json.dumps(dict(zips=len(sample), files_present=present, cockpits_parsed=parsed,
                          failures=failures, cockpit_sections=dict(sections.most_common())), indent=1))


if __name__ == '__main__':
    main()
