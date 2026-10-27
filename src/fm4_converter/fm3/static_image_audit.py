"""Bind static addresses to local retail XEX input and a freshly decoded image.

Reads bytes only; this module neither executes guest code nor applies updates.
Decoded images and detailed evidence remain private, ignored local artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unpack(data, offset, fmt):
    size=struct.calcsize(fmt)
    if offset < 0 or offset+size > len(data):
        raise ValueError("Header read outside input bounds")
    return struct.unpack_from(fmt,data,offset)[0]


def xex_metadata(data):
    if data[:4] != b"XEX2":
        raise ValueError("Expected XEX2")
    count=unpack(data,20,">I")
    if count > (len(data)-24)//8:
        raise ValueError("Optional header count exceeds input")
    options={}
    for i in range(count):
        key=unpack(data,24+8*i,">I")
        if key in options:
            raise ValueError("Duplicate optional header key")
        options[key]=unpack(data,28+8*i,">I")
    result={"image_base":options.get(0x10201),"entry_point":options.get(0x10100)}
    if 0x40006 in options:
        offset=options[0x40006]
        result["execution"]={
            name:f"{unpack(data,offset+delta,'>I'):08X}"
            for name,delta in (("media_id",0),("version",4),("base_version",8),("title_id",12))}
    return result


def pe_metadata(data):
    if data[:2] != b"MZ":
        raise ValueError("Decoded image has no MZ header")
    pe=unpack(data,0x3C,"<I")
    if data[pe:pe+4] != b"PE\0\0":
        raise ValueError("Decoded image has no PE signature")
    count=unpack(data,pe+6,"<H")
    optional_size=unpack(data,pe+20,"<H")
    optional=pe+24
    magic=unpack(data,optional,"<H")
    if magic != 0x10B:
        raise ValueError("Expected Xbox PE32 image")
    if optional_size < 64:
        raise ValueError("Truncated PE32 optional header")
    image_base=unpack(data,optional+28,"<I")
    section_start=optional+optional_size
    if section_start+40*count > len(data):
        raise ValueError("Truncated PE section table")
    sections=[]
    for i in range(count):
        at=section_start+40*i
        name=data[at:at+8].split(b"\0",1)[0].decode("ascii")
        size=unpack(data,at+8,"<I")
        start=image_base+unpack(data,at+12,"<I")
        flags=unpack(data,at+36,"<I")
        complete=start-image_base+size <= len(data)
        if not complete and (flags & 0x20000000 or name in (".rdata",".pdata",".data")):
            raise ValueError("Code or analysis data section exceeds decoded file")
        sections.append({"name":name,"start":start,"size":size,"executable":bool(flags & 0x20000000)})
    return {"image_base":image_base,"entry_point":image_base+unpack(data,optional+16,"<I"),
            "image_size":unpack(data,optional+56,"<I"),"decoded_file_size":len(data),"sections":sections,
            "incomplete_sections":[{**s,"unavailable_tail_bytes":s["start"]-image_base+s["size"]-len(data)}
                                   for s in sections if s["start"]-image_base+s["size"]>len(data)]}


def audit(xex, image, sections, expected_sha=None, generated_input=None):
    xm=xex_metadata(Path(xex).read_bytes())
    pm=pe_metadata(Path(image).read_bytes())
    source_hash=sha(xex)
    if expected_sha and source_hash != expected_sha:
        raise ValueError("Retail XEX hash does not match expected build")
    if xm["image_base"] != pm["image_base"] or xm["entry_point"] != pm["entry_point"]:
        raise ValueError("XEX and decoded PE base/entry point disagree")
    listed=[]
    for line in Path(sections).read_text().splitlines():
        name,start,size,flags=line.split("\t")
        listed.append({"name":name,"start":int(start),"size":int(size),"executable":bool(int(flags)&2)})
    if listed != pm["sections"]:
        raise ValueError("Decoded PE and section listing disagree")
    result={"source":str(Path(xex).resolve()),"source_sha256":source_hash,
            "image":str(Path(image).resolve()),"image_sha256":sha(image),
            "sections_sha256":sha(sections),"xex":xm,"pe":pm,
            "scope":"Fresh local decoder output; base/entry/section identity and source hashes. Executable/.rdata/.pdata/.data ranges must be complete; any other unavailable ranges are explicitly listed and must not be read. Not a signature check or proof of solver semantics.",
            "guest_code_executed":False,"title_update_applied":False}
    if generated_input:
        result["generated_input"]={"path":str(Path(generated_input).resolve()),
                                   "sha256":sha(generated_input)}
        if result["generated_input"]["sha256"] != source_hash:
            raise ValueError("Generated manifest input is a different executable")
        result["generated_input"]["matches_retail_source"]=True
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xex",type=Path,required=True)
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--sections",type=Path,required=True)
    parser.add_argument("--expected-sha")
    parser.add_argument("--generated-input",type=Path)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.xex,args.image,args.sections,args.expected_sha,args.generated_input)
    with args.out.open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2)
    print(json.dumps({"source_sha256":result["source_sha256"],"image_sha256":result["image_sha256"],
                      "image_base":hex(result["pe"]["image_base"]),"sections":len(result["pe"]["sections"])}))


if __name__=="__main__":
    main()
