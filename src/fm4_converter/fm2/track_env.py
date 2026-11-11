"""FM2-only track environments (New York, the Test Track) -> FM4 track items (format 2).

FM2's tracks are two generations older than FM4's (track_models): every model is converted
to FM4 models written from FM4 Disc 1's own track models, and the PVS to version 27. The rest
follows the FM3 tracks (fm3.track_env): the lighting from an FM4 track's `TrackSettings.xml`
and `staticCarCubemap.xpr` with the FM3 tracks' caps (FM2's tracks have no SH probes either),
the AI files under FM4's names and padded, FM2's collision, crowd and camera files as they are,
and FM2's own audio with FM4 Infineon's decision zones. FM2's database has no environments:
each FM2 track gets a new FM4 environment.

    python -m fm4_converter.fm2.track_env --out <new folder> --content-root <...\\4D530910\\00000002>
        [--env NewYork --env TestTrackinfield]
"""
import argparse, json, re, shutil, sqlite3, struct, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from . import sources, track_models as tm
from .. import items as it
from ..fm3 import track_env as t3, track_grid, track_pvs, ui_names
from ..fm3.integration import archive_read

# media: (FM2 track folder, FM4 TrackSettings donor, environment name, location, FM4 environment
# whose country, pictures and logos stand in until FM2's are converted).
ENVIRONMENTS = {
    "NewYork": ("newyork", "Tsukuba", "New York", "New York City, USA", "RoadAtlanta"),
    "TestTrackinfield": ("testtrackinfield", "Tsukuba", "Test Track", "Test Track", "RoadAtlanta"),
}
FM2_PRIORITY_LABEL = "FM2"
SPECIAL_CELL_FLAGS = track_pvs.SPECIAL_CELL_FLAGS
CPU_DATA_MIN = 14_000_000      # FM4's own tracks' PVS CPU data size (FM2's New York: 13,000,000)
SKY_TEMPLATE = ("Tsukuba", "Tsukubaout.00006.rmb.bin", "sky_diff_1", 16)
# FM2's ribbons have no pre-race cameras; FM3's and FM4's do. The Alps' shots are all relative to
# the car or its parts (CarSpace, PartSpace, BoundingBoxSpace), so they fit any track.
PRERACE_DONOR, PRERACE_CAMS = "Alps", "preracecams.xml"


def _find(folder, name):
    return next(p for p in Path(folder).iterdir() if p.name.lower() == name.lower())


def _maybe(folder, name):
    return next((p for p in Path(folder).iterdir() if p.name.lower() == name.lower()), None)


# --- templates --------------------------------------------------------------------------------

def template_cells(fm4_tracks, spec):
    """The model instance (l36 cell) of a template model in its track's ribbons (an ordinary
    cell before a special one)."""
    track, name = spec[0], spec[1]
    number = int(name.split(".")[1])
    folder = _find(fm4_tracks, track)
    found = []
    for pvs in sorted(folder.glob("*/*.pvs")):
        p = track_pvs.parse(pvs.read_bytes())
        found += [c for c in p["l36"] + p["l68"] if c["u0"] == number]
    if not found:
        raise tm.FormatError(f"{track} {name}: no model instance")
    return dict(sorted(found, key=lambda c: c["u4"] == SPECIAL_CELL_FLAGS)[0])


class Templates:
    """The FM4 template models, their shader files and their instance records."""

    def __init__(self, fm4_media):
        tracks = _find(fm4_media, "tracks")
        self.models, self.shaders = tm.load_templates(tracks)
        specs = dict(tm.TEMPLATES, sky=SKY_TEMPLATE)
        z = zipfile.ZipFile(_find(_find(tracks, SKY_TEMPLATE[0]), "bin.zip"))
        self.models["sky"] = tm.Template(archive_read(z, SKY_TEMPLATE[1]), SKY_TEMPLATE[2], SKY_TEMPLATE[3])
        member = next(n for n in z.namelist() if n.lower() == f"shaders/track/{SKY_TEMPLATE[2]}.fxobj")
        self.shaders[member] = archive_read(z, member)
        self.cells = {kind: template_cells(tracks, spec) for kind, spec in specs.items()}
        self.techniques = {kind: spec[2] for kind, spec in specs.items()}


# --- geometry ---------------------------------------------------------------------------------

