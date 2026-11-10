"""One command from a player's discs to an FM4 mod package.

  python -m fm4_converter.cli convert --game fm3 --disc <FM3 Disc 1> [--disc2 <FM3 Disc 2>]
      --fm4 <FM4 Disc 1 folder> [--content-root <...\\4D530910\\00000002>]
      --helper <carbin-cpu.exe> --out <new folder> [--cache <folder>] [--json]
  python -m fm4_converter.cli convert --game fm2 --disc <FM2 disc> [--bonus-disc <FM2 Bonus Disc>] ...
  python -m fm4_converter.cli identify <disc folder or .iso>
  python -m fm4_converter.cli verify <package>

A source disc is an extracted folder or its .iso; FM4 Disc 1 is the extracted folder a
launcher already has. `--content-root` holds the installed FM4 DLC packs: their keys stay
reserved and their string tables win, so build against the packs the player has. The
calibration is the frozen data of `fm4_converter.data`.

Cars that need the disc not given (FM3 Disc 2, FM2 Bonus Disc) are listed as skipped. A
failed car does not stop the others. The output is `<out>/files` (FM4 Disc 1 layout),
`<out>/mod.json` and `<out>/items.json` (format 2, `fm4_converter.items`).

With `--json`, stdout carries one JSON object per line and nothing else:
  {"event": "stage", "stage": "check"|"extract"|"dlc"|"package"|"describe", "message": ...}
  {"event": "extract", "role": ..., "file": ..., "done": bytes, "total": bytes}
  {"event": "car", "index": n, "total": n, "car": ..., "status": "packaged"|"failed", "error": ...}
  {"event": "done", "package": ..., "mod": ..., "packaged": n, "failed": n, "skipped": n}
  {"event": "error", "message": ...}   (exit code 1)
Without the cache folder named by `--cache`, extracted files are removed after success.
"""
import argparse
from contextlib import closing, redirect_stdout
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time

from . import data, items
from .discs import Disc, DiscError, ROLES
from .items import ModError

FM3_DISC2_PACKAGES = Path(ROLES["fm3-disc2"][2][0])
FM2_BONUS_PACKAGES = Path(ROLES["fm2-bonus"][2][0])


class Events:
    """Progress as JSON lines on the real stdout, or as text on stderr."""

    def __init__(self, as_json, stream=None):
        self.as_json, self.stream = as_json, stream or sys.stdout
        self.last_extract = 0.0

    def emit(self, event, **fields):
        if self.as_json:
            self.stream.write(json.dumps({"event": event, **fields}, ensure_ascii=False) + "\n")
            self.stream.flush()
            return
        if event == "stage":
            text = f"== {fields['message']}"
        elif event == "extract":
            text = f"   {fields['role']}: {fields['done'] >> 20} / {fields['total'] >> 20} MiB"
        elif event == "car":
            text = f"[{fields['index']}/{fields['total']}] {fields['car']}: {fields['status']}"
            if fields.get("error"):
                text += f" ({fields['error'][:200]})"
        else:
            text = " ".join(f"{k}={v}" for k, v in fields.items())
            text = f"{event}: {text}"
        print(text, file=sys.stderr, flush=True)

    def stage(self, stage, message):
        self.emit("stage", stage=stage, message=message)

    def extractor(self, role):
        def progress(file, done, total):
            now = time.monotonic()
            if done == total or now - self.last_extract >= 0.5:
                self.last_extract = now
                self.emit("extract", role=role, file=file, done=done, total=total)
        return progress


def fm4_disc(path):
    disc = Disc(path, "fm4-disc1")
    if disc.image:
        raise DiscError("Give the extracted FM4 Disc 1 folder (the one Motorsport DX plays from), not the image")
    for needed in ("Media/DB/gamedb.slt", "Media/zipmanifest.xml", "Media/StringTables", "Media/Cars"):
        if not (disc.path / needed).exists():
            raise DiscError(f"{disc.path} lacks {needed}")
    return disc


