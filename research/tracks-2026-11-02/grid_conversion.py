"""Konversi StartGridPositions FM3 (12 posisi dunia) ke bentuk FM4 (per slot).

FM4 menyimpan `MetersBackFromStartLine`, `MetersRightOfCenterLine` dan `Yaw`
(derajat, relatif arah lintasan). Nilai itu didapat dengan memproyeksikan posisi
FM3 ke garis tengah AI `<media>_<NN>[_r].geo`: waypoint 0 adalah garis start,
dan sumbu horizontal `.geo` adalah X,Y (= x,z dunia; Z `.geo` adalah tinggi).
Slot 12-15 (FM4 punya 16, FM3 12) mengikuti pola Turn 10 pada Motegi: slot k-4
digeser sejauh slot 11 - slot 7, lateral sama, Yaw 0.

Dijalankan langsung, skrip membandingkan hasil hitung dengan baris FM4 untuk
semua layout yang ada di kedua game. Hanya membaca (SQLite mode=ro).
"""
from pathlib import Path
import sqlite3

from fm4_converter.fm3.track_grid import convert, find_ai, geo, slot  # noqa: F401

FM3 = Path(r'D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)\Media')
FM4 = Path(r'D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)\Media')


def main():
    a = sqlite3.connect(f"file:{FM3/'DB/gamedb.slt'}?mode=ro", uri=True)
    b = sqlite3.connect(f"file:{FM4/'DB/gamedb.slt'}?mode=ro", uri=True)
    fm4 = {r[0]: r for r in b.execute('SELECT id, DefaultStartGridPositionsId FROM Tracks')}
    close = total = 0
    for tid, media, rib, rev, grid in a.execute(
            'SELECT id, MediaName, RibbonIndex, ReverseIndex, DefaultStartGridPositionsId FROM Tracks'):
        if tid not in fm4:
            continue
        native = b.execute('SELECT MetersBackFromStartLine, MetersRightOfCenterLine FROM StartGridPositions '
                           'WHERE id=? ORDER BY StartIndex', (fm4[tid][1],)).fetchall()
        row = a.execute('SELECT * FROM StartGridPositions WHERE id=?', (grid,)).fetchone()
        ai = find_ai((FM4/'AI/Tracks', FM3/'AI/Tracks'), media, rib, rib != rev)
        if not native or not row or not ai:
            continue
        c = geo(ai)
        diffs = []
        for k in range(12):
            _, back, right, _ = slot(c, row[1+6*k], row[3+6*k], row[4+6*k], row[6+6*k])
            diffs.append(max(abs(back-native[k][0]), abs(right-native[k][1])))
        worst = max(diffs)
        total += 1
        close += worst <= 0.35
        print(f'{tid:4} {media:14} ribbon {rib:2}  max |FM3 hitung - FM4| = {worst:8.2f} m')
    print(f'{close}/{total} layout cocok dalam 0,35 m pada semua 12 slot')


if __name__ == '__main__':
    main()