def roles(draw, textures, model_textures):
    """(diffuse, lightmap) PVS list indices of a draw: the lightmap is the bound texture with the
    lightmap flag; the diffuse the bound colour texture on the lowest sampler (else any other
    bound texture, else the model's first non-lightmap texture)."""
    bound = sorted(draw.samplers.items())
    flags = lambda i: textures[model_textures[i]][6] if i < len(model_textures) else 0
    lightmap = next((i for _, i in bound if i < len(model_textures) and flags(i) & tm.LIGHTMAP_FLAG), None)
    others = [i for _, i in bound if i < len(model_textures) and not flags(i) & tm.LIGHTMAP_FLAG]
    colour = [i for i in others if flags(i) & tm.COLOUR_FLAG]
    if colour or others:
        return (colour or others)[0], lightmap
    rest = [i for i in range(len(model_textures)) if not flags(i) & tm.LIGHTMAP_FLAG]
    return (rest[0] if rest else None), lightmap


def convert_models(fm2_bin, ribbons, templates, prefix):
    """(objects, bin.zip members {name: bytes}): every FM2 model's draws as FM4 models
    `<prefix>.NNNNN.rmb.bin` numbered as the PVS objects, the sky's last, and per object
    {kind, model, draw, bounds, diffuse, lightmap} (PVS list indices of the first ribbon)."""
    first = ribbons[0]
    textures = first["textures"]
    z = zipfile.ZipFile(fm2_bin)
    names = {n.lower(): n for n in z.namelist()}
    objects, members = [], {}

    def add(draw, model_textures, kind=None):
        diffuse, lightmap = roles(draw, textures, model_textures)
        if kind is None:
            kind, data, bounds = tm.fm4_model(draw, templates.models, lightmap)
        else:
            data, bounds = sky_model(draw, templates.models[kind])
        members[f"{prefix}.{len(objects):05d}.rmb.bin"] = data
        objects.append(dict(kind=kind, model=draw.model, draw=draw.number, bounds=bounds,
                            diffuse=diffuse, lightmap=lightmap if kind in ("opaque", "two_sided", "alpha_test") else None))

    skipped = 0
    for number, record in enumerate(first["models"]):
        name = names.get(f"{prefix}.{number:05d}.rmb.bin".lower())
        if name is None:
            raise tm.FormatError(f"{prefix}.{number:05d}.rmb.bin missing")
        for draw in tm.draws(tm.Model(archive_read(z, name)), number):
            if draw is None:
                skipped += 1
                continue
            add(draw, record["textures"])
    sky_name = names.get(f"{prefix}.sky.rmb.bin".lower())
    sky = []
    if sky_name:
        for draw in tm.draws(tm.Model(archive_read(z, sky_name)), -1):
            if draw is not None:
                sky.append(len(objects))
                add(draw, first["sky"][1]["textures"], kind="sky")
    # Colour and lightmap textures of every ribbon's table get FM4's gamma (track_models.with_gamma).
    gamma = {t[1]: t[0] for r in ribbons for t in r["textures"] if t[6] & (tm.COLOUR_FLAG | tm.LIGHTMAP_FLAG)}
    gamma.update({r["textures"][i][1]: r["textures"][i][0] for r in ribbons for i in r["sky"][1]["textures"]})
    singles = {f"_0x{build:08x}.bin" for build in gamma.values()}
    for name in z.namelist():
        low = name.lower()
        if low.endswith(".rmb.bin") or low.endswith(".htm"):
            continue
        data = archive_read(z, name)
        if low.endswith(".stx.bin"):
            data = tm.with_gamma(data, set(gamma))
        elif low in singles:
            data = tm.with_gamma(data)
        members[name] = data
    members.update(templates.shaders)
    return objects, sky, members, skipped


def sky_model(draw, template):
    """FM4 sky model (stride 16: position and texture coordinates) of one FM2 sky draw."""
    words, uvos = tm.uv_words(draw.uv0)
    v = np.zeros((len(draw.positions), 4), ">u4")
    v[:, 0:3] = draw.positions.astype(">f4").view(">u4")
    v[:, 3] = words
    lo, hi = tuple(map(float, draw.positions.min(0))), tuple(map(float, draw.positions.max(0)))
    return template.build(v.tobytes(), draw.indices, (lo, hi), uvos), (lo, hi)


def half(v):
    return int(np.float16(v).view(np.uint16))


