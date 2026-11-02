"""Prototipe NewYork FM3 (layout 22-25) sebagai overlay uji FM4, biner track FM3 apa adanya.

Logo/mini ribbon/gambar environment sementara memakai tekstur Camino Viejo (FM4 tidak
punya tekstur NewYork). Berkas baru dikirim dalam ZIP yang di-mount zipmanifest.xml,
kecuali audio: FMOD membuka `<track>.fev` lewat path langsung, jadi audio juga ditulis
sebagai berkas lepas. `--ai-donor CrownJewel_19_R` mengganti isi AI `newyork_01`
dengan berkas donor (diagnosis, lihat REPORT.md).

    python research/tracks-2026-11-02/newyork_proto.py <paket-baru> [--ai-donor NAMA]
"""
import argparse, io, json, shutil, sqlite3, struct, sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fm4_converter.fm3 import integration, ui_names
from fm4_converter.fm3.integration import archive_read
from fm4_converter.fm3 import converter as c
from grid_conversion import FM3 as F3, FM4 as F4, convert, geo
import pvs
from fm4_converter.fm3 import track_rmb
PVS_W3 = 0x401FB8   # FM4 Tsukuba v27 header word

CONTENT = Path(r"I:\FM4-build-usa\user-data\0000000000000000\4D530910\00000002")
MEDIA, ENV, IDS = "NewYork", 12, (22, 23, 24, 25)
UI_LOGO = "GAME:\\Media\\UI\\Textures\\UI4\\Logos\\Track_Logos\\L_TRK_OldCourse.tga"
UI_LOGO_SM = "GAME:\\Media\\UI\\Textures\\UI4\\Logos\\Track_Logos_SM\\L_TRK_OldCourse.tga"
UI_RIB = "GAME:\\Media\\UI\\Textures\\UI4\\Logos\\Mini_Track_Ribbons\\RIB_OldCourse10.tga"

parser = argparse.ArgumentParser()
parser.add_argument("out")
parser.add_argument("--ai-donor")
parser.add_argument("--ai-donor-parts", default="", help="comma list: only donor files whose path contains one of these")
parser.add_argument("--convert", action="store_true", help="PVS v24 -> v27 and RMB v4 -> v5 (normal FM4 track path)")
args = parser.parse_args()
out = Path(args.out)/"files"
if out.parent.exists():
    raise SystemExit("Choose a new package directory")


def find(folder, name):
    return next(p for p in folder.iterdir() if p.name.lower() == name.lower())


def grid_rows(gid, g3, ai):
    return [list(r) for r in convert(gid, g3, geo(ai))]


