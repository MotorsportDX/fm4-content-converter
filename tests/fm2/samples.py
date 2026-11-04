"""A minimal synthetic FM2 wheel .carbin: one glass-buffer section holding a unit quad."""
import struct


def u32(v):
    return struct.pack('>I', v)


def vertex(x, y, normal=(0, 0, 1)):
    position = struct.pack('>4e', x, y, 0.0, 1.0)
    uv = struct.pack('>4H', round(32768 + 1310.72 * x), round(32768 + 1310.72 * y), 32768, 32768)
    nx, ny, nz = (round(normal[0] * 1023) & 0x7FF, round(normal[1] * 1023) & 0x7FF, round(normal[2] * 511) & 0x3FF)
    return position + uv + u32(nx | ny << 11 | nz << 22) + bytes(40)


def wheel(name=b'rim', indices=(0, 1, 2, 0, 2, 3), index_type=4):
    quad = [(0, 0), (1, 0), (1, 1), (0, 1)]
    header = u32(1) + u32(0x2CA) + u32(1) + u32(0) + u32(1) + bytes(96) + u32(4) + u32(4)
    # One pair of draw lists: the first draws section 0 mesh 0, the second is empty.
    lists = u32(1) + u32(1) + u32(0) + u32(0) + bytes(4) + u32(1)
    section = (u32(2) + struct.pack('>9f', 0, 0, 0, -1, -1, -1, 1, 1, 1) + bytes(0x1C) + u32(0) + bytes(4)
               + u32(0) + struct.pack('>2H', 0, len(quad) - 1) + u32(5) + u32(5) + bytes([len(name)]) + name
               + u32(2) + u32(1) + u32(0) + u32(60) + bytes(4) + u32(1))
    sub = (bytes(8) + u32(len(name)) + name + u32(index_type) + u32(1) + u32(3) + u32(len(indices)) + u32(2)
           + struct.pack(f'>{len(indices)}H', *indices))
    buffers = (bytes(8) + u32(len(quad)) + u32(60) + bytes(4) + b''.join(vertex(x, y) for x, y in quad)
               + bytes(12) + u32(0) + u32(60) + bytes(4))
    data = header + lists + section + sub + buffers
    return data + bytes(max(0, 0x201 - len(data)))
