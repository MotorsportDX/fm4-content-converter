"""FM3 StartGridPositions (12 world positions) -> FM4 rows (one per slot).

FM4 stores `MetersBackFromStartLine`, `MetersRightOfCenterLine` and `Yaw` (degrees,
relative to the track direction). They are found by projecting each FM3 position onto
the AI centreline `<media>_<NN>[_r].geo`: waypoint 0 is the start line, and the
horizontal axes of `.geo` are X,Y (world x,z; `.geo` Z is height). Slots 12-15 (FM4 has
16, FM3 12) follow Turn 10's pattern on Motegi: slot k-4 moved back by slot 11 - slot 7,
same lateral offset, Yaw 0. Point-to-point layouts on a loop's AI line (Amalfi 122-125)
start at `Tracks.StartLine`, a fraction of the loop: MetersBack is measured from there. On 29 of 78 layouts in both games this reproduces FM4 within
0.35 m on all 12 slots (research/tracks-2026-11-02/grid_conversion.py).
"""
from pathlib import Path
import math, re, struct


def geo(data):
    """Float arrays of an AI MLPData file (big-endian), from its bytes or path."""
    d = data if isinstance(data, bytes) else Path(data).read_bytes()
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


def slot(centreline, x, z, hx, hz, start=0.0, near=8.0):
    """(distance to the centreline, MetersBack, MetersRight, Yaw degrees) of one slot.

    Of the centreline points within `near` metres, the one closest to the start line wins:
    roads that pass close to themselves (Amalfi) would otherwise send a slot kilometres
    down the road."""
    X, Z = centreline['fWaypointX'], centreline['fWaypointY']
    n = len(X)
    cum = [0.0]
    for i in range(1, n):
        cum.append(cum[-1] + math.hypot(X[i]-X[i-1], Z[i]-Z[i-1]))
    total = cum[-1] + math.hypot(X[0]-X[-1], Z[0]-Z[-1])
    candidates = []
    for i in range(n):
        j = (i+1) % n
        dx, dz = X[j]-X[i], Z[j]-Z[i]
        L2 = dx*dx + dz*dz or 1e-9
        t = max(0.0, min(1.0, ((x-X[i])*dx + (z-Z[i])*dz)/L2))
        px, pz = X[i]+t*dx, Z[i]+t*dz
        dist = math.hypot(x-px, z-pz)
        L = math.sqrt(L2)
        ahead = (cum[i] + t*L - start * total) % total   # distance past the start line
        back = total - ahead if ahead > total/2 else -ahead
        candidates.append((dist, back, ((x-px)*dz - (z-pz)*dx)/L, math.atan2(dx, dz)))
    # True projections only: local minima of the distance along the line.
    close = [c for i, c in enumerate(candidates) if c[0] <= near
             and c[0] <= candidates[i-1][0] and c[0] <= candidates[(i+1) % n][0]]
    dist, back, right, tangent = min(close, key=lambda c: abs(c[1])) if close else min(candidates)
    yaw = (math.degrees(math.atan2(hx, hz) - tangent) + 180) % 360 - 180
    return dist, back, right, yaw


def convert(grid_id, fm3_row, centreline, max_offset=8.0, start=0.0):
    """FM4 StartGridPositions rows (16 slots) from one FM3 row.

    FM3 grids for 8 cars (Amalfi, LeMans) fill slots 8-11 with repeats or stray positions; a
    slot from 8 on that repeats an earlier one, lies ahead of it or off the AI line ends the
    grid, and
    the missing slots are extended by whole rows of four, as Turn 10 does for 12 -> 16."""
    rows = []
    for k in range(12):
        x, y, z, hx, hy, hz = fm3_row[1+6*k:7+6*k]
        dist, back, right, yaw = slot(centreline, x, z, hx, hz, start)
        if k >= 8 and (dist > max_offset or back < rows[-1][2] - 2.0
                       or any(math.hypot(back - r[2], right - r[3]) < 0.5 for r in rows)):
            break
        if dist > max_offset:
            raise ValueError(f'Slot {k} is {dist:.1f} m from the AI centreline')
        rows.append((grid_id, k, back, right, yaw))
    shift = rows[-1][2] - rows[-5][2]
    while len(rows) < 16:
        k = len(rows)
        rows.append((grid_id, k, rows[k-4][2]+shift, rows[k-4][3], 0.0))
    # Two-wide grids (LeMans) put a pair side by side, staggered by under a metre, as FM4 does.
    if any(b[2] < a[2] - 2.0 for a, b in zip(rows, rows[1:])) or rows[-1][2] <= rows[0][2]:
        raise ValueError('Grid is not ordered back from the start line')
    return rows