def pvs27(p, objects, sky, templates, skybox_slot, w3=t3.PVS_W3):
    """FPVS v27 of one ribbon: FM2's zones and texture table, one PVS model and one model
    instance an object (FM2's positions are world space: an identity instance), the sky
    objects in every zone and the first of them as FM4's special sky cell."""
    model_textures = p["models"]
    sky_textures = p["sky"][1]["textures"]
    techniques = sorted({templates.techniques[o["kind"]] for o in objects})
    shader_names = ["shaders\\track\\" + t for t in techniques]
    by_model = {}
    for number, o in enumerate(objects):
        by_model.setdefault(o["model"], []).append(number)
    l36, l52 = [], []
    for number, o in enumerate(objects):
        own = sky_textures if o["kind"] == "sky" else model_textures[o["model"]]["textures"]
        refs = [own[o["diffuse"]] if o["diffuse"] is not None else (own[0] if own else 0)]
        if o["lightmap"] is not None:
            refs.append(own[o["lightmap"]])
        lo, hi = np.array(o["bounds"][0]), np.array(o["bounds"][1])
        centre, size = (lo + hi) / 2, (hi - lo) / 2
        l52.append({"refs": refs, "ids": [techniques.index(templates.techniques[o["kind"]])],
                    "mat": (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0,
                            *map(float, centre), 1.0),
                    "vec": (*map(float, size), 0.0)})
        cell = dict(templates.cells[o["kind"]])
        cell.update(u0=number, u8=0, u12=0xFFFFFFFF, f40=(0.0, 0.0, 0.0),
                    u52=(half(1), 0, 0, 0, half(1), 0, 0, 0, half(-1)), v16=(0.0, 0.0, 0.0, 0.0))
        l36.append(cell)
    special = None
    if sky:
        special = len(l36)
        l36.append({**l36[sky[0]], "u0": sky[0], "u4": SPECIAL_CELL_FLAGS})
    zones = []
    for zone in p["zones"]:
        inst = sorted({n for m in zone["models"] for n in by_model.get(m, ())} | set(sky))
        zones.append((inst, inst, list(zone["textures"]), list(zone["flags"])))
    textures = [t[:2] + (abs(t[2]),) + t[3:] if t[6] & tm.LIGHTMAP_FLAG else t for t in p["textures"]]
    q = {"ver": 27, "w2": max(p["cpu"], CPU_DATA_MIN), "w3": w3, "h0": 0, "h2": p["h2"], "l4": zones,
         "l20": textures, "l172": shader_names, "l36": l36, "l52": l52,
         "a84": ([track_pvs.NONE] * skybox_slot + [special]) if special is not None else [],
         "a100": ([track_pvs.NONE] * skybox_slot + [sky[0]]) if special is not None else [],
         "a116": [sky[0]] if special is not None else [],
         "l68": [], "s132": p["name"], "b160": 1, "b196": 0, "l200": [], "l192": [[0] * len(z[0]) for z in zones]}
    if len(l36) > 0xFFFF:
        raise tm.FormatError("too many model instances for 16-bit zone lists")
    return track_pvs.write(q)


# --- cameras ----------------------------------------------------------------------------------

def segment_cams(fm2_xml, donor_xml):
    """`TrackSegCams.xml` (the replay and post-race TV cameras) in FM4's format from FM2's.

    FM2's file is an older format (a `TrackSegCams` root, keys under `Keys`, a playback time and
    no `NumCams`), which FM4 reads as garbage: the post-race screen read a null camera
    (sub_8268D4F8). FM4's own cameras are all `Animateable`: each of FM2's animated cameras keeps
    its cut, position and rotation types, flags and keys (spread over its playback time), in the
    frame of the donor's first camera (post effects, fades, camera physics); FM2's bumper, hood
    and wheel cuts are left out. Cuts before the start line wrap to the end of the lap."""
    donor = ET.fromstring(donor_xml)
    frame = donor.find("Cam")
    out = ET.Element("Cams", CutQueueType="TrackSeg")
    cams = []
    for cam in ET.fromstring(fm2_xml).findall("Cam"):
        anim = cam.find("Anim")
        keys = anim.findall("Keys/Key") if anim is not None else []
        if cam.get("Type") != "Animateable" or not keys:
            continue
        cut = float(cam.get("StartCut", "0")) % 1.0
        cams.append((cut, cam, anim, keys))
    flag = lambda v: "1" if (v or "").lower() == "true" else "0"
    for cut, cam, anim, keys in sorted(cams, key=lambda c: c[0]):
        new = ET.fromstring(ET.tostring(frame))
        new.set("StartCut", f"{cut:.6f}")
        new.set("CameraManShakeOn", flag(cam.get("CameraManShakeOn")))
        new.set("AutoZoomOn", flag(cam.get("AutoZoomOn")))
        new.set("AutoZoomScale", cam.get("AutoZoomScale", "1.000000"))
        a = new.find("Anim")
        for k in list(a):
            a.remove(k)
        a.set("PosAnimType", anim.get("PosAnimType", "WorldSpace"))
        a.set("RotAnimType", anim.get("CamRotType", "TargetCar"))
        a.set("EaseIn", f"{float(anim.get('EaseInPos', '0')):.6f}")
        a.set("EaseOut", f"{1.0 - float(anim.get('EaseOutPos', '1')):.6f}")
        a.set("NumKeys", str(len(keys)))
        span = float(anim.get("PlaybackTime", "0"))
        for i, key in enumerate(keys):
            t = span * i / (len(keys) - 1) if len(keys) > 1 else 0.0
            attrs = {"Time": f"{t:.6f}"}
            attrs.update({n: key.get(n, "0.000000") for n in ("PosX", "PosY", "PosZ", "Yaw", "Pitch", "Roll", "FOV")})
            attrs["TimeC0"] = "0"
            ET.SubElement(a, "Key", attrs)
        out.append(new)
    out.set("NumCams", str(len(out)))
    return b"\n" + ET.tostring(out, encoding="utf-8")