a = sqlite3.connect(f"file:{F3/'DB/gamedb.slt'}?mode=ro", uri=True)
a.row_factory = sqlite3.Row
db_path = out/"Media/DB/gamedb.slt"
db_path.parent.mkdir(parents=True)
shutil.copyfile(F4/"DB/gamedb.slt", db_path)
b = sqlite3.connect(db_path)
b.row_factory = sqlite3.Row
report = {}
with b:
    if b.execute("select 1 from Environments where Id=?", (ENV,)).fetchone():
        raise SystemExit("env exists")
    e3 = dict(a.execute("select * from Environments where Id=?", (ENV,)).fetchone())
    e4cols = [r[1] for r in b.execute("pragma table_info(Environments)")]
    env = {k: e3.get(k) for k in e4cols}
    env.update(ImagePath=UI_LOGO, ThumbImageName="OldCourse", Description=e3["Location"],
               ShowOnMap=0, MapX=0.0, MapY=0.0)
    b.execute(f"insert into Environments ({','.join(env)}) values ({','.join('?'*len(env))})", list(env.values()))
    tod = dict(b.execute("select * from EnvironmentTimeOfDay where EnvironmentId=4 and TimeOfDayIndex=0").fetchone())
    tod.update(Id=b.execute("select max(Id)+1 from EnvironmentTimeOfDay").fetchone()[0], EnvironmentId=ENV)
    b.execute(f"insert into EnvironmentTimeOfDay ({','.join(tod)}) values ({','.join('?'*len(tod))})", list(tod.values()))
    t4cols = [r[1] for r in b.execute("pragma table_info(Tracks)")]
    pit_ids = {r[0] for r in b.execute("select id from PittingProfiles")}
    for tid in IDS:
        if b.execute("select 1 from Tracks where id=?", (tid,)).fetchone():
            raise SystemExit("track exists")
        r3 = dict(a.execute("select * from Tracks where id=?", (tid,)).fetchone())
        row = {k: r3.get(k) for k in t4cols}
        row.update(IsRealWorld=0, IsReverse=int(r3["RibbonIndex"] != r3["ReverseIndex"]), IsHomespace=0,
                   CarsPerUniverse=0, QuickRaceLapCountKinect=1, SatImageName=str(tid),
                   Logo=UI_LOGO, LogoSmall=UI_LOGO_SM, MiniRibbonPath=UI_RIB, RichPresence=70,
                   MPPitProfile=r3["MPPitProfile"] if r3["MPPitProfile"] in pit_ids else 100)
        missing = [k for k, v in row.items() if v is None]
        if missing:
            raise SystemExit(f"None columns {missing}")
        b.execute(f"insert into Tracks ({','.join(row)}) values ({','.join('?'*len(row))})", list(row.values()))
    grids = {}
    for tid in IDS:
        r3 = a.execute("select * from Tracks where id=?", (tid,)).fetchone()
        gid = r3["DefaultStartGridPositionsId"]
        if gid in grids:
            continue
        ai = find(F3/"AI/Tracks", f"{MEDIA}_{r3['RibbonIndex']:02d}{'_r' if r3['RibbonIndex'] != r3['ReverseIndex'] else ''}.geo")
        rows = grid_rows(gid, a.execute("select * from StartGridPositions where id=?", (gid,)).fetchone(), ai)
        if b.execute("select 1 from StartGridPositions where id=?", (gid,)).fetchone():
            raise SystemExit("grid exists")
        b.executemany("insert into StartGridPositions values (?,?,?,?,?)", rows)
        grids[gid] = [[round(v, 3) for v in r[2:]] for r in rows]
    report["grids"] = grids
    nxt = b.execute("select max(ID)+1 from SplitPoints").fetchone()[0]
    for r in a.execute("select TrackId, Split from SplitPoints where TrackId in (22,23,24,25) order by TrackId, Split"):
        b.execute("insert into SplitPoints (ID, TrackId, Split) values (?,?,?)", (nxt, r[0], r[1]))
        nxt += 1
    for t in ("GraffitiPoints", "TrackPittingZones", "TrackStartingMerges"):
        col = "Tracks_id" if t != "GraffitiPoints" else "TrackId"
        report[t] = b.execute(f"select count(*) from {t} where {col} in (22,23,24,25)").fetchone()[0]
assert b.execute("pragma integrity_check").fetchone()[0] == "ok"
b.close()

# strings: Tracks.str (track names) and Environments.str (env names), FM3 text per language
fm3_tables = {}
for p in sorted((F3/"StringTables").glob("*.zip")):
    with zipfile.ZipFile(p) as z:
        for m in z.namelist():
            if m.lower() in ("tracks.str", "environments.str"):
                fm3_tables[(p.stem.lower(), m.lower())] = ui_names.StringTable(archive_read(z, m))
wanted = {"tracks.str": [], "environments.str": []}
for tid in IDS:
    r3 = a.execute("select DisplayName, ShortDisplayName from Tracks where id=?", (tid,)).fetchone()
    wanted["tracks.str"] += [(ui_names.reference(r3[0]), f"IDS_DisplayName_{tid}"), (ui_names.reference(r3[1]), f"IDS_ShortDisplayName_{tid}")]
for field in ("Location", "DisplayName", "ShortDisplayName"):
    wanted["environments.str"].append((ui_names.reference(e3[field]), f"IDS_{field}_{ENV}"))
stream = io.BytesIO()
with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as zout:
    for table in ("Tracks.str", "Environments.str"):
        tables, _ = ui_names.winning_tables(F4, CONTENT, archive_read, c.sha, table)
        en = fm3_tables[("en", table.lower())]
        for key in wanted[table.lower()]:
            assert en.names.get(key[0] & 65535) == key[1], key
        for code, (prio, lang, origin, data) in sorted(tables.items()):
            src = fm3_tables.get((code, table.lower()), en)
            adds = [(k, s, src.texts.get(k & 65535) or en.texts[k & 65535]) for k, s in wanted[table.lower()]]
            zout.writestr(zipfile.ZipInfo(f"{lang}/{table}", (1980, 1, 1, 0, 0, 0)), ui_names.StringTable(data).add(adds))
names = stream.getvalue()
prio_names = max(ui_names.winning_tables(F4, CONTENT, archive_read, c.sha, t)[0][k][0]
                 for t in ("Tracks.str", "Environments.str") for k in ("en",)) + 1


def zip_of(entries):
    s = io.BytesIO()
    with zipfile.ZipFile(s, "w", compression=zipfile.ZIP_STORED) as z:
        for name, data in sorted(entries.items()):
            z.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data)
    return s.getvalue()


track3 = F3/"Tracks"/MEDIA
ai = {p.relative_to(F3/"AI/Tracks").as_posix(): p.read_bytes()
      for p in (F3/"AI/Tracks").rglob("*") if p.is_file() and "newyork" in p.as_posix().lower()}