def content_packs(content_root):
    """The installed FM4 DLC archives a package was built against."""
    if not content_root:
        return []
    root = Path(content_root)
    return [dict(path=p.relative_to(root).as_posix(), size=p.stat().st_size)
            for p in sorted(root.glob("*/Media/DLCZips/*.zip"))]


def built_against(fm4, content_root):
    from .fm3 import converter as c
    media = fm4.path / "Media"
    return dict(fm4_disc1=fm4.describe(),
                fm4_gamedb_sha256=c.sha(media / "DB/gamedb.slt"),
                fm4_zipmanifest_sha256=c.sha(media / "zipmanifest.xml"),
                content_root=str(content_root) if content_root else None,
                content_packs=content_packs(content_root))


def fm3_cars(fm3_media, fm4_media, content_root, disc2):
    """(cars to package, skipped cars): every FM3 car FM4's discs lack, also those an FM4 DLC pack
    has (fm4_converter.compose leaves them out while that pack is installed); without Disc 2,
    only those whose assets are on Disc 1."""
    from .fm3 import batch_package
    from .fm3 import converter as c
    with closing(c.connect(fm3_media / "DB/gamedb.slt")) as a, closing(c.connect(fm4_media / "DB/gamedb.slt")) as t:
        missing = batch_package.missing_cars(a, t, {})
    if disc2:
        return missing, []
    on_disc = {p.stem.casefold() for p in (fm3_media / "Cars").glob("*.zip")}
    return ([m for m in missing if m.casefold() in on_disc],
            [dict(media=m, status="skipped", error="needs FM3 Disc 2") for m in missing
             if m.casefold() not in on_disc])


def convert_fm3(a, events, cache):
    from .fm3 import batch_package
    events.stage("check", "Checking the discs")
    disc1, fm4 = Disc(a.disc, "fm3-disc1"), fm4_disc(a.fm4)
    disc2 = Disc(a.disc2, "fm3-disc2") if a.disc2 else None
    discs = [d for d in (disc1, disc2) if d]
    events.stage("extract", "Reading the FM3 discs")
    root1 = disc1.root(cache, events.extractor(disc1.role))
    packages = disc2.root(cache, events.extractor(disc2.role)) / FM3_DISC2_PACKAGES if disc2 else None
    fm3_media, fm4_media = root1 / "Media", fm4.path / "Media"
    a.edition = fm3_edition(fm3_media)
    cars, skipped = fm3_cars(fm3_media, fm4_media, a.content_root, packages)
    if a.cars:
        wanted = {x.casefold() for x in a.cars}
        unknown = wanted - {m.casefold() for m in cars}
        if unknown:
            raise DiscError(f"Not FM3-only cars with sources here: {sorted(unknown)}")
        cars, skipped = [m for m in cars if m.casefold() in wanted], []
    if not cars:
        raise DiscError("No FM3 car to convert")
    events.stage("package", f"Converting {len(cars)} FM3 cars")
    with redirect_stdout(sys.stderr):
        manifest = batch_package.build(
            fm3_media / "DB/gamedb.slt", fm4_media / "DB/gamedb.slt", a.stage, a.helper, cars,
            data.path("fm3/rules.json"), data.path("fm3/pi-model.json"), a.content_root,
            data.path("fm3/value-scales.json"), False, packages, log=lambda s: None,
            progress=lambda p: events.emit("car", **p))
    records = manifest["items"] + [items.item(f"car:{s['media']}", "car", s["media"], status="skipped",
                                              error=s["error"]) for s in skipped]
    return "fm3-cars", "FM3 cars", "FM3", fm4, discs, records, CAR_ARCHIVES


