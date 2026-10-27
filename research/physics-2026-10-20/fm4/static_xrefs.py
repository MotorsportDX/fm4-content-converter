"""Locate strings and candidate PowerPC lis/addi references in an existing image, without execution.

Only a convenience cross-reference scan: disassembly/data-flow review is required.
The image is an existing workspace artifact, not authenticated to a disc by this script.
"""
from fm4_converter.paths import PHYSICS_RESEARCH_OUTPUT
from pathlib import Path
import struct,re,hashlib,json
OUT=PHYSICS_RESEARCH_OUTPUT / 'fm4'
OUT.mkdir(parents=True, exist_ok=True)
WORK=OUT.parents[2]/'work/fm4'
p=WORK/'loaded-image.bin';b=p.read_bytes();base=0x82000000
secs=[(x[0],int(x[1]),int(x[2]),int(x[3])) for x in [l.split('\t') for l in (WORK/'sections.tsv').read_text().splitlines()]]
needles=['CarPhysicsUpdateHz','game:\\Media\\Physics\\PhysicsSettings.ini','SELECT * FROM List_TireFrictionCurve WHERE FrictionCurveID=','MinLoadCurve','game:\\media\\Tracks\\%s\\Ribbon_%02d\\%s_track_%02d.col']
r=[]
for needle in needles:
    off=b.find(needle.encode())
    if off<0:continue
    addr=base+off;hi=((addr+0x8000)>>16)&0xffff;lo=addr&0xffff;hits=[]
    for sec,st,sz,fl in secs:
        if not fl&2:continue
        for o in range(st-base,st-base+sz-4,4):
            w=struct.unpack_from('>I',b,o)[0]
            if w>>26!=15 or (w>>16)&31!=0 or w&65535!=hi:continue
            reg=(w>>21)&31
            for q in range(o+4,min(o+100,st-base+sz-4),4):
                w2=struct.unpack_from('>I',b,q)[0]
                if w2>>26==15 and (w2>>21)&31==reg:break
                if w2>>26==14 and (w2>>16)&31==reg and w2&65535==lo:
                    hits.append({'lis':hex(base+o),'addi':hex(base+q),'register':reg,'instructions':[hex(w),hex(w2)]})
    datarefs=[hex(base+m.start()) for m in re.finditer(re.escape(addr.to_bytes(4,'big')),b)]
    r.append({'string':needle,'offset':hex(off),'address_assuming_base_82000000':hex(addr),'lis_addi_candidates':hits,'literal_pointer_candidates':datarefs})
(OUT/'static_xrefs.json').write_text(json.dumps({'image':str(p.resolve()),'sha256':hashlib.sha256(b).hexdigest(),'provenance':'Existing workspace image; loader source and section list inspected but not re-extracted or provenance matched to retail XEX in this subtask. Static candidates only.','results':r},indent=2),encoding='utf-8')
(OUT/'xref_addresses.txt').write_text('\n'.join(sorted(set(x['addi'][2:] for a in r for x in a['lis_addi_candidates']))),encoding='ascii')
