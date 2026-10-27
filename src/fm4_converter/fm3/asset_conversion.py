"""Convert local FM3 models with the pinned CPU helper and audit every result.

No game launch, renderer, or GPU API is used by this module.
SPDX-License-Identifier: GPL-3.0-only
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from . import carbin_audit
from . import texture_audit


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_helper(exe):
    exe = Path(exe).resolve()
    record = json.loads((exe.parent/"build.json").read_text(encoding="utf-8"))
    if record.get("reference_commit") != "8807c7d137646dab8d9eecab7e8d5a6602ef58aa":
        raise ValueError("Unreviewed model converter revision")
    if sha(exe.read_bytes()) != record["helper_sha256"]:
        raise ValueError("Model converter executable differs from its build record")
    dll = exe.parent/"MonoGame.Framework.dll"
    if sha(dll.read_bytes()) != record["math_library_sha256"]:
        raise ValueError("CPU math library differs from its build record")
    return record


def convert_texture(data, name):
    """FM3 colour fetch constants -> FM4 gamma/AS_16; pixels stay verbatim.

The two changed bytes match native FM4 Cobalt colour textures. Normal maps
and menu thumbnails retain their original fetch constants.
"""
    filename = Path(name).stem.lower()
    if len(data)<52 or int.from_bytes(data[:4],"big")!=3:
        raise ValueError(f"Unsupported XDS header: {name}")
    if "_nrm" in filename or "normal" in filename or filename.startswith("thumbnail_"):
        return data
    fmt = data[35]&63
    if fmt not in (18,20):
        raise ValueError(f"Colour texture format needs review: {name} ({fmt})")
    result = bytearray(data)
    result[31] = (result[31]&3)|252
    result[35] = (result[35]&192)|(fmt+33)
    return bytes(result)


def convert_payloads(payloads, exe):
    build = check_helper(exe)
    converted, audits = {}, []
    with tempfile.TemporaryDirectory(prefix="fm3-fm4-models-") as temp:
        temp = Path(temp)
        for number,(path,data) in enumerate(sorted(payloads.items())):
            output_path = path
            record = {"source_path":path.as_posix(),"source_sha256":sha(data)}
            if path.suffix.lower()==".carbin":
                # Bound-check before handing bytes to the external parser.
                carbin_audit.parse(data,"FM3")
                source, target = temp/f"{number}.fm3.carbin",temp/f"{number}.fm4.carbin"
                source.write_bytes(data)
                p = subprocess.run([str(Path(exe).resolve()),"convert",str(source),str(target)],
                                   capture_output=True,text=True,timeout=60,check=False)
                if p.returncode:
                    raise ValueError(f"Model conversion failed for {path}: {p.stderr.strip()}")
                result = target.read_bytes()
                record["geometry"] = carbin_audit.audit_conversion(data,result)
                if re.search(r"_(?:caliper|rotor)(?:lf|lr|rf|rr)\.carbin$",path.name,re.I):
                    output_path = path.with_name(path.stem+"_lod0.carbin")
                record["operation"] = "FM3 -> FM4 carbin"
            elif path.suffix.lower()==".xds":
                result = convert_texture(data,path.name)
                record["operation"] = "colour fetch constants" if result!=data else "preserved"
                record["pixel_payload_unchanged"] = result[52:]==data[52:]
                record["texture"] = texture_audit.compare(data, result)
            else:
                result = data
                record["operation"] = "preserved"
            if output_path in converted:
                raise ValueError(f"Converted asset path collision: {output_path}")
            converted[output_path] = result
            record.update(path=output_path.as_posix(),sha256=sha(result),bytes=len(result))
            audits.append(record)
    return converted,{"helper":build,"assets":audits,"runtime_tested":False,
                     "passed":True,"scope":"Model geometry/rig preservation and all XDS mip bounds/pixel preservation"}
