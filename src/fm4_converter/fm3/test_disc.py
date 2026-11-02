"""Build a disposable FM4 test disc from an original disc and a package overlay.

Every original file is hard-linked (no copy, no write); each overlay file
replaces its link with a fresh copy, so the original disc never changes.
The result is only for runtime tests, never for distribution.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil


class TestDiscError(RuntimeError):
    pass


def sha(path):
    h = hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda: f.read(1<<20),b""):
            h.update(block)
    return h.hexdigest()


def overlay_files(package):
    files = Path(package)/"files"
    if not files.is_dir():
        raise TestDiscError(f"No files/ overlay in {package}")
    return {p.relative_to(files).as_posix():p for p in sorted(files.rglob("*")) if p.is_file()}


def build(disc, package, out):
    disc,package,out = (Path(p).resolve() for p in (disc,package,out))
    if not (disc/"default.xex").is_file():
        raise TestDiscError(f"{disc} is not an FM4 disc root")
    if out.exists():
        raise TestDiscError("Choose a new test directory")
    if out==disc or disc in out.parents or out in disc.parents:
        raise TestDiscError("Test disc must be outside the original disc")
    overlay = overlay_files(package)
    originals = {p.relative_to(disc).as_posix():p for p in disc.rglob("*") if p.is_file()}
    lower = {k.lower():k for k in originals}
    # The disc is case-insensitive; map each overlay path onto the original's spelling.
    targets = {lower.get(k.lower(),k):v for k,v in overlay.items()}
    replaced = sorted(k for k in targets if k in originals)
    before = {k:sha(originals[k]) for k in replaced}
    out.mkdir(parents=True)
    for rel,src in originals.items():
        dst = out/rel
        dst.parent.mkdir(parents=True,exist_ok=True)
        os.link(src,dst)
    for rel,src in targets.items():
        dst = out/rel
        dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.exists():
            dst.unlink()  # drop the link first: a write through it would edit the original
        shutil.copyfile(src,dst)
    after = {k:sha(originals[k]) for k in replaced}
    if before!=after:
        raise TestDiscError("Original disc changed during installation")
    record = {
        "disc_source":str(disc),"package":str(package),"disc":str(out),
        "linked_files":len(originals),"replaced":replaced,
        "added":sorted(k for k in targets if k not in originals),
        "overlay_sha256":{k:sha(out/k) for k in sorted(targets)},
        "original_sha256":before,"originals_unchanged":True,
    }
    for rel,digest in record["overlay_sha256"].items():
        if digest!=sha(targets[rel]):
            raise TestDiscError(f"Overlay copy mismatch: {rel}")
    return record


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--disc",type=Path,required=True,help="original FM4 Disc 1 root")
    p.add_argument("--package",type=Path,required=True,help="offline_package output directory")
    p.add_argument("--out",type=Path,required=True,help="new directory for the test disc")
    a = p.parse_args()
    record = build(a.disc,a.package,a.out)
    (a.out.parent/"installation.json").write_text(json.dumps(record,indent=2))
    print(json.dumps({k:record[k] for k in ("disc","linked_files","replaced","added")},indent=2))


if __name__=="__main__":
    main()