# --- audio ------------------------------------------------------------------------------------

def shared_event(name):
    """FM4's shared-bank event for an FM2 positioned sound, or None: FM2's crowds and reflections
    have FM4 counterparts in `SharedDynamicAudio` and `SharedStaticAudio`; its city sounds do not."""
    up = name.upper()
    m = re.fullmatch(r"CRWD_(LRG|MED)_(\d+)", up)
    if m:
        return ("dynamic", f"CRWD_{m.group(1)}_{(int(m.group(2)) - 1) % 2 + 1}")
    m = re.fullmatch(r"CRWD_SML_(\d+)", up)
    if m:
        return ("dynamic", f"CRWD_SMALL_{(int(m.group(1)) - 1) % 3 + 1}")
    m = re.fullmatch(r"CRWD_CHEER_(\d+)", up)
    if m:
        return ("dynamic", "Crwd_OneShot_" + "ABCD"[(int(m.group(1)) - 1) % 4])
    if up.startswith("REF_OVERPASS"):
        return ("static", "REF_OVERPASS_1")
    if up.startswith("REF_FLAG"):
        return ("static", "REF_FLAGGERSTATION_1")
    return None


def audio_xml(fm2_xml, donor_xml):
    """A ribbon's `TrackAudio` for FM4 from FM2's: FM2's file is an older format (lower-case
    attribute names, an FMOD bank of FEV version 0x21 and FSB3, which FM4's FMOD does not read),
    so the donor's file is the frame, its own positioned sounds (the announcer, the donor's
    crowds and reflections) are dropped, and FM2's crowds and reflections are placed at their
    FM2 positions with FM4's shared events (`shared_event`)."""
    donor = ET.fromstring(donor_xml)
    fm2 = ET.fromstring(fm2_xml)
    for section in (donor.find("Track3D"), donor.find("Track2D")):
        if section is not None:
            for child in list(section):
                section.remove(child)
    static = donor.find("SharedAudio/Shared3D")
    dynamic = donor.find("SharedAudioDynamic/Shared3D")
    for target in (static, dynamic):
        if target is not None:
            for child in list(target):
                target.remove(child)
    track3d = fm2.find("Track3D")
    for obj in (track3d if track3d is not None else []):
        attrs = {k.lower(): v for k, v in obj.attrib.items()}
        mapped = shared_event(attrs.get("eventname", ""))
        target = static if mapped and mapped[0] == "static" else dynamic if mapped else None
        if target is None:
            continue
        new = ET.SubElement(target, "Object", objectName=attrs.get("objectname", mapped[1]), eventName=mapped[1])
        for child in obj:
            ET.SubElement(new, child.tag, dict(child.attrib))
    return ET.tostring(donor, encoding="utf-8")


def audio_files(fm2_folder, donor_folder, media):
    """{path under Audio/Tracks/<media>: bytes}: the donor's FMOD bank (the ribbons' soundbank
    names it, and FM4 opens `<media folder>/<soundbank>.fev`) and one ribbon file an FM2 ribbon."""
    donor_xml = next(donor_folder.glob("*/*ribbon_00.xml")).read_bytes()
    out = {p.name: p.read_bytes() for p in donor_folder.iterdir() if p.suffix.lower() in (".fev", ".fsb")}
    if fm2_folder is not None:
        for p in sorted(fm2_folder.glob("*/*.xml")):
            m = re.fullmatch(r"(?i).*ribbon_(\d+)\.xml", p.name)
            if m:
                rib = int(m.group(1))
                out[f"Ribbon_{rib:02d}/{media.lower()}Ribbon_{rib:02d}.xml"] = audio_xml(p.read_bytes(), donor_xml)
    return out


# --- database ---------------------------------------------------------------------------------