def convert_fm3_tracks(a, events, cache):
    """The FM3 environments and layouts FM4 lacks (fm3.track_env): NewYork, the Bugatti circuit,
    Amalfi (FM3 Disc 2), the Test Track (the Ultimate Collection's discs) and CrownJewel 170."""
    from .discs import FM3_TRACK_PATHS
    from .fm3 import track_env
    events.stage("check", "Checking the discs")
    disc1, fm4 = Disc(a.disc, "fm3-disc1"), fm4_disc(a.fm4)
    disc2 = Disc(a.disc2, "fm3-disc2") if a.disc2 else None
    discs = [d for d in (disc1, disc2) if d]
    events.stage("extract", "Reading the FM3 discs")
    root1 = disc1.root(cache, events.extractor(disc1.role), FM3_TRACK_PATHS, "fm3-disc1-tracks")
    packages = [disc2.root(cache, events.extractor(disc2.role)) / FM3_DISC2_PACKAGES] if disc2 else []
    fm3_media = root1 / "Media"
    a.edition = fm3_edition(fm3_media)
    with closing(sqlite3.connect(f"file:{fm3_media / 'DB/gamedb.slt'}?mode=ro", uri=True)) as fm3_db:
        reasons = track_env.available(fm3_db, fm3_media, packages)
    envs = [env for env, reason in reasons.items() if reason is None]
    skipped = [dict(media=env, name=None, status="skipped", error=reason) for env, reason in reasons.items()
               if reason is not None]
    if a.cars:
        raise DiscError("--cars is for --content cars")
    if not envs:
        raise DiscError("No FM3 track to convert: " + "; ".join(f"{s['media']} {s['error']}" for s in skipped))
    events.stage("package", f"Converting {len(envs)} FM3 environments and the CrownJewel 170 layout")
    done = []

    def progress(p):
        # The previous environment is packaged when the next one starts.
        if done:
            events.emit("track", index=done[-1]["index"], total=p["total"], track=done[-1]["track"],
                        status="packaged", error=None)
        done.append(p)

    with redirect_stdout(sys.stderr):
        report = track_env.build(a.stage, envs, a.content_root, fm3_db=fm3_media / "DB/gamedb.slt",
                                 fm4=fm4.path / "Media", fm3_media=fm3_media, packages=packages,
                                 progress=progress)
    if done:
        events.emit("track", index=done[-1]["index"], total=len(envs), track=done[-1]["track"],
                    status="packaged", error=None)
    records = report["items"] + [items.item(f"environment:{s['media']}", "environment", s["media"], status="skipped",
                                            error=s["error"]) for s in skipped]
    return "fm3-tracks", "FM3 tracks", "FM3", fm4, discs, records, track_archives(records)


def track_archives(records):
    """The shared archives of track items: the AI archive and one archive a UI texture folder."""
    archives = {}
    for record in records:
        for relative in record.get("members", ()):
            root = relative[:-len(".zip")]
            archives[relative] = {"priority": 80, "root": root}
    return archives


CAR_ARCHIVES = {"Media/UI/Textures/Thumbnails.zip": {"priority": 80, "root": "Media/UI/Textures/Thumbnails"},
                "Media/audio/Cars.zip": {"priority": 96, "root": "Media/audio/Cars"}}


def fm2_cars(fm2_db, fm4_db):
    """MediaNames of every FM2 car (with the Bonus Disc's DLC when read) whose ID FM4's discs lack;
    an FM2 car with an FM4 ID is that FM4 car (some renamed, e.g. FER_612_05 is FM4's FER_612_04)."""
    with closing(sqlite3.connect(f"file:{fm4_db}?mode=ro", uri=True)) as t:
        known = {r[0] for r in t.execute("SELECT Id FROM Data_Car")}
        known_media = {r[0].casefold() for r in t.execute("SELECT MediaName FROM Data_Car")}
    with closing(sqlite3.connect(f"file:{fm2_db}?mode=ro", uri=True)) as a:
        return [m for i, m in a.execute("SELECT Id, MediaName FROM Data_Car ORDER BY Id")
                if i not in known and m.casefold() not in known_media]


