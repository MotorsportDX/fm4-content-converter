"""FM3-only track environments (NewYork, Amalfi, TestTrackinfield) -> one FM4 overlay.

Each environment is a whole FM3 track: database rows, ribbon files, track binaries, AI,
audio and names. What FM4 needs, and why (research/tracks-2026-11-02/REPORT.md):

- PVS v24 -> v27 (`track_pvs.to_v27`), so FM4 takes its normal track path.
- RMB v4 -> v5 (`track_rmb.to_v5`), so FM4's main view draws the models (pass 5).
- `bin.zip` rebuilt with stored members (Python cannot write XMemCompress).
- `TrackSettings.xml` from an FM4 track: FM4 relit every track and its lighting values do
  not map from FM3's (`--settings-donor`).
- AI files named `<MediaName>_NN[_R]` and MLP files padded to 1280 bytes: FM4 reads the
  first 1280 bytes of an MLP file in one call, which fails for shorter members of a
  mounted ZIP.
- New files in ZIPs mounted by `zipmanifest.xml`; audio also loose, because FMOD opens
  `<media>.fev` by path. FM3 has no `decisionzones` audio; FM4 Infin's is borrowed.
- Track logos, mini ribbons and the environment picture are FM4 placeholders.

    python -m fm4_converter.fm3.track_env --out <new package> --content-root <...\\4D530910\\00000002>
        [--env NewYork --env Amalfi --env TestTrackinfield] [--base <car package>]
"""
import argparse, io, json, os, re, shutil, sqlite3, struct, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from . import integration, ui_names, track_grid, track_pvs, track_rmb, track_package
from .integration import archive_read
from ..archives.stfs_reader import STFS
from ..archives.stfs_zip_io import STFSFile

FM3 = Path(r"D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)\Media")
FM3UC = Path(r"D:\Data\FM3\USA Ultimate Collection\Forza Motorsport 3 - Ultimate Collection (USA) (Disc 1) (Play Disc)\Media")
FM3UC2 = Path(r"D:\Data\FM3\USA Ultimate Collection\Forza Motorsport 3 - Ultimate Collection (USA) (Disc 2) (Content Install Disc)\Content\0000000000000000\4D53084D\00000002")
FM4 = Path(r"D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)\Media")

PVS_W3 = 0x401FB8          # header word of FM4's Tsukuba v27 ribbons
MLP_READ = 1280            # bytes FM4's MLP reader takes in one call (82CF42E0)
UI_ROOTS = [FM3UC / "UI/Textures.zip", FM3 / "UI/Textures.zip"]   # FM3 logos, mini ribbons, images
DECISION_ZONES_DONOR = ("Infin", "ribbon_00")


class DiscSource:
    """An environment on an FM3 disc (`Media/Tracks/<media>` with `bin.zip`)."""

    def __init__(self, media, root=FM3):
        self.media, self.root = media, Path(root)

    def _folder(self, *parts):
        p = self.root
        for part in parts:
            p = next(c for c in p.iterdir() if c.name.lower() == part.lower())
        return p

    def track_files(self):
        folder = self._folder("Tracks", self.media)
        return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*")
                if p.is_file() and p.name.lower() != "bin.zip"}

    def bin_members(self):
        with zipfile.ZipFile(self._folder("Tracks", self.media, "bin.zip")) as z:
            for info in z.infolist():
                yield info.filename, archive_read(z, info)

    def ai_files(self):
        folder = self._folder("AI", "Tracks")
        key = self.media.lower() + "_"
        return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*")
                if p.is_file() and key in p.as_posix().lower()}

    def audio_files(self):
        folder = self._folder("Audio", "Tracks", self.media)
        return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