def fm2_tracks(fm2_db, media):
    return [dict(r) for r in fm2_db.execute("select * from Tracks where MediaName=? order by id", (media,))]


def ui_paths(row):
    """{texture path under Media/UI/Textures: the row's GAME: path} of a layout's logo and mini map:
    FM2's are `.xds` files of its `UI/Textures.zip` with the same Xenos header as FM3's and FM4's,
    named `.tga` in the database as FM4's are."""
    out = {}
    for field in ("Logo", "MiniRibbonPath"):
        value = row.get(field) or ""
        rel = value.replace(chr(92), "/").split("Textures/", 1)[-1].rsplit(".", 1)[0] + ".xds"
        if value:
            out[rel] = value
    return out


def ui_textures(tracks, source):
    """{texture path: .xds bytes} of FM2's logos and mini maps of `tracks` (rows), from FM2's
    `UI/Textures.zip` (`source`, a ZipFile); paths it lacks are left out."""
    names = {n.lower(): n for n in source.namelist()}
    out = {}
    for t in tracks:
        for rel in ui_paths(t):
            hit = names.get(rel.lower())
            if hit:
                out[hit] = archive_read(source, hit)
    return out


def add_database(fm2_db, b, media, ai, names, stand_in, ui=frozenset()):
    """Environment, time of day, Tracks, StartGridPositions, FlyingStartPositions and SplitPoints
    of one FM2 environment into the FM4 database `b`. FM2's grids are FM3's format (12 world
    positions, track_grid); its flying starts get new IDs (FM4 uses FM2's for other tracks)."""
    if b.execute("select 1 from Environments where MediaName=?", (media,)).fetchone():
        raise ValueError(f"FM4 already has environment {media}")
    template = dict(b.execute("select * from Environments where MediaName=?", (stand_in,)).fetchone())
    env = b.execute("select max(Id)+1 from Environments").fetchone()[0]
    row = dict(template)
    row.update(Id=env, MediaName=media, ShowOnMap=0, MapX=0.0, MapY=0.0, **names)
    b.execute(f"insert into Environments ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values()))
    tod = dict(b.execute("select * from EnvironmentTimeOfDay where EnvironmentId=4 and TimeOfDayIndex=0").fetchone())
    tod.update(Id=b.execute("select max(Id)+1 from EnvironmentTimeOfDay").fetchone()[0], EnvironmentId=env)
    b.execute(f"insert into EnvironmentTimeOfDay ({','.join(tod)}) values ({','.join('?' * len(tod))})",
              list(tod.values()))
    cols = [r[1] for r in b.execute("pragma table_info(Tracks)")]
    defaults = dict(b.execute("select * from Tracks where MediaName=?", (stand_in,)).fetchone())
    pits = {r[0] for r in b.execute("select id from PittingProfiles")}
    tracks = fm2_tracks(fm2_db, media)
    lower = {n.lower() for n in ai}
    reverse = {t["id"]: f"{media}_{t['RibbonIndex']:02d}_r.geo".lower() in lower for t in tracks}
    grid_ids, grids, flying = {}, {}, {}
    for t in tracks:
        gid = t["DefaultStartGridPositionsId"]
        if gid not in grid_ids:
            new = gid if not b.execute("select 1 from StartGridPositions where id=?", (gid,)).fetchone() \
                else b.execute("select max(id)+1 from StartGridPositions").fetchone()[0]
            geo_name = f"{media}_{t['RibbonIndex']:02d}{'_r' if reverse[t['id']] else ''}.geo".lower()
            geo = next(d for n, d in ai.items() if n.lower() == geo_name)
            rows = track_grid.convert(new, fm2_db.execute("select * from StartGridPositions where id=?", (gid,)).fetchone(),
                                      track_grid.geo(geo))
            b.executemany("insert into StartGridPositions values (?,?,?,?,?)", rows)
            grid_ids[gid], grids[new] = new, len(rows)
        fid = t["FlyingStartPosId"]
        if fid not in flying:
            source = fm2_db.execute("select * from FlyingStartPositions where id=?", (fid,)).fetchone()
            if source is None:
                flying[fid] = fid
            else:
                new = b.execute("select max(id)+1 from FlyingStartPositions").fetchone()[0]
                values = dict(source)
                values["id"] = new
                b.execute(f"insert into FlyingStartPositions ({','.join(values)}) values ({','.join('?' * len(values))})",
                          list(values.values()))
                flying[fid] = new
    used = {r[0] for r in b.execute("select MPSortOrder from Tracks")}
    start = (max(used) // 100 + 1) * 100
    low = min(t["MPSortOrder"] for t in tracks)
    for t in tracks:
        if b.execute("select 1 from Tracks where id=?", (t["id"],)).fetchone():
            raise ValueError(f"FM4 already has track {t['id']}")
        row = {k: t.get(k, defaults[k]) for k in cols}
        own = {rel.lower(): value for rel, value in ui_paths(t).items()}
        logo = next((v for r, v in own.items() if "/l_trk_" in r and r in ui), None)
        ribbon = next((v for r, v in own.items() if "mini_track_ribbons" in r and r in ui), None)
        row.update(Logo=logo or defaults["Logo"], LogoSmall=logo or defaults["LogoSmall"],
                   MiniRibbonPath=ribbon or defaults["MiniRibbonPath"],
                   IsRealWorld=0, IsReverse=int(reverse[t["id"]]), IsHomespace=0, Active=1, ContentId=0,
                   IsPurchased=1, IsInstalled=1, CarsPerUniverse=0, Renderable=1, StartLine=0.0, FinishLine=1.0,
                   XMirror321=0, RibbonConfiguration=0, QuickRaceLapCountKinect=1, RichPresence=70,
                   SatImageName=str(t["id"]), EnvironmentId=env, MediaName=media,
                   MPSortOrder=start + t["MPSortOrder"] - low,
                   DefaultStartGridPositionsId=grid_ids[t["DefaultStartGridPositionsId"]],
                   FlyingStartPosId=flying[t["FlyingStartPosId"]],
                   MPPitProfile=t["MPPitProfile"] if t["MPPitProfile"] in pits else 100)
        b.execute(f"insert into Tracks ({','.join(cols)}) values ({','.join('?' * len(cols))})", [row[k] for k in cols])
    ids = [t["id"] for t in tracks]
    nxt = b.execute("select max(ID)+1 from SplitPoints").fetchone()[0]
    marks = ",".join("?" * len(ids))
    for tid, split in fm2_db.execute(f"select TrackId, Split from SplitPoints where TrackId in ({marks}) "
                                     "order by TrackId, Split", ids):
        b.execute("insert into SplitPoints (ID, TrackId, Split) values (?,?,?)", (nxt, tid, split))
        nxt += 1
    return {"environment": env, "tracks": ids, "grids": grids}


def track_keys(rows):
    """fm3.track_env.track_keys plus the flying start positions the tracks refer to."""
    specs = t3.track_keys(rows)
    tracks = [n for n, r in enumerate(rows) if r["table"] == "Tracks"]
    for n, r in enumerate(rows):
        if r["table"] == "FlyingStartPositions":
            refs = [[t, "FlyingStartPosId"] for t in tracks if rows[t]["row"]["FlyingStartPosId"] == r["row"]["id"]]
            specs.append(it.key_spec("FlyingStartPositions", "id", [n], refs))
    return specs


# --- strings ----------------------------------------------------------------------------------

def fm2_tables(fm2_media):
    """{language code: StringTable} of FM2's Tracks.str."""
    out = {}
    for p in sorted(Path(fm2_media, "StringTables").glob("*.zip")):
        with zipfile.ZipFile(p) as z:
            hit = next((n for n in z.namelist() if n.lower() == "tracks.str"), None)
            if hit:
                try:
                    out[p.stem.lower()] = ui_names.StringTable(archive_read(z, hit))
                except Exception:
                    pass
    return out


def strings(record, tables, env_names, tracks_page):
    """Item strings: FM2's layout names (Tracks.str, on FM4's page of that table: FM2's references
    are on another) and the environment's names."""
    rows = record["rows"]
    for n, r in enumerate(rows):
        if r["table"] == "Tracks":
            for field in ("DisplayName", "ShortDisplayName"):
                key = ui_names.reference(r["row"][field]) & 65535
                texts = {code: t.texts[key] for code, t in tables.items() if key in t.texts}
                texts["*"] = texts.get("en") or next(iter(texts.values()))
                record["strings"].append(it.string("Tracks.str", f"_&{(tracks_page << 16) | key}",
                                                   f"IDS_{field}_{r['row']['id']}", texts, [[n, field]]))
        elif r["table"] == "Environments":
            for field, text in env_names.items():
                record["strings"].append(it.string("Environments.str", r["row"][field],
                                                   f"IDS_{field}_FM2_{r['row']['MediaName']}", {"*": text}, [[n, field]]))


# --- build ------------------------------------------------------------------------------------

def build(out, envs, content_root, fm2_media=None, fm4=None, progress=None):
    """One overlay (`out/files`, the stage of fm4_converter.cli) with the FM2 environments `envs`;
    returns the report with the items (format 2)."""
    fm2_media = Path(fm2_media or sources.FM2_MEDIA)
    fm4 = Path(fm4 or Path(sources.FM4_CARS).parent)
    files = Path(out) / "files"
    if Path(out).exists():
        raise SystemExit("Choose a new package directory")
    db_path = files / "Media/DB/gamedb.slt"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fm4 / "DB/gamedb.slt", db_path)
    a = sqlite3.connect(f"file:{fm2_media / 'DB/gamedb.slt'}?mode=ro", uri=True)
    a.row_factory = sqlite3.Row
    b = sqlite3.connect(db_path)
    b.row_factory = sqlite3.Row
    templates = Templates(fm4)
    tables = fm2_tables(fm2_media)
    zones_dir = _find(_find(fm4 / "audio/tracks", t3.DECISION_ZONES_DONOR[0]), t3.DECISION_ZONES_DONOR[1])
    zone_file = next(p for p in zones_dir.iterdir() if "decisionzones" in p.name.lower()).read_bytes()
    ui_zip = _maybe(_find(fm2_media, "UI"), "Textures.zip")
    ui_source = zipfile.ZipFile(ui_zip) if ui_zip else None
    ui_all = {}
    env_page = ui_names.reference(b.execute("select DisplayName from Environments limit 1").fetchone()[0]) >> 16
    tracks_page = ui_names.reference(b.execute("select DisplayName from Tracks limit 1").fetchone()[0]) >> 16
    recorder, records, report, ai_all = it.Recorder(b), [], {}, {}
    archives, loose = {}, {}
    for number, media in enumerate(envs, 1):
        if progress:
            progress(dict(index=number, total=len(envs), track=media))
        folder_name, donor, env_name, location, stand_in = ENVIRONMENTS[media]
        folder = _find(_find(fm2_media, "tracks"), folder_name)
        settings = _find(fm4 / "tracks" / donor, "TrackSettings.xml").read_bytes()
        cubemap = _find(fm4 / "tracks" / donor, t3.CUBEMAP).read_bytes()
        key = folder_name.lower() + "_"
        ai_folder = _find(_find(fm2_media, "AI"), "Tracks")
        # The line files and, in Level1 to Level3 and SegmentProfiles, the per-level AI data FM4 loads
        # as `AI\Tracks\Level%d\<track>.bin` (without them it reads a null level when the AI
        # drivers are made: guest null read in sub_82A94158 on the pre-race screen).
        ai = {t3.canonical_ai_name(p.relative_to(ai_folder).as_posix(), media): t3.pad_mlp(p.read_bytes())
              for p in ai_folder.rglob("*") if p.is_file() and p.name.lower().startswith(key)}
        # Geometry and the PVS of each ribbon.
        pvs_files = sorted(p for p in folder.rglob("*") if p.suffix.lower() == ".pvs")
        ribbons = [tm.pvs11(p.read_bytes()) for p in pvs_files]
        if not ribbons:
            raise ValueError(f"{media}: no PVS")
        if any(len(r["models"]) != len(ribbons[0]["models"]) or r["name"] != ribbons[0]["name"] for r in ribbons):
            raise ValueError(f"{media}: ribbons list different models")
        prefix = ribbons[0]["name"]
        objects, sky, members, skipped = convert_models(_find(folder, "bin.zip"), ribbons, templates, prefix)
        slot = t3.skybox_index(settings) or 0
        track = {}
        for p in folder.rglob("*"):
            if not p.is_file() or p.name.lower() == "bin.zip":
                continue
            rel = p.relative_to(folder).as_posix()
            if p.suffix.lower() == ".pvs":
                track[rel] = pvs27(ribbons[pvs_files.index(p)], objects, sky, templates, slot)
            elif p.name.lower() == "tracksettings.xml":
                track[rel] = t3.light_settings(settings, p.read_bytes())
            elif p.name.lower() == t3.CUBEMAP:
                track[rel] = cubemap
            else:
                track[rel] = p.read_bytes()
        seg_donor = next(p for p in _find(fm4 / "tracks", donor).glob("*/*")
                         if p.name.lower() == "tracksegcams.xml").read_bytes()
        for name in [n for n in track if n.lower().endswith("/tracksegcams.xml")]:
            track[name] = segment_cams(track[name], seg_donor)
        prerace = next(p for p in _find(fm4 / "tracks", PRERACE_DONOR).glob("*/*")
                       if p.name.lower() == PRERACE_CAMS).read_bytes()
        for rib in sorted({n.split("/")[0] for n in track if "/" in n and n.lower().startswith("ribbon_")}):
            if not any(n.lower() == f"{rib}/{PRERACE_CAMS}".lower() for n in track):
                track[f"{rib}/{PRERACE_CAMS}"] = prerace
        if not any(n.lower() == "tracksettings.xml" for n in track):
            track["TrackSettings.xml"] = t3.light_settings(settings)
        if not any(n.lower() == t3.CUBEMAP for n in track):
            track["staticCarCubemap.xpr"] = cubemap
        archives[Path(f"Media/tracks/{media}.zip")] = t3.zip_bytes(track)
        bin_path = files / f"Media/tracks/{media}/bin.zip"
        bin_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(bin_path, "w", compression=zipfile.ZIP_STORED) as z:
            for name, data in members.items():
                z.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data)
        audio_folder = _maybe(_find(_find(fm2_media, "Audio"), "Tracks"), folder_name)
        audio = audio_files(audio_folder, _find(fm4 / "audio/tracks", donor), media)
        ribbon_numbers = sorted({int(m.group(1)) for n in list(track) + list(audio)
                                 for m in [re.match(r"ribbon_(\d+)/", n, re.I)] if m})
        for rib in ribbon_numbers:
            if not any(f"ribbon_{rib:02d}/" in n.lower() and "decisionzones" in n.lower() for n in audio):
                audio[f"Ribbon_{rib:02d}/{media.lower()}ribbon_{rib:02d}decisionzones.xml"] = zone_file
        archives[Path(f"Media/audio/tracks/{media}.zip")] = t3.zip_bytes(audio)
        loose.update({Path("Media/audio/tracks") / media / n: d for n, d in audio.items()})
        ai_all.update(ai)
        refs = {field: f"_&{(env_page << 16) | k}" for k, field in enumerate(
            ("Location", "DisplayName", "ShortDisplayName", "Description"), 1)}
        ui = ui_textures(fm2_tracks(a, media), ui_source) if ui_source else {}
        ui_all.update(ui)
        recorder.start()
        with b:
            info = add_database(a, b, media, ai, refs, stand_in, {n.lower() for n in ui})
        added, _ = recorder.take()
        entry = it.item(f"environment:{media}", "environment", media,
                        identity={"environments": [media], "tracks": list(info["tracks"])})
        entry.update(rows=added, renumber=track_keys(added))
        strings(entry, tables, {"Location": location, "DisplayName": env_name, "ShortDisplayName": env_name,
                                "Description": location}, tracks_page)
        entry["files"].update({f"Media/tracks/{media}.zip": 80, f"Media/tracks/{media}/bin.zip": 80,
                               f"Media/audio/tracks/{media}.zip": 80,
                               **{(Path("Media/audio/tracks") / media / n).as_posix(): None for n in audio}})
        entry["members"]["Media/AI/Tracks.zip"] = sorted(ai)
        for name in ui:
            folder, filename = name.rsplit("/", 1)
            entry["members"].setdefault(f"Media/UI/Textures/{folder}.zip", []).append(filename)
        records.append(entry)
        kinds = {}
        for o in objects:
            kinds[o["kind"]] = kinds.get(o["kind"], 0) + 1
        report[media] = {**info, "objects": len(objects), "kinds": kinds, "sky": len(sky), "skipped_draws": skipped,
                         "settings_donor": donor, "track_files": len(track), "ai_files": len(ai),
                         "audio_files": len(audio), "bin_members": len(members)}
    recorder.close()
    assert b.execute("pragma integrity_check").fetchone()[0] == "ok"
    b.close()
    archives[Path("Media/AI/Tracks.zip")] = t3.zip_bytes(ai_all)
    folders = {}
    for name, data in ui_all.items():
        folder, filename = name.rsplit("/", 1)
        folders.setdefault(folder, {})[filename] = data
    for folder, entries in folders.items():
        archives[Path("Media/UI/Textures") / f"{folder}.zip"] = t3.zip_bytes(entries)
    for rel, data in {**archives, **loose}.items():
        (files / rel).parent.mkdir(parents=True, exist_ok=True)
        (files / rel).write_bytes(data)
    report["items"] = records
    (Path(out) / "report.json").write_text(json.dumps({k: v for k, v in report.items() if k != "items"}, indent=1))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--content-root", type=Path)
    ap.add_argument("--fm2-media", type=Path)
    ap.add_argument("--fm4-media", type=Path)
    ap.add_argument("--env", action="append", choices=sorted(ENVIRONMENTS))
    a = ap.parse_args(argv)
    report = build(a.out, a.env or sorted(ENVIRONMENTS), a.content_root, a.fm2_media, a.fm4_media)
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, indent=1))


if __name__ == "__main__":
    main()
