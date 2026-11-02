"""Track model (`*.rmb.bin`, CTrackModel) command buffers, FM3 RMB v4 -> FM4 v5.

FM4 draws track objects through command buffers recorded offline into each model:
`CTrackPresentation::DrawObject` (82314BC8) draws slot `pass*3 + variant` only when it is
below the model's slot count and the slot holds a buffer. The slot count comes from the
model version (`CTrackModel::vf0` 828826F0: v3 12, v4 15, v5 18, v6 21). FM4's main view
uses pass 5 (slots 15-17), which FM3 models (v4) do not have, so FM3 track geometry
only showed in the mirror. In FM4's own models pass 5 is a main-viewport (1280x720)
color pass that differs from FM4's own pass 4 only in being single-sampled
(`RB_SURFACE_INFO` 0x2000 without the MSAA bits, `PA_SC_AA_CONFIG` 0x2301 = 0) plus the
window scissor. FM3's pass 4 (slots 12-14) is its main-viewport color pass. `to_v5`
copies pass 4 into pass 5 and makes the copy single-sampled and untiled
(`main_view_pass`).

Layout (big-endian, `IOSys::CBinaryVersionedStream`: every version is a u32), at the end
of the model stream, `CommandBufferGroup` (8287EBE8):

    u32 version (1)
    u32 SharedHeaderSize, SharedPhysicalSize, SharedInitializationSize,
        SharedStaticFixupSize, SharedDynamicFixupSize
    per slot (8287E878):
        u32 version (2)
        u32 n, n x 8 bytes      first fixup list (82871600 / 8286C450)
        u32 n, n x 8 bytes      second fixup list
        u32 HeaderSize, PhysicalSize, InitializationSize
    header pool, physical pool, initialization pool

Each slot's data follows in each pool in slot order: header and initialization parts
4-byte aligned, physical parts 32-byte aligned with no padding after the last one. The
fixup sizes are 8 x the total items of the second and first lists. Fixups are relative
to the slot's own data (FM4's own slots 3 and 15 share identical fixup lists).
"""
import struct

SLOTS = {3: 12, 4: 15, 5: 18, 6: 21}
VARIANTS = 3


def _align(value, step):
    return (value + step - 1) // step * step


class Group:
    def __init__(self, data, at, slots):
        self.at = at
        o = at
        (self.version, header, physical, init,
         self.static_size, self.dynamic_size) = struct.unpack_from(">6I", data, o)
        o += 24
        self.slots = []
        for _ in range(slots):
            start = o
            version = struct.unpack_from(">I", data, o)[0]
            if version != 2:
                raise ValueError(f"command buffer version {version}")
            o += 4
            lists = []
            for _ in range(2):
                n = struct.unpack_from(">I", data, o)[0]
                if n > 1 << 16:
                    raise ValueError("fixup count")
                lists.append(n)
                o += 4 + 8 * n
            sizes = struct.unpack_from(">3I", data, o)
            o += 12
            self.slots.append({"stream": data[start:o], "fixups": lists, "sizes": sizes})
        pools = data[o:]
        if len(pools) != header + physical + init or self.version > 1:
            raise ValueError("pool sizes")
        self.pools_at = o
        self.parts = self._split(pools[:header], pools[header:header + physical],
                                 pools[header + physical:])

    def _split(self, header, physical, init):
        offsets = [0, 0, 0]
        parts = []
        for slot in self.slots:
            part = []
            for k, (pool, step) in enumerate(((header, 4), (physical, 32), (init, 4))):
                size = slot["sizes"][k]
                part.append(pool[offsets[k]:offsets[k] + size])
                if size:
                    offsets[k] = _align(offsets[k] + size, step)
            parts.append(part)
        expect = (len(header), _align(len(physical), 32), len(init))
        if (offsets[0], _align(offsets[1], 32), offsets[2]) != expect:
            raise ValueError("pool layout")
        return parts

    def encode(self):
        pools = [bytearray(), bytearray(), bytearray()]
        for part in self.parts:
            for k, step in enumerate((4, 32, 4)):
                if part[k]:
                    pools[k] += b"\0" * (_align(len(pools[k]), step) - len(pools[k]))
                    pools[k] += part[k]
        first = sum(s["fixups"][0] for s in self.slots)
        second = sum(s["fixups"][1] for s in self.slots)
        out = bytearray(struct.pack(">6I", self.version, len(pools[0]), len(pools[1]), len(pools[2]),
                                    8 * second, 8 * first))
        for slot in self.slots:
            out += slot["stream"]
        return bytes(out + pools[0] + pools[1] + pools[2])