class PackSource:
    """An environment in an FM3 DLC package (STFS): loose `<pri>_pri_65/Media/...`,
    `<pri>_pri_65.zip` (`media/Tracks/<media>/...`) and `<media>_pri_65.zip` (bin)."""

    def __init__(self, media, package, pri):
        self.media, self.package, self.pri = media, Path(package), pri

    def _entries(self):
        with STFS(self.package) as s:
            return {e["name"].lower(): e for e in s.entries}

    def _loose(self, prefix):
        prefix = f"media/dlczips/{self.pri}_pri_65/media/{prefix}".lower()
        out = {}
        with STFS(self.package) as s:
            for e in s.entries:
                n = e["name"]
                if n.lower().startswith(prefix) and not e.get("is_dir") and e.get("size"):
                    out[n[len(prefix):]] = s.read(e)
        return out

    def _zip(self, name):
        s = STFS(self.package)
        entry = next(e for e in s.entries if e["name"].lower() == f"media/dlczips/{name}".lower())
        return s, zipfile.ZipFile(STFSFile(s, entry))

    def track_files(self):
        prefix = f"tracks/{self.media}/"
        files = self._loose(prefix)
        s, z = self._zip(f"{self.pri}_pri_65.zip")
        with s:
            for info in z.infolist():
                n = info.filename
                if n.lower().startswith("media/" + prefix.lower()) and not n.endswith("/"):
                    files[n[len("media/" + prefix):]] = archive_read(z, info)
        return files

    def bin_members(self):
        s, z = self._zip(f"{self.media}_pri_65.zip")
        with s:
            for info in z.infolist():
                if not info.filename.endswith("/"):
                    yield info.filename, archive_read(z, info)

    def ai_files(self):
        key = self.media.lower() + "_"
        return {n: d for n, d in self._loose("ai/tracks/").items() if key in n.lower()}

    def audio_files(self):
        return self._loose(f"audio/tracks/{self.media}/")


class RenamedSource:
    """An FM3 environment under a new MediaName. FM4 builds file names from MediaName
    (`%s.stx.bin`, `Ribbon_%02d\%s_%02d.pvs`, `%s_track_%02d.col`, AI `%s_%02d%s`,
    `%s.fev`), so every file name carrying the old name is renamed; model names come from
    the PVS (`lemansout.%05d.rmb.bin`) and stay."""

    def __init__(self, source, media):
        self.source, self.media = source, media
        self.pattern = re.compile(rf"(?i){re.escape(source.media)}(?!out)")

    def _name(self, name):
        return self.pattern.sub(self.media, name)

    def track_files(self):
        return {self._name(n): d for n, d in self.source.track_files().items()}

    def bin_members(self):
        for name, data in self.source.bin_members():
            yield self._name(name), data

    def ai_files(self):
        return {self._name(n): d for n, d in self.source.ai_files().items()}

    def audio_files(self):
        # The folder follows MediaName, but FM4 asks for the FMOD project by its own name
        # (`Audio\Tracks\LeMansBugatti\lemans.fev`): original names, plus renamed copies.
        files = self.source.audio_files()
        return {**{self._name(n): d for n, d in files.items()}, **files}


# media in FM4 -> source, FM4 TrackSettings donor, FM3 MediaName, FM3 track ids (None: all),
# FM4 environment the layouts join (None: a new environment)
SOURCES = {
    "NewYork": (lambda: DiscSource("NewYork"), "Tsukuba", "NewYork", None, None),
    "Amalfi": (lambda: PackSource("Amalfi", FM3UC2 / "4D53084D0CCF0060", "0060"), "AmalfiGP", "Amalfi", None, "AmalfiGP"),
    "TestTrackinfield": (lambda: PackSource("TestTrackinfield", FM3UC2 / "4D53084D0CCF0045", "0045"), "Tsukuba",
                         "TestTrackinfield", None, None),
    # FM4 keeps LeMans 100/101 with its own models; FM3's Bugatti circuit (102, ribbon 0)
    # needs FM3's whole LeMans set, so it becomes an environment of its own.
    "LeMansBugatti": (lambda: RenamedSource(DiscSource("LeMans"), "LeMansBugatti"), "LeMans", "LeMans", (102,), "LeMans"),
}


