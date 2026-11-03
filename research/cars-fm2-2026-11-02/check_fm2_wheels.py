"""Validasi velg FM2 -> FM4 pada semua velg disc FM2 (REPORT bagian 9.3).

Per velg: carbin_fm2.parse, fm2_to_fm3.convert (velg FM3 type 2) dibaca carbin_audit (FM3),
`carbin-cpu convert` + audit_conversion, `carbin-cpu lod0` + prototype_fm4_model.audit_wheel_lod0.
Untuk velg yang juga ada di FM3, header hasil transkode dibandingkan dengan file FM3 asli
(selain dua float akhir, yang berbeda per velg). Hasil di
outputs/car-fm2-research-2026-11-02/fm2_wheels_check.json.
"""
from pathlib import Path
import argparse, json, struct, sys, tempfile, zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carbin_fm2, fm2_to_fm3, prototype_fm4_model as proto
from fm4_converter.fm3 import carbin_audit
from fm4_converter.fm3.integration import archive_read
from fm4_converter.paths import PROJECT_ROOT

FM3_WHEELS = Path(r'D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)\Media\Wheels')
OUT = PROJECT_ROOT / 'outputs/car-fm2-research-2026-11-02/fm2_wheels_check.json'
END_FLOATS_AT = 0x1C4


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--limit', type=int)
    a = p.parse_args()
    fm3 = {q.stem.lower(): q for q in FM3_WHEELS.glob('*.zip')}
    wheels = sorted(proto.FM2_WHEELS.glob('*.zip'))[:a.limit]
    result = dict(wheels=len(wheels), not_fm2_format=[], failures={}, passed=0, header_checks=0,
                  header_same_except_end_floats=0, worst={})
    worst = result['worst']
    with tempfile.TemporaryDirectory(prefix='fm2-wheels-') as temp:
        temp = Path(temp)
        for number, path in enumerate(wheels):
            name = path.stem.lower()
            with zipfile.ZipFile(path) as z:
                data = z.read(next(i for i in z.infolist() if i.filename.lower() == name + '.carbin'))
            if not carbin_fm2.is_fm2(data):
                result['not_fm2_format'].append(path.stem)
                continue
            try:
                out, _ = fm2_to_fm3.convert(data)
                head = carbin_audit.parse(out, 'FM3')['header']
                if name in fm3:
                    with zipfile.ZipFile(fm3[name]) as z:
                        member = next(n for n in z.namelist() if n.lower().endswith('.carbin'))
                        native = carbin_audit.parse(archive_read(z, member), 'FM3')['header']
                    result['header_checks'] += 1
                    result['header_same_except_end_floats'] += (
                        len(native) == len(head) and native[:END_FLOATS_AT] == head[:END_FLOATS_AT]
                        and native[END_FLOATS_AT + 8:] == head[END_FLOATS_AT + 8:])
                source, lod15, final = (temp / f'{number}.{k}.carbin' for k in ('fm3', 'lod15', 'fm4'))
                source.write_bytes(out)
                proto.helper('convert', source, lod15)
                audit = carbin_audit.audit_conversion(out, lod15.read_bytes())
                proto.helper('lod0', lod15, final)
                lod0 = proto.audit_wheel_lod0(lod15.read_bytes(), final.read_bytes())
                for key, value in (('position_m', audit['position_error_m']),
                                   ('normal_deg', audit['normal_error_degrees']), ('uv', audit['uv_error']),
                                   ('lod0_position_m', lod0['lod0_worst_position_m']),
                                   ('lod15_after_lod0_position_m', lod0['lod1_5_worst_position_m'])):
                    if value > worst.get(key, (0, ''))[0]:
                        worst[key] = (value, path.stem)
                result['passed'] += 1
            except Exception as error:
                result['failures'][path.stem] = f'{type(error).__name__}: {error}'[:300]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1), encoding='utf-8')
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
