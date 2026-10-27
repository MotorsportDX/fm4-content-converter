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

`build_carbin_cpu.py` checks the source revision and clean checkout. It downloads
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

```powershell
<helper-directory>/carbin-cpu.exe inspect <input.carbin>
<helper-directory>/carbin-cpu.exe convert <source-fm3.carbin> <new-fm4.carbin>
```