def canonical_ai_name(name, media):
    """FM4 asks for `<MediaName>_NN[_R]` (`%s_%02d%s`), and mounted ZIPs match exact names."""
    name = re.sub(re.escape(media), media, name, flags=re.I)
    return re.sub(r"_r(?=[./])", "_R", name)


def pad_mlp(data):
    if data.startswith(b"MLPDataStart") and len(data) < MLP_READ:
        return data + bytes(MLP_READ - len(data))
    return data


ROAD_DETAIL = 0x10   # texture type in l20 flags (& 0xF0) that makes FM4 build its road detail array


def without_road_detail(p):
    """The PVS with its road detail texture made an ordinary one (flags 0x14 -> 0x04).

    `CTrackPresentation::vf74` (82956C00) blurs every type-0x10 texture into a
    `CRoadDetailTextureArray`; with NewYork's FM3 texture its state machine reads a null
    texture in state 4 (8290F4E8 -> D3D::GetTextureDescInternal) in some runs."""
    q = dict(p)
    q["l20"] = [t[:6] + (t[6] & ~0xF0 if t[6] & 0xF0 == ROAD_DETAIL else t[6],) for t in p["l20"]]
    return q


def skybox_index(settings):
    m = re.search(rb'<SkyboxIndex\s+value="(\d+)"', settings or b"")
    return int(m.group(1)) if m else None


def convert_track_file(name, data, settings):
    """A file of `Media/Tracks/<media>/` as FM4 needs it."""
    low = name.lower()
    if low.endswith(".pvs"):
        p = track_pvs.to_v27(track_pvs.parse(data), PVS_W3, skybox_index(settings))
        return track_pvs.write(without_road_detail(p))
    if low == "tracksettings.xml" and settings is not None:
        return settings
    return data


def write_bin(path, members, sky_indexes=()):
    """Write the track `bin.zip` (stored) with RMB v4 models as v5; (members, models).
    The FM3 sky model (`<x>.sky.rmb.bin`) is also written as `<x>.{i:05d}.rmb.bin` for each
    sky object index i of the converted ribbons (`track_pvs.sky_model_index`)."""
    count = models = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        for name, data in members:
            if name.lower().endswith(".rmb.bin") and track_rmb.model_version(data) == 4:
                data = track_rmb.to_v5(data)
                models += 1
            z.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data)
            count += 1
            if name.lower().endswith(".sky.rmb.bin"):
                for i in sky_indexes:
                    z.writestr(zipfile.ZipInfo(f"{name[:-len('.sky.rmb.bin')]}.{i:05d}.rmb.bin",
                                               (1980, 1, 1, 0, 0, 0)), data)
                    count += 1
    return count, models


def zip_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as z:
        for name, data in sorted(entries.items()) if isinstance(entries, dict) else entries:
            z.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data)
    return stream.getvalue()


def zip_directory(end):
    """(dirstart, dirsize with FM4's +22 convention, entries) from a ZIP's last 22 bytes."""
    if len(end) != 22 or end[:4] != b"PK\x05\x06":
        raise ValueError("unexpected ZIP end record")
    _, _, _, count, size, start, comment = struct.unpack_from("<4H2IH", end, 4)
    if comment:
        raise ValueError("ZIP comment")
    return start, size + 22, count


def _find(folder, name):
    return next(p for p in Path(folder).iterdir() if p.name.lower() == name.lower())


def fm3_tracks(fm3_db, fm3_media, ids=None):
    rows = [dict(r) for r in fm3_db.execute("select * from Tracks where MediaName=? order by id", (fm3_media,))]
    return [r for r in rows if ids is None or r["id"] in ids]


