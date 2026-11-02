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
import math, re, sqlite3, struct

FM3 = Path(r'D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)\Media')
FM4 = Path(r'D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)\Media')


def geo(path):
    """Array float sebuah berkas AI MLPData (big-endian)."""
    d = Path(path).read_bytes()
    fields = {}
    for m in re.finditer(rb'(\w+):(\w+):(\d+):\d+:\s+(\d+)\n', d[:d.find(b'MLPDataEnd')]):
        if m.group(2) == b'float':
            fields[m.group(1).decode()] = struct.unpack_from(f'>{int(m.group(3))}f', d, int(m.group(4)))
    return fields


def find_ai(roots, media, ribbon, reverse):
    name = f"{media}_{ribbon:02d}{'_r' if reverse else ''}.geo".lower()
    for root in roots:
        for p in Path(root).iterdir():
            if p.name.lower() == name:
                return p


def slot(centreline, x, z, hx, hz):
    """(jarak ke garis tengah, MetersBack, MetersRight, Yaw derajat) satu slot."""
    X, Z = centreline['fWaypointX'], centreline['fWaypointY']
    n = len(X)
    cum = [0.0]
    for i in range(1, n):
        cum.append(cum[-1] + math.hypot(X[i]-X[i-1], Z[i]-Z[i-1]))
    total = cum[-1] + math.hypot(X[0]-X[-1], Z[0]-Z[-1])
    best = None
    for i in range(n):
        j = (i+1) % n
        dx, dz = X[j]-X[i], Z[j]-Z[i]
        L2 = dx*dx + dz*dz or 1e-9
        t = max(0.0, min(1.0, ((x-X[i])*dx + (z-Z[i])*dz)/L2))
        px, pz = X[i]+t*dx, Z[i]+t*dz
        dist = math.hypot(x-px, z-pz)
        if best is None or dist < best[0]:
            L = math.sqrt(L2)
            best = (dist, cum[i]+t*L, ((x-px)*dz - (z-pz)*dx)/L, math.atan2(dx, dz))
    dist, s, right, tangent = best
    back = total - s if s > total/2 else -s
    yaw = (math.degrees(math.atan2(hx, hz) - tangent) + 180) % 360 - 180
    return dist, back, right, yaw


def convert(grid_id, fm3_row, centreline, max_offset=8.0):
    """Baris StartGridPositions FM4 (16 slot) dari satu baris FM3."""
    rows = []
    for k in range(12):
        x, y, z, hx, hy, hz = fm3_row[1+6*k:7+6*k]
        dist, back, right, yaw = slot(centreline, x, z, hx, hz)
        if dist > max_offset:
            raise ValueError(f'Slot {k} is {dist:.1f} m from the AI centreline')
        rows.append((grid_id, k, back, right, yaw))
    shift = rows[11][2] - rows[7][2]
    rows += [(grid_id, k, rows[k-4][2]+shift, rows[k-4][3], 0.0) for k in range(12, 16)]
    if any(b[2] <= a[2] for a, b in zip(rows, rows[1:])):
        raise ValueError('Grid is not ordered back from the start line')
    return rows


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