def convert_fm2(a, events, cache):
    from .fm2 import dlc, package, sources
    events.stage("check", "Checking the discs")
    a.edition = "fm2"
    disc, fm4 = Disc(a.disc, "fm2-disc"), fm4_disc(a.fm4)
    bonus = Disc(a.bonus_disc, "fm2-bonus") if a.bonus_disc else None
    discs = [d for d in (disc, bonus) if d]
    events.stage("extract", "Reading the FM2 discs")
    root = disc.root(cache, events.extractor(disc.role))
    bonus_root = bonus.root(cache, events.extractor(bonus.role)) if bonus else None
    # Always point the DLC folder into the cache: without the Bonus Disc it stays absent.
    dlc_out = cache / "fm2-dlc"
    if bonus:
        if not (dlc_out / "report.json").exists():
            events.stage("dlc", "Reading the FM2 DLC from the Bonus Disc")
            shutil.rmtree(dlc_out, ignore_errors=True)
            with redirect_stdout(sys.stderr):
                dlc.build(dlc_out, bonus_root, root / "Media/DB/gamedb.slt")
    sources.configure(fm2_media=root / "Media", bonus_disc=bonus_root, dlc=dlc_out / "Media",
                      fm4_media=fm4.path / "Media")
    every = fm2_cars(sources.fm2_db(), fm4.path / "Media/DB/gamedb.slt")
    available = sources.fm2_zips("cars")
    cars = [m for m in every if m.casefold() in available]
    skipped = [items.item(f"car:{m}", "car", m, status="skipped", error="needs the FM2 Bonus Disc")
               for m in every if m.casefold() not in available]
    if a.cars:
        wanted = {x.casefold() for x in a.cars}
        unknown = wanted - {m.casefold() for m in cars}
        if unknown:
            raise DiscError(f"Not FM2 cars FM4 lacks with sources here: {sorted(unknown)}")
        cars, skipped = [m for m in cars if m.casefold() in wanted], []
    events.stage("package", f"Converting {len(cars)} FM2 cars")
    models = cache / "fm2-models"
    models.mkdir(parents=True, exist_ok=True)
    with redirect_stdout(sys.stderr):
        manifest = package.build(a.stage, cars, fm4.path / "Media/DB/gamedb.slt", a.content_root,
                                 data.path("fm2/study.json"), models, a.helper,
                                 progress=lambda p: events.emit("car", **p))
    return "fm2-cars", "FM2 cars", "FM2", fm4, discs, manifest["items"] + skipped, CAR_ARCHIVES


NOTES = ("Experimental: cockpit view, engine sound, paint colours and PI class can differ from the "
         "original game; see the converter's docs.",
         "Plays on FM4 Disc 1 alone or with the other packages (fm4_converter.compose).")

TRACK_NOTES = ("Experimental: each environment is lit with an FM4 track's settings, and only a sample of "
               "the layouts has been raced to the finish; see the converter's docs.",
               "Plays on FM4 Disc 1 alone or with the other packages (fm4_converter.compose).")


def convert(a, events):
    out = Path(a.out).resolve()
    if out.exists():
        raise DiscError(f"{out} exists; choose a new package folder")
    if not Path(a.helper).is_file():
        raise DiscError(f"Model helper {a.helper} not found")
    if a.content_root and not Path(a.content_root).is_dir():
        raise DiscError(f"Content root {a.content_root} not found")
    # An absolute path: Windows does not find a relative helper path with forward slashes.
    a.out, a.helper = out, Path(a.helper).resolve()
    cache = Path(a.cache).resolve() if a.cache else out.with_name(out.name + ".cache")
    if cache == out or out in cache.parents or cache in out.parents:
        raise DiscError("The cache folder must be outside the package folder")
    cache.mkdir(parents=True, exist_ok=True)
    a.content = getattr(a, "content", "cars")
    # The builders write a whole overlay here (the package database included); the package takes
    # only its items' files from it.
    a.stage = cache / f"stage-{a.game}-{a.content}"
    shutil.rmtree(a.stage, ignore_errors=True)
    convert_game = {("fm3", "cars"): convert_fm3, ("fm2", "cars"): convert_fm2,
                    ("fm3", "tracks"): convert_fm3_tracks}.get((a.game, a.content))
    if convert_game is None:
        raise DiscError(f"No {a.content} conversion for {a.game}")
    mod_id, name, game, fm4, discs, records, archives = convert_game(a, events, cache)
    events.stage("describe", "Writing mod.json")
    header = dict(id=mod_id, name=name, kind="track-overlay" if a.content == "tracks" else "car-overlay",
                  source_game=game, edition=a.edition,
                  sources=[d.describe() for d in discs], built_against=built_against(fm4, a.content_root),
                  notes=list(TRACK_NOTES if a.content == "tracks" else NOTES))
    described = items.write(out, a.stage / "files", records, archives, header)
    items.verify(out)
    shutil.rmtree(a.stage, ignore_errors=True)
    if not a.cache:
        shutil.rmtree(cache, ignore_errors=True)
    events.emit("done", package=str(out), mod=str(out / "mod.json"), packaged=described["packaged"],
                failed=described["failed"], skipped=described["skipped"])
    return described