RB_SURFACE_INFO, PA_SC_AA_CONFIG, PA_SC_WINDOW_OFFSET = 0x2000, 0x2301, 0x2080
SET_CONSTANT, SET_BIN_SELECT, SET_BIN_MASK = 0x2D, 0x60, 0x61
NOP = 0x80000000                       # type-2 PM4 filler
MAIN_SCISSOR_BR = 720 << 16 | 1280     # FM4 pass 5: PA_SC_WINDOW_SCISSOR_BR


def main_view_pass(physical):
    """FM3 pass 4 (4x MSAA, predicated tiling) -> single-sampled untiled pass 5.

    Register writes: MSAA bits of RB_SURFACE_INFO cleared, PA_SC_AA_CONFIG = 0. The tiling
    prologue/epilogue (SET_BIN_SELECT, SET_BIN_MASK and the predicated per-tile window
    offset/scissor SET_CONSTANTs) become NOPs, except the first window SET_CONSTANT, which
    becomes unpredicated offset 0, scissor (0, 0)-(1280, 720) as FM4's pass 5 sets it. Packet
    sizes are kept, so the slot's fixup offsets stay valid."""
    words = list(struct.unpack(f">{len(physical) // 4}I", physical[:len(physical) // 4 * 4]))
    window_set = False
    i = 0
    while i < len(words):
        head = words[i]
        kind = head >> 30
        count = ((head >> 16) & 0x3FFF) + 1
        if kind == 0:
            base = head & 0x7FFF
            for k in range(min(count, len(words) - i - 1)):
                if base + k == RB_SURFACE_INFO:
                    words[i + 1 + k] &= ~0x30000
                elif base + k == PA_SC_AA_CONFIG:
                    words[i + 1 + k] = 0
            i += 1 + count
        elif kind == 3:
            op = (head >> 8) & 0x7F
            window = (op == SET_CONSTANT and count == 4 and i + 4 < len(words)
                      and words[i + 1] == 4 << 16 | (PA_SC_WINDOW_OFFSET - 0x2000))
            if window and not window_set:
                words[i] = head & ~1
                words[i + 2:i + 5] = [0, 0, MAIN_SCISSOR_BR]
                window_set = True
            elif window or op in (SET_BIN_SELECT, SET_BIN_MASK):
                words[i:i + 1 + count] = [NOP] * (1 + count)
            i += 1 + count
        else:
            i += 1 if kind == 2 else 2
    return struct.pack(f">{len(words)}I", *words) + physical[len(words) * 4:]


def model_version(data):
    return struct.unpack_from(">I", data)[0]


def group(data):
    """The CommandBufferGroup that ends the model stream (the only offset that parses)."""
    slots = SLOTS[model_version(data)]
    found = None
    for at in range(len(data) - 24 - slots * 24, 99, -1):
        if data[at:at + 4] not in (b"\0\0\0\1", b"\0\0\0\0"):
            continue
        try:
            g = Group(data, at, slots)
        except (ValueError, struct.error):
            continue
        if found is not None:
            raise ValueError("ambiguous command buffer group")
        found = g
    if found is None:
        raise ValueError("no command buffer group")
    return found


def to_v5(data):
    """FM3 v4 model -> v5 with pass 5 (slots 15-17) copied from pass 4 (slots 12-14)."""
    if model_version(data) != 4:
        raise ValueError("expected RMB v4")
    g = group(data)
    g.slots += [dict(s) for s in g.slots[12:15]]
    g.parts += [[p[0], main_view_pass(p[1]), p[2]] for p in g.parts[12:15]]
    body = data[4:g.at]
    out = struct.pack(">I", 5) + body + g.encode()
    check = group(out)
    if len(check.slots) != 18 or check.parts[15:] != g.parts[15:]:
        raise AssertionError("pass 5 not reproduced")
    return out
