"""Forza Motorsport 2 cars converted directly to FM4.

`carbin` reads FM2 car and wheel models, `transcode` rewrites them as FM3 models
for the existing FM3 -> FM4 model converter, `models` builds the FM4 main,
close-up and wheel models, `physics` calibrates FM2 stock physics to FM4, and
`package` writes FM2-only cars into an offline FM4 overlay. The research behind
each step is in research/cars-fm2-2026-11-02/REPORT.md.
"""
