"""Pembaca berkas track `FPVS` (Ribbon_NN/<t>_NN.pvs), mengikuti urutan baca FM4.

Implementasi ada di `fm4_converter.fm3.track_pvs`; skrip ini hanya mencetak ringkasan.

    python research/tracks-2026-11-02/pvs.py <berkas.pvs>...   # parse sampai EOF
"""
import sys

from fm4_converter.fm3.track_pvs import *  # noqa: F401,F403 (research scripts import pvs)
from fm4_converter.fm3.track_pvs import parse, summary

if __name__ == "__main__":
    for path in sys.argv[1:]:
        p = parse(open(path, "rb").read())
        print(path.split("/")[-1].split("\\")[-1], summary(p))