def add_database(fm3_db, fm4_db, media, ai, fm3_media=None, ids=None, join=None):
    """Environment, time of day, Tracks, StartGridPositions and SplitPoints of one FM3
    environment into the FM4 database `fm4_db` (an open sqlite3 connection), as `media`.

    With `join` (an FM4 environment's MediaName) the layouts join that environment
    instead of a new one: FM4's location menu shows at most 30 environments (FM3 Amalfi,
    the 31st, never appeared), and Amalfi Coast and Le Mans Bugatti share their location
    with FM4's AmalfiGP and LeMans. Track files still follow `Tracks.MediaName`."""
    a, b = fm3_db, fm4_db
    fm3_media = fm3_media or media
    if b.execute("select 1 from Environments where MediaName=?", (media,)).fetchone():
        raise ValueError(f"FM4 already has environment {media}")
    if join:
        env = b.execute("select Id from Environments where MediaName=?", (join,)).fetchone()[0]
    else:
        e3 = dict(a.execute("select * from Environments where MediaName=?", (fm3_media,)).fetchone())
        env = e3["Id"]
        # FM4's environment ids start at 1; FM3's Amalfi is 0.
        if env < 1 or b.execute("select 1 from Environments where Id=?", (env,)).fetchone():
            env = b.execute("select max(Id)+1 from Environments").fetchone()[0]
        cols = [r[1] for r in b.execute("pragma table_info(Environments)")]
        row = {k: e3.get(k) for k in cols}
        row.update(Id=env, MediaName=media, Description=e3["Location"], ShowOnMap=0, MapX=0.0, MapY=0.0)
        b.execute(f"insert into Environments ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values()))
        tod = dict(b.execute("select * from EnvironmentTimeOfDay where EnvironmentId=4 and TimeOfDayIndex=0").fetchone())
        tod.update(Id=b.execute("select max(Id)+1 from EnvironmentTimeOfDay").fetchone()[0], EnvironmentId=env)
        b.execute(f"insert into EnvironmentTimeOfDay ({','.join(tod)}) values ({','.join('?' * len(tod))})",
                  list(tod.values()))
    cols = [r[1] for r in b.execute("pragma table_info(Tracks)")]
    pits = {r[0] for r in b.execute("select id from PittingProfiles")}
    tracks = fm3_tracks(a, fm3_media, ids)
    ids = [t["id"] for t in tracks]
    names = {n.lower() for n in ai}
    # ReverseIndex names the ribbon whose geometry a layout uses (Amalfi 122 drives ribbon
    # 0's road forwards); a reverse layout is the one with `<media>_NN_R` AI files.
    reverse = {t["id"]: f"{media}_{t['RibbonIndex']:02d}_r.geo".lower() in names for t in tracks}
    # Grids first: an FM3 grid id FM4 already uses (Amalfi 121 = AmalfiGP) gets a new id.
    grids, grid_ids = {}, {}
    for t in tracks:
        gid = t["DefaultStartGridPositionsId"]
        if gid in grid_ids:
            continue
        new = gid
        if b.execute("select 1 from StartGridPositions where id=?", (gid,)).fetchone():
            new = b.execute("select max(id)+1 from StartGridPositions").fetchone()[0]
        geo_name = f"{media}_{t['RibbonIndex']:02d}{'_r' if reverse[t['id']] else ''}.geo".lower()
        geo_data = next(d for n, d in ai.items() if n.lower() == geo_name)
        rows = track_grid.convert(new, a.execute("select * from StartGridPositions where id=?", (gid,)).fetchone(),
                                  track_grid.geo(geo_data), start=t["StartLine"] or 0.0)
        b.executemany("insert into StartGridPositions values (?,?,?,?,?)", rows)
        grid_ids[gid] = new
        grids[new] = len(rows)
    # FM4 lists environments by their tracks' MPSortOrder; FM3's Amalfi uses AmalfiGP's
    # 1400/1401 and its environment did not show. A colliding block moves to free hundreds.
    used = {r[0] for r in b.execute("select MPSortOrder from Tracks")}
    orders = {t["id"]: t["MPSortOrder"] for t in tracks}
    if used & set(orders.values()):
        low = min(orders.values())
        start = (max(used) // 100 + 1) * 100
        orders = {k: start + v - low for k, v in orders.items()}
    for t in tracks:
        if b.execute("select 1 from Tracks where id=?", (t["id"],)).fetchone():
            raise ValueError(f"FM4 already has track {t['id']}")
        if not b.execute("select 1 from FlyingStartPositions where id=?", (t["FlyingStartPosId"],)).fetchone() and                 a.execute("select 1 from FlyingStartPositions where id=?", (t["FlyingStartPosId"],)).fetchone():
            raise ValueError(f"track {t['id']}: FM3 flying start {t['FlyingStartPosId']} missing in FM4")
        row = {k: t.get(k) for k in cols}
        row.update(IsRealWorld=0, IsReverse=int(reverse[t["id"]]), IsHomespace=0,
                   CarsPerUniverse=0, QuickRaceLapCountKinect=1, SatImageName=str(t["id"]),
                   RichPresence=70,
                   # FM3 DLC rows name their content pack (Amalfi 96); FM4 hides tracks of
                   # content it does not own. This overlay ships the track itself.
                   ContentId=0, IsInstalled=1, MPSortOrder=orders[t["id"]],
                   DefaultStartGridPositionsId=grid_ids[t["DefaultStartGridPositionsId"]], EnvironmentId=env,
                   MediaName=media,
                   MPPitProfile=t["MPPitProfile"] if t["MPPitProfile"] in pits else 100)
        missing = [k for k, v in row.items() if v is None]
        if missing:
            raise ValueError(f"track {t['id']}: no value for {missing}")
        b.execute(f"insert into Tracks ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values()))
    nxt = b.execute("select max(ID)+1 from SplitPoints").fetchone()[0]
    marks = ",".join("?" * len(ids))
    for tid, split in a.execute(f"select TrackId, Split from SplitPoints where TrackId in ({marks}) order by TrackId, Split", ids):
        b.execute("insert into SplitPoints (ID, TrackId, Split) values (?,?,?)", (nxt, tid, split))
        nxt += 1
    return {"environment": env, "tracks": ids, "grids": grids}


def ui_textures(env_row, tracks, fm4_names, sources, environment=True):
    """{texture path under Media/UI/Textures: xds bytes} FM4 lacks for one environment's
    logo, small logo, mini ribbons (and _SM) and environment images (UI4/Track_Images/
    <ThumbImageName>1..3), taken from FM3's UI archives. FM3 and FM4 UI .xds are both Xenos
    texture headers plus data (FM3 8888, FM4 DXT)."""
    bs = chr(92)
    wanted = set()
    for value in [env_row["ImagePath"]] * environment + [t[k] for t in tracks for k in ("Logo", "LogoSmall", "MiniRibbonPath")]:
        rel = value.replace(bs, "/").split("Textures/", 1)[-1].rsplit(".", 1)[0] + ".xds"
        wanted.add(rel)
        if "/Mini_Track_Ribbons/" in rel:
            wanted.add(rel.replace("/Mini_Track_Ribbons/", "/Mini_Track_Ribbons_SM/"))
    if environment:
        wanted.update(f"UI4/Track_Images/{env_row['ThumbImageName']}{k}.xds" for k in (1, 2, 3))
    out = {}
    for rel in sorted(wanted):
        if rel.lower() in fm4_names:
            continue
        for z in sources:
            hit = next((n for n in z.namelist() if n.lower() == rel.lower()), None)
            if hit:
                out[hit] = archive_read(z, hit)
                break
    return out


def string_additions(media_rows, env_row, media, siblings=frozenset()):
    """{table: [(fm3 key, FM4 key name, FM3 table, keys whose text it must not repeat)]}
    one environment needs; no environment names when it joins an FM4 one (env_row None)."""
    wanted = {"tracks.str": [], "environments.str": []}
    for t in media_rows:
        wanted["tracks.str"] += [(ui_names.reference(t["DisplayName"]), f"IDS_DisplayName_{t['id']}", "tracks.str",
                                  siblings),
                                 (ui_names.reference(t["ShortDisplayName"]), f"IDS_ShortDisplayName_{t['id']}",
                                  "tracks.str", siblings)]
    for field in ("Location", "DisplayName", "ShortDisplayName") if env_row else ():
        # Labels only: FM4 finds the text by key. Labels by id can exist already
        # (FM4's tables name environments its database no longer has, e.g. 62).
        wanted["environments.str"].append((ui_names.reference(env_row[field]), f"IDS_{field}_FM3_{media}",
                                           "environments.str", frozenset()))
    return wanted


def fm3_string_tables(roots):
    tables = {}
    for root in roots:
        for p in sorted(Path(root).glob("*.zip")):
            with zipfile.ZipFile(p) as z:
                for m in z.namelist():
                    if m.lower() in ("tracks.str", "environments.str"):
                        tables[(p.stem.lower(), m.lower())] = ui_names.StringTable(archive_read(z, m))
    return tables


def build(out, envs, content_root, fm3_db=FM3UC / "DB/gamedb.slt", base=None, fm4=FM4, string_roots=None,
          layouts=(170,)):
    from . import converter as c
    files = Path(out) / "files"
    if Path(out).exists():
        raise SystemExit("Choose a new package directory")
    db_path = files / "Media/DB/gamedb.slt"
    base_names, base_priority = {}, 0
    if base:
        # The car package's files (hard links); the files written below are replaced, not
        # modified, so the base package stays as it is.
        shutil.copytree(Path(base) / "files", files, copy_function=os.link)
        db_path.unlink()
        if (Path(base) / "files" / ui_names.OVERRIDE).exists():
            with zipfile.ZipFile(Path(base) / "files" / ui_names.OVERRIDE) as z:
                base_names = {n: z.read(n) for n in z.namelist()}
            mounts = ET.fromstring((Path(base) / "files/Media/zipmanifest.xml").read_bytes()).findall("Zip")
            base_priority = max(int(m.attrib["priority"]) for m in mounts
                                if m.attrib["path"].casefold() == "\\".join(["game:", "media", "stringtables.zip"]))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(base) / "files/Media/DB/gamedb.slt" if base else fm4 / "DB/gamedb.slt", db_path)
    a = sqlite3.connect(f"file:{fm3_db}?mode=ro", uri=True)
    a.row_factory = sqlite3.Row
    b = sqlite3.connect(db_path)
    b.row_factory = sqlite3.Row
    fm4_env_keys = {ui_names.reference(v) & 65535 for row in b.execute(
        "select DisplayName, ShortDisplayName from Environments") for v in row}
    report, archives, loose, bins, ai_all = {}, {}, {}, {}, {}
    wanted = {"tracks.str": [], "environments.str": []}
    zones_dir = _find(_find(fm4 / "audio/tracks", DECISION_ZONES_DONOR[0]), DECISION_ZONES_DONOR[1])
    zone_file = next(p for p in zones_dir.iterdir() if "decisionzones" in p.name.lower()).read_bytes()
    fm4_ui = {n.lower() for n in zipfile.ZipFile(fm4 / "UI/Textures.zip").namelist()}
    ui_sources = [zipfile.ZipFile(p) for p in UI_ROOTS if Path(p).exists()]
    ui_all = {}
    for media in envs:
        make, donor, fm3_media, ids, join = SOURCES[media]
        source = make()
        settings = _find(fm4 / "tracks" / donor, "TrackSettings.xml").read_bytes()
        ai = {canonical_ai_name(n, media): pad_mlp(d) for n, d in source.ai_files().items()}
        with b:
            info = add_database(a, b, media, ai, fm3_media, ids, join)
        ai_all.update(ai)
        rows = fm3_tracks(a, fm3_media, ids)
        env_row = dict(a.execute("select * from Environments where MediaName=?", (fm3_media,)).fetchone())
        ui = ui_textures(env_row, rows, fm4_ui, ui_sources, environment=not join)
        ui_all.update(ui)
        # Layout names of the FM4 environment a joined one shares (AmalfiGP: "Full Circuit").
        siblings = {ui_names.reference(v) & 65535 for r in b.execute(
            "select DisplayName, ShortDisplayName from Tracks where EnvironmentId=? and MediaName!=?",
            (info["environment"], media)) for v in r} if join else set()
        for k, v in string_additions(rows, None if join else env_row, media, siblings).items():
            wanted[k] += v
        originals = source.track_files()
        track = {n: convert_track_file(n, d, settings) for n, d in originals.items()}
        skies = sorted({track_pvs.sky_model_index(track_pvs.parse(d)) for n, d in originals.items()
                        if n.lower().endswith(".pvs")})
        archives[Path(f"Media/tracks/{media}.zip")] = zip_bytes(track)
        bin_path = files / f"Media/tracks/{media}/bin.zip"
        members, models = write_bin(bin_path, source.bin_members(), skies)
        bins[media] = bin_path
        audio = source.audio_files()
        ribbons = sorted({int(m.group(1)) for n in track for m in [re.match(r"ribbon_(\d+)/", n, re.I)] if m})
        for rib in ribbons:
            if not any(f"ribbon_{rib:02d}/" in n.lower() and "decisionzones" in n.lower() for n in audio):
                audio[f"Ribbon_{rib:02d}/{media.lower()}ribbon_{rib:02d}decisionzones.xml"] = zone_file
        archives[Path(f"Media/audio/tracks/{media}.zip")] = zip_bytes(audio)
        loose.update({Path("Media/audio/tracks") / media / n: d for n, d in audio.items()})
        report[media] = {**info, "ui_textures": sorted(ui), "settings_donor": donor, "models_v5": models, "track_files": len(track),
                         "ai_files": len(ai), "audio_files": len(audio), "bin_members": members}
    for layout in layouts:
        # Layouts on FM4's own geometry (CrownJewel 170): `track_package`'s row and files.
        from contextlib import closing
        from . import converter as cv
        fm3_src, fm4_src = Path(cv.FM3_DEFAULT).resolve(), (fm4 / "DB/gamedb.slt").resolve()
        f3, f4 = fm3_src.parents[1], fm4_src.parents[1]
        with closing(cv.connect(fm3_src)) as s3, closing(cv.connect(fm4_src)) as s4:
            row, _ = track_package.plan_row(s3, s4, layout)
        media = row["MediaName"]
        ribbon, _ = track_package.ribbon_files(track_package.find(f3, "Tracks"), track_package.find(f4, "tracks"),
                                               media, row["RibbonIndex"], row["ReverseIndex"])
        ai, _ = track_package.ai_files(f3 / "AI/Tracks", f4 / "AI/Tracks", media, row["RibbonIndex"])
        audio_dir = track_package.find(track_package.find(track_package.find(f4, "audio"), "Tracks"), media)
        sound, _ = track_package.audio_files(audio_dir, media, row["RibbonIndex"], row["ReverseIndex"])
        for group in (ribbon, sound):
            if group:
                archive, data = track_package.mounted_archive(Path(next(iter(group))).parent, group)
                archives[archive] = data
        ai_all.update({Path(k).relative_to("Media/AI/Tracks").as_posix(): pad_mlp(v) for k, v in ai.items()})
        with b:
            b.execute(f"insert into Tracks ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values()))
        wanted["tracks.str"] += [(ui_names.reference(row["DisplayName"]), f"IDS_DisplayName_{layout}", "tracks.str",
                                  frozenset()),
                                 (ui_names.reference(row["ShortDisplayName"]), f"IDS_ShortDisplayName_{layout}",
                                  "tracks.str", frozenset())]
        report[f"layout_{layout}"] = {"media": media, "ribbon": row["RibbonIndex"], "geometry_ribbon": row["ReverseIndex"]}
    assert b.execute("pragma integrity_check").fetchone()[0] == "ok"
    b.close()
    archives[Path("Media/AI/Tracks.zip")] = zip_bytes(ai_all)
    # One ZIP per UI folder, mounted at that folder (game:\media\ui\textures\UI4\...\).
    folders = {}
    for name, data in ui_all.items():
        folder, filename = name.rsplit("/", 1)
        folders.setdefault(folder, {})[filename] = data
    for folder, entries in folders.items():
        archives[Path("Media/UI/Textures") / f"{folder}.zip"] = zip_bytes(entries)
    # Names: FM3 text per language, on top of the winning FM4 (and DLC) tables.
    fm3 = fm3_string_tables(string_roots or [FM3UC / "StringTables", FM3 / "StringTables"])
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as zout:
        for name, data in sorted(base_names.items()):
            if name.rsplit("/", 1)[-1].lower() not in ("tracks.str", "environments.str"):
                zout.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data)
        for table in ("Tracks.str", "Environments.str"):
            tables, _ = ui_names.winning_tables(fm4, content_root, archive_read, c.sha, table)
            en = fm3[("en", table.lower())]
            for code, (prio, lang, origin, data) in sorted(tables.items()):
                src = fm3.get((code, table.lower()), en)
                target = ui_names.StringTable(data)
                # Keys FM4 already has (LeMans' environment names) are FM4's own text: reused.
                adds = []
                for k, label, origin, siblings in wanted[table.lower()]:
                    if k & 65535 in target.texts:
                        continue
                    text_src = fm3.get((code, origin), fm3[("en", origin)])
                    text = text_src.texts.get(k & 65535) or fm3[("en", origin)].texts[k & 65535]
                    # A name FM4 already shows next to it (an environment's, or a layout's in
                    # the same environment) gets the "(FM3)" mark the cars carry.
                    taken = fm4_env_keys if table == "Environments.str" else siblings
                    if text in {target.texts[e] for e in taken if e in target.texts}:
                        text += " (FM3)"
                    adds.append((k, label, text))
                zout.writestr(zipfile.ZipInfo(f"{lang}/{table}", (1980, 1, 1, 0, 0, 0)), target.add(adds))
    names = stream.getvalue()
    prio_names = max(ui_names.winning_tables(fm4, content_root, archive_read, c.sha, t)[0]["en"][0]
                     for t in ("Tracks.str", "Environments.str")) + 1
    prio_names = max(prio_names, base_priority)
    priorities = {ui_names.OVERRIDE: prio_names, **{p: 80 for p in archives}}
    manifest_src = (Path(base) / "files/Media/zipmanifest.xml") if base else fm4 / "zipmanifest.xml"
    manifest = integration.extend_zip_manifest(manifest_src.read_bytes(), {ui_names.OVERRIDE: names, **archives},
                                               (ui_names.OVERRIDE,) if base_names else (), priorities)
    for media, path in bins.items():
        with open(path, "rb") as f:
            f.seek(-22, 2)
            start, size, count = zip_directory(f.read())
        guest = "\\".join(["game:", "media", "tracks", media.lower(), "bin.zip"])
        entry = (f'<Zip version="1" path="{guest}" priority="80" '
                 f'dirstart="{start}" dirsize="{size}" direntries="{count}" />').encode()
        manifest = manifest.replace(b"</ZipFiles>", entry + b"</ZipFiles>")
    for rel, data in {**archives, **loose, ui_names.OVERRIDE: names, Path("Media/zipmanifest.xml"): manifest}.items():
        (files / rel).parent.mkdir(parents=True, exist_ok=True)
        if (files / rel).exists():
            (files / rel).unlink()   # a hard link to the base package
        (files / rel).write_bytes(data)
    report["names_priority"] = prio_names
    report["accepted"] = False
    report["runtime_tested"] = False
    (Path(out) / "report.json").write_text(json.dumps(report, indent=1))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--content-root", required=True, type=Path)
    ap.add_argument("--env", action="append", choices=sorted(SOURCES))
    ap.add_argument("--base", help="overlay package (e.g. the FM3 cars) to extend")
    a = ap.parse_args(argv)
    report = build(a.out, a.env or sorted(SOURCES), a.content_root, base=a.base)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