def fm3_edition(fm3_media):
    """"fm3-uc" for the Ultimate Collection's Disc 1 (its database has the Test Track, which the
    original release's lacks), else "fm3". A player converts the FM3 content of one of them."""
    with closing(sqlite3.connect(f"file:{Path(fm3_media) / 'DB/gamedb.slt'}?mode=ro", uri=True)) as db:
        found = db.execute("SELECT 1 FROM Tracks WHERE MediaName='TestTrackinfield'").fetchone()
    return "fm3-uc" if found else "fm3"


def main(argv=None):
    p = argparse.ArgumentParser(prog="fm4-convert", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("convert", help="convert the FM2 or FM3 cars (or FM3's tracks) FM4 lacks into one mod package")
    c.add_argument("--game", choices=("fm3", "fm2"), required=True)
    c.add_argument("--content", choices=("cars", "tracks"), default="cars",
                   help="cars (FM3 and FM2) or tracks (FM3's environments and layouts FM4 lacks)")
    c.add_argument("--disc", required=True, help="FM3 Disc 1 or the FM2 disc: folder or .iso")
    c.add_argument("--disc2", help="FM3 Disc 2 (Content Install Disc): folder or .iso")
    c.add_argument("--bonus-disc", help="FM2 Bonus Disc: folder or .iso")
    c.add_argument("--fm4", required=True, help="extracted FM4 Disc 1 folder")
    c.add_argument("--content-root", help="installed FM4 DLC packs (...\\4D530910\\00000002)")
    c.add_argument("--helper", required=True, help="carbin-cpu.exe (tools/carbin_cpu)")
    c.add_argument("--out", required=True, help="new package folder")
    c.add_argument("--cache", help="keep extracted discs and FM2 models here to resume or rebuild")
    c.add_argument("--cars", nargs="*", help="only these MediaNames")
    c.add_argument("--json", action="store_true", help="JSON lines on stdout")
    i = sub.add_parser("identify", help="print which game and disc a folder or .iso is")
    i.add_argument("path")
    v = sub.add_parser("verify", help="check a mod package's files against mod.json")
    v.add_argument("package")
    a = p.parse_args(argv)
    if a.command == "convert":
        if a.game == "fm3" and a.bonus_disc or a.game == "fm2" and a.disc2:
            p.error("--disc2 is for FM3, --bonus-disc for FM2")
        events = Events(a.json)
        try:
            convert(a, events)
        except Exception as error:   # noqa: BLE001 - every failure ends as one error event
            events.emit("error", message=f"{type(error).__name__}: {error}")
            return 1
        return 0
    if a.command == "identify":
        try:
            print(json.dumps(Disc(a.path).describe(), indent=1))
        except (DiscError, OSError, ValueError) as error:
            print(json.dumps({"error": str(error)}, indent=1))
            return 1
        return 0
    try:
        checked = items.verify(a.package)
    except (ModError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1
    print(json.dumps({"ok": True, "id": checked["id"], "files": len(checked["files"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
