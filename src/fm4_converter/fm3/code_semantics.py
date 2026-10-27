"""Opt-in stock coordinate adapter justified by paired executable traces.

This preserves the traced FM3 configuration/main mass-block input in FM4. It
does not reproduce native FM4 car retuning, all mass blocks, assets, or handling.
"""
from __future__ import annotations

import math
import struct
import json

from . import converter as c
from . import suspension_semantics as suspension

WEIGHT="List_UpgradeCarBodyWeight"
ORIGIN="BottomCenterWheelbasePosy"
EVIDENCE={
    "fm3_config_loader":"0x826BAB88",
    "fm3_mass_builder":"0x82728C58",
    "fm4_config_correction":"0x828A77A0..0x828A77C8",
    "fm4_main_mass_center_y":"0x8281E308..0x8281E314",
    "scope":"Retail base FM3 USA / FM4 Japan-Asia; stock, unchanged body geometry, zero selected WeightDistDiff",
}


def f32(value):
    return struct.unpack(">f",struct.pack(">f",value))[0]


def row(graph,role):
    return graph["nodes"][role]["row"]


def finite(value,label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise c.MappingError("Invalid finite numeric field: "+label)
    return value


def inputs(graph,version):
    weight,body=row(graph,WEIGHT),row(graph,"body")
    height=finite(weight["CMHeight"],"CMHeight")
    dist=finite(weight["CMBackFront"],"CMBackFront")
    # Reject boundary/modified cases instead of silently guessing part selection
    # or the contribution of unsupported upgrades to effective distribution.
    if not .01 <= dist <= .99:
        raise c.MappingError("Code semantics supports stock CMBackFront in [.01,.99]")
    origin=finite(body[ORIGIN],ORIGIN)
    selected=[]
    for role,node in graph["nodes"].items():
        if not role.startswith("List_Upgrade"):
            continue
        part=node["row"]
        if part.get("IsStock") != 1:
            raise c.MappingError("Code semantics requires selected stock parts: "+role)
        if "WeightDistDiff" in part:
            delta=finite(part["WeightDistDiff"],role+".WeightDistDiff")
            if delta != 0:
                raise c.MappingError("Nonzero selected WeightDistDiff requires a full selection trace")
            selected.append(role)
    result={"height":height,"distribution":dist,"origin_y":origin,"zero_weight_delta_roles":selected}
    if version=="fm4":
        car=row(graph,"car")
        front=finite(car["FrontStockRideHeight"],"FrontStockRideHeight")
        rear=finite(car["RearStockRideHeight"],"RearStockRideHeight")
        if front < 0 or rear < 0:
            raise c.MappingError("Negative stock ride-height reference unsupported")
        result.update(front_height=front,rear_height=rear,
                      weighted_height=rear+(front-rear)*dist)
    elif version!="fm3":
        raise c.MappingError("Unknown coordinate convention")
    return result


def effective_center(graph,version):
    """Analytical traced input, NOT final multi-block assembled vehicle CG."""
    value=inputs(graph,version)
    config_height=value["height"]-value.get("weighted_height",0)
    return {**value,"config_cmheight":config_height,
            "main_mass_block_center_y":config_height+value["origin_y"],
            "meaning":"Input to traced main mass-block builder; not whole-vehicle measured CG"}


def apply(result,source):
    if "code_semantics" in result:
        raise c.MappingError("Code coordinate policy already applied")
    candidate=result["candidate"]
    source_parts={r for r in source["nodes"] if r.startswith("List_Upgrade")}
    target_parts={r for r in candidate["nodes"] if r.startswith("List_Upgrade")}
    if source_parts != target_parts:
        raise c.MappingError("Code semantics requires the same selected stock-part roles")
    for role in source_parts:
        if source["nodes"][role]["table"]!=candidate["nodes"][role]["table"]:
            raise c.MappingError("Selected part table changed: "+role)
    a=inputs(source,"fm3")
    before=effective_center(candidate,"fm4")
    # Existing empirical CG/suspension estimates implement a different policy.
    # Fail closed rather than mixing calibrations or silently overwriting them.
    if row(candidate,WEIGHT)["CMHeight"] != row(source,WEIGHT)["CMHeight"]:
        raise c.MappingError("Code semantics cannot be mixed with an estimated CMHeight")
    if row(candidate,WEIGHT)["CMBackFront"] != row(source,WEIGHT)["CMBackFront"]:
        raise c.MappingError("Changed weight distribution outside stock coordinate policy")
    source_body,target_body=row(source,"body"),row(candidate,"body")
    body_pk=source["nodes"]["body"]["pk"]
    if any(source_body[k]!=target_body.get(k) for k in source_body if k!=body_pk):
        raise c.MappingError("Code semantics requires unchanged body geometry/origin")
    for role,node in source["nodes"].items():
        for col,value in node["row"].items():
            if "mass" in col.lower() or col.startswith("BlockDim") or col=="CurbWeight":
                if role not in candidate["nodes"] or row(candidate,role).get(col)!=value:
                    raise c.MappingError("Code semantics requires preserved visible mass inputs: "+role+"."+col)
    for role in ("spring.front","spring.rear","antiroll.front","antiroll.rear"):
        sa,ta=row(source,role),row(candidate,role)
        for col in sa:
            if col.startswith(("Def","Min","Max")) and any(x in col for x in
                    ("SpringRate","DampenBumpRate","DampenReboundRate","SwaybarStiffness")):
                if sa[col]!=ta[col]:
                    raise c.MappingError("Code semantics preserves source rate fields: "+role+"."+col)
    travel=suspension.plan(source,candidate)
    front=travel["axles"]["front"]["target_stock_height"]
    rear=travel["axles"]["rear"]["target_stock_height"]
    weighted=rear+(front-rear)*a["distribution"]
    converted=a["height"]+weighted
    finite(converted,"converted CMHeight")
    # Provenance must be resolvable before the single candidate write.
    mapping=c.one([m for m in result["mapping"] if m["role"]==WEIGHT and m["target_column"]=="CMHeight"],
                  "CMHeight code mapping")
    if not isinstance(result.get("assumptions"),list):
        raise c.MappingError("Code semantics requires an assumptions list")
    proposed=[]
    for axle in ("front","rear"):
        stock_col=axle.title()+"StockRideHeight"
        details=travel["axles"][axle]
        stock_mapping=c.one([m for m in result["mapping"] if m["role"]=="car" and
                             m["target_column"]==stock_col],stock_col+" code mapping")
        cap_mapping=c.one([m for m in result["mapping"] if m["role"]=="spring."+axle and
                           m["target_column"]=="MaxStretchDeltaFromRideHeight"],axle+" extension mapping")
        proposed.append((stock_col,details,stock_mapping,cap_mapping))
    audit={"version":"stock-coordinate-v2","evidence":EVIDENCE,
           "formula":"FM4.CMHeight = FM3.CMHeight + RearStockRideHeight + (FrontStockRideHeight-RearStockRideHeight)*CMBackFront",
           "source":a,"target_before":before,"target_raw_cmheight":converted,
           "source_main_mass_block_center_y":a["height"]+a["origin_y"],
           "expected_target_main_mass_block_center_y":converted-weighted+before["origin_y"],
           "target_stock_height_policy":"Source axle MaxRideHeight preserves the traced FM3 suspension reference. Data_CarBody.ModelStockRideHeight is a separate unchanged body field.",
           "suspension":travel,
           "rates_policy":"Source Min/Def/Max spring/damper/antiroll retained; no global rate multiplier",
           "runtime_verified":False,"installable":False}
    # Validate every proposal and its serializable evidence before any write.
    json.dumps(audit,allow_nan=False)
    for stock_col,details,stock_mapping,cap_mapping in proposed:
        axle="front" if stock_col.startswith("Front") else "rear"
        row(candidate,"car")[stock_col]=details["target_stock_height"]
        stock_mapping.update(baseline_value=details["old_candidate_stock_height"],
                             source_expression="spring."+axle+".MaxRideHeight",
                             source_value=details["target_stock_height"],
                             target_value=details["target_stock_height"],
                             action="code_verified_stock_reference",
                             confidence="paired_static_code_stock_scope")
        cap_mapping.update(action="retained_cohort_cap_verified_nonbinding",
                           confidence="paired_static_setup_selected_spring_range",
                           validation=details)
    row(candidate,WEIGHT)["CMHeight"]=converted
    mapping.update(baseline_value=a["height"],target_value=converted,
                   action="code_verified_coordinate_conversion",
                   source_expression=audit["formula"],confidence="paired_static_code_stock_scope")
    result["code_semantics"]=audit
    result["assumptions"].append({"rule":"stock_coordinate_conversion","runtime_verified":False,
                                  "limitation":audit["target_stock_height_policy"]})
    result["assumptions"].append({"rule":"selected_stock_extension_cap_audit",
                                  "runtime_verified":False,"audit":travel})
    return audit


def compare_centers(source,candidate,reference=None):
    a,b=effective_center(source,"fm3"),effective_center(candidate,"fm4")
    delta=b["main_mass_block_center_y"]-a["main_mass_block_center_y"]
    result={"source":a,"candidate":b,"candidate_minus_source":delta,
            "source_preserved_within_tolerance":abs(delta)<=1e-6,
            "scope":"Traced stock main mass-block center input only; not measured final vehicle CG"}
    if reference is not None:
        try:
            native=effective_center(reference,"fm4")
            result["native_fm4"]=native
            result["candidate_minus_native"]=b["main_mass_block_center_y"]-native["main_mass_block_center_y"]
        except (c.MappingError,KeyError) as error:
            result["native_unavailable_reason"]=str(error)
    return result


def run_cg_instruction_slice(image,base,*,height,distribution,front,rear):
    """Interpret only the audited 11-instruction arithmetic slice as data.

    No guest machine, branch, native call, file access, or game is executed.
    Normal finite float32 inputs only; no FPSCR/denormal/exception equivalence.
    This oracle reads instruction words from the verified local image instead
    of calling the analytical conversion formula.
    """
    memory={2324:f32(height),2328:f32(distribution),11480:f32(front),11484:f32(rear)}
    regs={}
    trace=[]
    for pc in range(0x828A77A0,0x828A77CC,4):
        off=pc-base
        if off<0 or off+4>len(image):
            raise c.MappingError("CG instruction slice outside image")
        word=int.from_bytes(image[off:off+4],"big")
        op=word>>26
        dest,ra,rb,rc=(word>>21)&31,(word>>16)&31,(word>>11)&31,(word>>6)&31
        imm=(word&65535)-(65536 if word&32768 else 0)
        if op==48 and ra==31:  # lfs
            if imm not in memory:
                raise c.MappingError("Unmapped slice load")
            regs[dest]=memory[imm]
        elif op==52 and ra==31 and imm==2324:  # stfs
            memory[imm]=f32(regs[dest])
        elif op==14 and ((dest in (4,5) and ra==0) or (dest==3 and ra==1)):
            pass  # unrelated argument setup, neither dereferenced nor called
        elif op==59 and ((word>>1)&31)==20:  # fsubs
            regs[dest]=f32(regs[ra]-regs[rb])
        elif op==59 and ((word>>1)&31)==29:  # fmadds
            # Inputs are float32: product uses <=48 significant binary bits;
            # binary64 suffices for the normal-range samples audited here.
            regs[dest]=f32(regs[ra]*regs[rc]+regs[rb])
        else:
            raise c.MappingError(f"Unsupported or changed CG slice instruction at {pc:08X}")
        trace.append(hex(pc))
    return {"config_cmheight":memory[2324],"instruction_addresses":trace,
            "scope":"Finite normal-range arithmetic micro-check; not full PowerPC emulation"}