if args.convert:
    # Mounted ZIPs are looked up by exact name: FM4 asks for <MediaName>_NN[_R] (CrownJewel_19_R).
    import re as _re
    canon = lambda n: _re.sub(r"_r(?=[./])", "_R", _re.sub("(?i)newyork", MEDIA, n))
    ai = {canon(n): d for n, d in ai.items()}
    # The MLP reader reads the first 1280 bytes of a file in one call (82CF42E0); from a
    # mounted ZIP a member shorter than that fails to open as MLP, so pad with zeros.
    ai = {n: d + bytes(1280 - len(d)) if d.startswith(b"MLPDataStart") and len(d) < 1280 else d
          for n, d in ai.items()}
if args.ai_donor:
    donor = {p.relative_to(F3/"AI/Tracks").as_posix().lower().replace(args.ai_donor.lower(), "*"): p
             for p in (F3/"AI/Tracks").rglob("*") if p.is_file() and args.ai_donor.lower() in p.as_posix().lower()}
    parts = [x.lower() for x in args.ai_donor_parts.split(",") if x]
    for name in [n for n in ai if "newyork_01" in n.lower() and (not parts or any(x in n.lower() for x in parts))]:
        ai[name] = donor[name.lower().replace("newyork_01", "*")].read_bytes()
        report.setdefault("ai_donor", []).append(name)
def track_file(p):
    data = p.read_bytes()
    if args.convert and p.suffix.lower() == ".pvs":
        data = pvs.write(pvs.to_v27(pvs.parse(data), PVS_W3))
    return data


archives = {
    Path("Media/tracks/NewYork.zip"): zip_of({p.relative_to(track3).as_posix(): track_file(p)
                                             for p in track3.rglob("*") if p.is_file() and p.name.lower() != "bin.zip"}),
    Path("Media/AI/Tracks.zip"): zip_of(ai),
}
audio3 = F3/"Audio/tracks"/MEDIA
audio = {p.relative_to(audio3).as_posix(): p.read_bytes() for p in audio3.rglob("*") if p.is_file()}
zones = find(find(F4/"audio/tracks", "Infin"), "ribbon_00")
zone_file = next(p for p in zones.iterdir() if "decisionzones" in p.name.lower())
for rib in range(4):
    audio[f"Ribbon_{rib:02d}/newyorkribbon_{rib:02d}decisionzones.xml"] = zone_file.read_bytes()
archives[Path("Media/audio/tracks/NewYork.zip")] = zip_of(audio)
priorities = {ui_names.OVERRIDE: prio_names, **{p: 80 for p in archives}}
manifest = integration.extend_zip_manifest((F4/"zipmanifest.xml").read_bytes(),
                                           {ui_names.OVERRIDE: names, **archives}, (), priorities)
# FM3 bin.zip as-is (LZX members; Python cannot CRC-check them), native dirsize convention (+22)
if args.convert:
    with zipfile.ZipFile(track3/"bin.zip") as zin:
        members = {}
        for info in zin.infolist():
            data = archive_read(zin, info)
            if info.filename.lower().endswith(".rmb.bin") and track_rmb.model_version(data) == 4:
                data = track_rmb.to_v5(data)
            members[info.filename] = data
    binzip = zip_of(members)
else:
    binzip = (track3/"bin.zip").read_bytes()
disk, cd_disk, n_disk, count, size, start, comment = struct.unpack_from("<4H2IH", binzip, len(binzip)-18)
assert binzip[-22:-18] == b"PK\x05\x06" and not comment and start+size == len(binzip)-22
entry = (f'<Zip version="1" path="game:\\media\\tracks\\newyork\\bin.zip" priority="80" '
         f'dirstart="{start}" dirsize="{size+22}" direntries="{count}" />').encode()
manifest = manifest.replace(b"</ZipFiles>", entry + b"</ZipFiles>")
loose_audio = {Path("Media/audio/tracks")/MEDIA/name: data for name, data in audio.items()}
for rel, data in {**archives, **loose_audio, ui_names.OVERRIDE: names, Path("Media/zipmanifest.xml"): manifest,
                  Path("Media/tracks/NewYork/bin.zip"): binzip}.items():
    (out/rel).parent.mkdir(parents=True, exist_ok=True)
    (out/rel).write_bytes(data)
report["names_priority"] = prio_names
(out.parent/"report.json").write_text(json.dumps(report, indent=1))
print(json.dumps({k: v for k, v in report.items() if k != "grids"}), {g: v[:3] for g, v in grids.items()})
for p in sorted(out.rglob("*")):
    if p.is_file():
        print(p.relative_to(out), p.stat().st_size)
