"""Build the optional, pinned CPU-only model conversion helper on Windows.

Does not launch the resulting helper, the editor, or any game.
Third-party sources and binaries stay in the selected local build directory.

`--reference` is a Git checkout of the pinned commit or GitHub's archive of it unpacked
(no Git needed, as on a player's computer). Either way the sources are read with CRLF line
ends, as a Windows checkout has them, and must match REFERENCE_SHA256.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
from ..paths import TOOLS_ROOT
import subprocess
import urllib.request
import zipfile

COMMIT = "8807c7d137646dab8d9eecab7e8d5a6602ef58aa"
REPOSITORY = "https://github.com/FMdangaina/ForzaEditor"
MONOGAME_VERSION = "3.6.0.1625"
MONOGAME_SHA256 = "ec22a974a2b6fa99ed022dc339a82fbecdcf2c5c05db7216ac7a436cfe1ca8fe"
SOURCES = ("CarbinModel.cs", "CarbinModelMotorsport3.cs", "ObjMesh.cs")
# SHA-256 of the pinned files with CRLF line ends: a Windows checkout (core.autocrlf) has them,
# GitHub's archive has LF. carbin-cpu-v9, which built the tested packages, used these bytes.
REFERENCE_SHA256 = {
    "ForzaStudio/CarbinModel.cs": "ca4a76b106741c052649acf76b60c9f515b7abae878d5fae417ea3ecd10c58d5",
    "ForzaStudio/CarbinModelMotorsport3.cs": "89efdac12a0570ffdeb2229c27ed83dfd4fb37306c1a00e82b07591833e2b9be",
    "ForzaStudio/ObjMesh.cs": "edf7e9ceb62120241bfe557eb673783bcdbe7d1356c4c7e541ee99b014432c8d",
    "LICENSE": "0b383d5a63da644f628d99c33976ea6487ed89aaa59f0b3257992deac1171e6b",
    "THIRD-PARTY-NOTICES.md": "221170ff836d4ac05a32c1f9a8bfdb7ff60f3ecc195107210507a14ff6718b23",
}
# Exact, reviewed edits to copies of the pinned sources (the checkout stays
# clean). Each anchor must occur once. Extensions live in tools/carbin_cpu.
PATCHES = (
    {"file":"CarbinModelMotorsport3.cs",
     "reason":"Refit bounds of FM3 sections whose vertices lie outside them (Motorsport3Bounds.cs)",
     "old":"            if (IsZeroBounds(section.Bounds))\r\n            {\r\n",
     "new":("            if (!IsZeroBounds(section.Bounds) && ExceedsBounds(section, lodPositions, lod0Positions))\r\n"
            "            {\r\n"
            "                FitBounds(section, lodPositions, lod0Positions);\r\n"
            "            }\r\n"
            "            if (IsZeroBounds(section.Bounds))\r\n            {\r\n")},
)
EXTENSIONS = ("Motorsport3Bounds.cs",)


def crlf(data):
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def reference_files(reference):
    """{relative path: CRLF bytes} of the pinned reference files, checked by SHA-256."""
    files = {}
    for name, expected in REFERENCE_SHA256.items():
        data = crlf((reference/name).read_bytes())
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"{name} of the reference is not the pinned ForzaEditor {COMMIT[:7]} file")
        files[name] = data
    return files


def build(out, reference):
    out, reference = Path(out).resolve(), Path(reference).resolve()
    if (reference/".git").exists():
        actual = subprocess.check_output(
            ["git", "-C", str(reference), "rev-parse", "HEAD"], text=True).strip()
        if actual != COMMIT:
            raise ValueError(f"Expected ForzaEditor commit {COMMIT}, got {actual}")
        # Local source changes would invalidate the provenance recorded below.
        if subprocess.check_output(["git", "-C", str(reference), "status", "--porcelain"], text=True).strip():
            raise ValueError("The reference checkout must be unmodified")
    pinned = reference_files(reference)
    out.mkdir(parents=True, exist_ok=False)
    package_url = (f"https://api.nuget.org/v3-flatcontainer/monogame.framework.desktopgl/"
                   f"{MONOGAME_VERSION}/monogame.framework.desktopgl.{MONOGAME_VERSION}.nupkg")
    with urllib.request.urlopen(package_url, timeout=30) as response:
        package = response.read()
    if hashlib.sha256(package).hexdigest() != MONOGAME_SHA256:
        raise ValueError("Downloaded math package does not match the reviewed SHA-256")
    with zipfile.ZipFile(io.BytesIO(package)) as z:
        (out/"MonoGame.Framework.dll").write_bytes(z.read("lib/net40/MonoGame.Framework.dll"))
    # MonoGame supplies XNA-compatible Vector/Matrix/Quaternion arithmetic.
    # The adapter never constructs a graphics device; native SDL/OpenGL binaries
    # are deliberately neither extracted nor supplied.
    adapter = TOOLS_ROOT/"carbin_cpu/Program.cs"
    originals = [reference/"ForzaStudio"/s for s in SOURCES]
    (out/"src").mkdir()
    for original in originals:
        data = pinned["ForzaStudio/"+original.name]
        for patch in PATCHES:
            if patch["file"] == original.name:
                old, new = patch["old"].encode(), patch["new"].encode()
                if data.count(old) != 1:
                    raise ValueError(f"Patch anchor not found exactly once in {original.name}")
                data = data.replace(old, new)
        (out/"src"/original.name).write_bytes(data)
    inputs = ([out/"src"/s for s in SOURCES] + [TOOLS_ROOT/"carbin_cpu"/e for e in EXTENSIONS]
              + [adapter])
    compiler = Path("C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe")
    exe = out/"carbin-cpu.exe"
    command = [str(compiler), "/nologo", "/target:exe", "/platform:x64",
               "/r:System.Core.dll", "/r:System.Web.Extensions.dll",
               f"/r:{out/'MonoGame.Framework.dll'}", f"/out:{exe}"]
    subprocess.run(command + [str(p) for p in inputs], check=True)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    record = {
        "reference_repository": REPOSITORY, "reference_commit": COMMIT,
        "reference_sources": {str(p):sha(pinned["ForzaStudio/"+p.name]) for p in originals},
        "patches": [{k:v for k,v in p.items() if k in ("file","reason")} for p in PATCHES],
        "sources": {str(p):sha(p.read_bytes()) for p in inputs},
        "package_url":package_url, "package_sha256":sha(package),
        "helper_sha256":sha(exe.read_bytes()), "cpu_only":True,
        "math_library_sha256":sha((out/"MonoGame.Framework.dll").read_bytes()),
        "graphics_device_created":False,
    }
    (out/"build.json").write_text(json.dumps(record,indent=2)+"\n", encoding="utf-8")
    (out/"ForzaEditor-LICENSE.txt").write_bytes(pinned["LICENSE"])
    (out/"ForzaEditor-NOTICES.md").write_bytes(pinned["THIRD-PARTY-NOTICES.md"])
    (out/"MonoGame-LICENSE.txt").write_bytes(
        (TOOLS_ROOT/"carbin_cpu/MonoGame-LICENSE.txt").read_bytes())
    return record


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.out,a.reference),indent=2))
