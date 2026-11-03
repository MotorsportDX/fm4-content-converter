# CPU model adapter

The build command requires the editable Python package from the
[repository setup](../../README.md#setup-python). Adapter sources and notices
are stored here; build outputs remain local.

The adapter links only `CarbinModel.cs`, `CarbinModelMotorsport3.cs`, and
`ObjMesh.cs` from [FMdangaina/ForzaEditor](https://github.com/FMdangaina/ForzaEditor)
at commit `8807c7d137646dab8d9eecab7e8d5a6602ef58aa`.
Those sources supply model parsing, writing and FM3-to-FM4 conversion.
Credit: FMdangaina, and the underlying Forza Studio work by Mike Davis.
The original MIT notices are preserved in that repository's
`THIRD-PARTY-NOTICES.md`. The adapter and derived audit modules carry
`GPL-3.0-only`; see [GPL-3.0.txt](GPL-3.0.txt).

Repository-wide [credits](../../CREDITS.md) and
[third-party notices](../../THIRD_PARTY_NOTICES.md) retain the upstream authors,
license snapshots and file-level usage, including Xenia's texture-format work.

`build_carbin_cpu.py` checks the source revision and clean checkout. It applies the reviewed edits in its `PATCHES` list to copies of the
pinned sources (the checkout stays clean), compiles `Motorsport3Bounds.cs` with them, and records
both in `build.json`. The only patch refits the bounds of FM3 sections whose vertices lie outside
them; other sections convert byte for byte as before. It downloads
the pinned MonoGame 3.6.0.1625 NuGet package, verifies its SHA-256, and extracts
only `MonoGame.Framework.dll` for XNA-compatible vector, matrix and quaternion
arithmetic. Its notices are in [MonoGame-LICENSE.txt](MonoGame-LICENSE.txt).
No SDL/OpenGL/native renderer binaries are extracted. The editor, game, texture
encoder, GUI, graphics device and animation player are not constructed or run.
The helper is a local build dependency, not a distributed game executable.

```powershell
git clone https://github.com/FMdangaina/ForzaEditor.git <reference-directory>
git -C <reference-directory> checkout 8807c7d137646dab8d9eecab7e8d5a6602ef58aa
python -m fm4_converter.fm3.build_carbin_cpu --reference <reference-directory> --out <new-helper-directory>
```

Build requires Windows .NET Framework 4's C# compiler. No XNA installation,
.NET SDK, Visual Studio project build, or GPU is needed. Build outputs, the
external checkout, extracted game assets and converted assets stay outside Git.

The `inspect` operation verifies byte-identical parse/write and draw lists.
`convert` additionally reparses the output as FM4 and creates a new file
exclusively. `asset_conversion.py` then uses the separate Python reader in
`carbin_audit.py` to compare geometry with the source. Helper success alone is
not an acceptance result.

`closeup` makes a `_lod0` or `_cockpit` model from an FM4 car model's LOD 1 with
ForzaEditor's `CloseUpFromLod1`. It is for sources without close-up files, such as FM2
cars. The header comes as-is from a native FM4 file of the wanted kind (`<head.carbin>`).
The sections named one per line in `<sections.txt>` are the only ones kept (`include`) or
the ones left out (`exclude`). An optional `<materials.txt>` holds `old new` material renames,
one pair per line, for the close-up's meshes; `section/old new` renames only in that section
and takes precedence. Every pair must match a mesh. FM4 draws LOD 0 cockpit meshes with
`cockpit_<material>` techniques, and some source material names have no such technique (FM2
`interior`); FM4 also draws mirror reflections only for the `mirrorLeft`/`mirrorRight`/
`mirrorMiddle` materials over UV 0..1 (U along model X, V along Y: 798 of the 830 FM4 Disc 1
mirror meshes). A mesh renamed to one of those gets such UVs: written from its X/Y positions when
no other mesh of the part uses its vertices, otherwise by refitting its UV transform (rejected
when the source UVs are not affine in X/Y). The output is reparsed and created exclusively.
`research/cars-fm2-2026-11-02/prototype_fm4_model.py` audits the result triangle by
triangle against LOD 1.

`lod0` rebuilds LOD 0 of an FM4 wheel (type 3) from its LOD 1 with ForzaEditor's
`Lod0FromLod1`, for wheels without one (FM2). As on 441 of FM4's 442 wheels, LOD 0 has no tire.
`research/cars-fm2-2026-11-02/prototype_fm4_model.py` audits LOD 1-5 before and after and each
LOD 0 mesh against LOD 1.

```powershell
<helper-directory>/carbin-cpu.exe inspect <input.carbin>
<helper-directory>/carbin-cpu.exe convert <source-fm3.carbin> <new-fm4.carbin>
<helper-directory>/carbin-cpu.exe closeup <fm4.carbin> <head.carbin> <new.carbin> <sections.txt> include|exclude [<materials.txt>]
<helper-directory>/carbin-cpu.exe lod0 <fm4-wheel.carbin> <new.carbin>
```
