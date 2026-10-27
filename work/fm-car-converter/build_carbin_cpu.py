"""Build the optional, pinned CPU-only model conversion helper on Windows.

Does not launch the resulting helper, the editor, or any game.
Third-party sources and binaries stay in the selected local build directory.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

COMMIT = "8807c7d137646dab8d9eecab7e8d5a6602ef58aa"
REPOSITORY = "https://github.com/FMdangaina/ForzaEditor"
MONOGAME_VERSION = "3.6.0.1625"
MONOGAME_SHA256 = "ec22a974a2b6fa99ed022dc339a82fbecdcf2c5c05db7216ac7a436cfe1ca8fe"
SOURCES = ("CarbinModel.cs", "CarbinModelMotorsport3.cs", "ObjMesh.cs")


def build(out, reference):
    out, reference = Path(out).resolve(), Path(reference).resolve()
    actual = subprocess.check_output(
        ["git", "-C", str(reference), "rev-parse", "HEAD"], text=True).strip()
    if actual != COMMIT:
        raise ValueError(f"Expected ForzaEditor commit {COMMIT}, got {actual}")
    # Local source changes would invalidate the provenance recorded below.
    if subprocess.check_output(["git", "-C", str(reference), "status", "--porcelain"], text=True).strip():
        raise ValueError("The reference checkout must be unmodified")
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
    adapter = Path(__file__).parent/"carbin_cpu/Program.cs"
    inputs = [reference/"ForzaStudio"/s for s in SOURCES] + [adapter]
    compiler = Path("C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe")
    exe = out/"carbin-cpu.exe"
    command = [str(compiler), "/nologo", "/target:exe", "/platform:x64",
               "/r:System.Core.dll", "/r:System.Web.Extensions.dll",
               f"/r:{out/'MonoGame.Framework.dll'}", f"/out:{exe}"]
    subprocess.run(command + [str(p) for p in inputs], check=True)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    record = {
        "reference_repository": REPOSITORY, "reference_commit": COMMIT,
        "sources": {str(p):sha(p.read_bytes()) for p in inputs},
        "package_url":package_url, "package_sha256":sha(package),
        "helper_sha256":sha(exe.read_bytes()), "cpu_only":True,
        "math_library_sha256":sha((out/"MonoGame.Framework.dll").read_bytes()),
        "graphics_device_created":False,
    }
    (out/"build.json").write_text(json.dumps(record,indent=2)+"\n", encoding="utf-8")
    (out/"ForzaEditor-LICENSE.txt").write_bytes((reference/"LICENSE").read_bytes())
    (out/"ForzaEditor-NOTICES.md").write_bytes((reference/"THIRD-PARTY-NOTICES.md").read_bytes())
    (out/"MonoGame-LICENSE.txt").write_bytes(
        (Path(__file__).parent/"carbin_cpu/MonoGame-LICENSE.txt").read_bytes())
    return record


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.out,a.reference),indent=2))
