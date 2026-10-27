"""CPU conversion of FM3 white-matte thumbnails to the FM4 two-view atlas.

FM4 ThumbnailCamSettings.xml / 822A45A0 specify 608x288 and 288x160 views.
Native 768x288 XDS stores the small view rotated counterclockwise at x=608.
Both output views use the actual source thumbnail, not a different car or an
invented render. Their camera angle is consequently shared rather than native
FM4's separately rendered side angle.
SPDX-License-Identifier: GPL-3.0-only
"""
from collections import deque
import hashlib
import struct

import numpy as np
from PIL import Image, ImageFilter
from texture_audit import Texture, tiled_address


class ThumbnailError(ValueError):
    pass


def decode(data, premultiplied=False):
    t = Texture(data)
    if t.codec != "RGBA8" or t.header[10] != 0xC14:
        raise ThumbnailError("Unsupported thumbnail channel layout")
    im = Image.frombytes("RGBA", (t.width,t.height), t.read_level(0), "raw", "BGRA")
    if premultiplied:
        pixels = np.array(im).astype(np.uint32)
        alpha = pixels[:,:,3:4]
        pixels[:,:,:3] = np.minimum(255, (pixels[:,:,:3]*255+alpha//2)//np.maximum(alpha,1))
        im = Image.fromarray(pixels.astype(np.uint8))
    return im


def remove_white_matte(image):
    """Remove the border matte and broad ground gaps; retain white details.

    The original FM3 alpha channel is not a cutout mask (its background is opaque).
    A two-pixel boundary is uncomposited against the known white matte to suppress
    white fringes. Interior car RGB is preserved. This is a derived UI asset only.
    """
    rgb = np.array(image.convert("RGB"))
    h,w,_ = rgb.shape
    eligible = rgb.min(axis=2) >= 250
    if not (eligible[0].all() and eligible[-1].all() and eligible[:,0].all() and eligible[:,-1].all()):
        raise ThumbnailError("Source thumbnail lacks the reviewed white border")
    background = np.zeros((h,w), dtype=bool)
    queue = deque([(x,0) for x in range(w)] + [(x,h-1) for x in range(w)]
                  + [(0,y) for y in range(1,h-1)] + [(w-1,y) for y in range(1,h-1)])
    for x,y in queue:
        background[y,x] = True
    while queue:
        x,y = queue.popleft()
        for xx,yy in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0 <= xx < w and 0 <= yy < h and eligible[yy,xx] and not background[yy,xx]:
                background[yy,xx] = True
                queue.append((xx,yy))
    # A cast shadow can enclose a white ground gap below the chassis. Remove
    # only broad, low, horizontal white islands; round wheel highlights and
    # the upper window/body reflections remain opaque.
    yy,xx = np.where(~eligible)
    if not len(xx):
        raise ThumbnailError("Thumbnail foreground is empty")
    low = yy.min()+(yy.max()-yy.min()+1)*0.65
    minimum_width = (xx.max()-xx.min()+1)*0.15
    visited = background.copy()
    ground_islands = 0
    for y,x in np.argwhere(eligible & ~visited):
        if visited[y,x]:
            continue
        component, queue = [], deque([(int(x),int(y))])
        visited[y,x] = True
        while queue:
            x,y = queue.popleft()
            component.append((x,y))
            for xx,yy in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if 0 <= xx < w and 0 <= yy < h and eligible[yy,xx] and not visited[yy,xx]:
                    visited[yy,xx] = True
                    queue.append((xx,yy))
        xs,ys = zip(*component)
        width,height = max(xs)-min(xs)+1,max(ys)-min(ys)+1
        if min(ys)>=low and width>=minimum_width and width>=height*3 and len(component)>=80:
            for x,y in component:
                background[y,x] = True
            ground_islands += 1
    mask = Image.fromarray(background.astype(np.uint8)*255)
    adjacent = (np.array(mask.filter(ImageFilter.MaxFilter(5)))>0) & ~background
    rgba = np.concatenate((rgb, np.full((h,w,1),255,dtype=np.uint8)),axis=2)
    edge = rgb[adjacent].astype(np.uint32)
    minimum = edge.min(axis=1,keepdims=True)
    alpha = 255-minimum
    rgba[adjacent,:3] = ((edge-minimum)*255//np.maximum(alpha,1)).astype(np.uint8)
    rgba[adjacent,3] = alpha[:,0].astype(np.uint8)
    rgba[background] = 0
    out = Image.fromarray(rgba)
    box = out.getbbox()
    if box is None or (box[2]-box[0])*(box[3]-box[1]) < w*h/10:
        raise ThumbnailError("Thumbnail foreground is empty or unexpectedly small")
    return out, {"source_size":[w,h],"foreground_bounds":list(box),
                 "transparent_background_pixels":int(background.sum()),
                 "enclosed_ground_matte_islands_removed":ground_islands,
                 "unmatted_boundary_pixels":int(adjacent.sum())}


def fit_view(cutout, size):
    # Preserve aspect ratio, leave gutters and put the floor close to the bottom.
    foreground = cutout.crop(cutout.getbbox())
    scale = min(size[0]*0.85/foreground.width, size[1]*0.85/foreground.height)
    dimensions = (max(1,round(foreground.width*scale)),max(1,round(foreground.height*scale)))
    foreground = foreground.resize(dimensions,Image.Resampling.LANCZOS)
    view = Image.new("RGBA",size)
    view.paste(foreground,((size[0]-foreground.width)//2,size[1]-foreground.height-6))
    return view


def encode(atlas, template):
    t = Texture(template)
    expected = (3,1,0,0,0,0xFFFF0000,0xFFFF0000,
                0x86000002,0x86,0x23E2FF,0xC14,0,0xA00)
    if t.header != expected or len(template) != 52+768*288*4 or atlas.size != (768,288):
        raise ThumbnailError("Unreviewed native thumbnail atlas header")
    rgba = np.array(atlas).astype(np.uint16)
    # Native UI atlases use premultiplied colour and zero RGB outside the car.
    rgba[:,:,:3] = (rgba[:,:,:3]*rgba[:,:,3:4]+127)//255
    raw = Image.fromarray(rgba.astype(np.uint8)).tobytes("raw","BGRA")
    output = bytearray(768*288*4)
    for y in range(288):
        for x in range(768):
            source = (y*768+x)*4
            dest = tiled_address(x,y,768,2)
            output[dest:dest+4] = raw[source:source+4][::-1]
    result = struct.pack(">13I",*expected)+output
    checked = Texture(result)
    if checked.read_level(0) != raw:
        raise ThumbnailError("Tiling/endian roundtrip failed")
    return bytes(result)


def convert(data, template):
    source = Texture(data)
    if (source.width,source.height,source.codec,source.gamma) != (512,256,"RGBA8",0):
        raise ThumbnailError("Unreviewed FM3 thumbnail format")
    cutout, report = remove_white_matte(decode(data))
    large = fit_view(cutout,(608,288))
    small = fit_view(cutout,(288,160))
    atlas = Image.new("RGBA",(768,288))
    atlas.paste(large,(0,0))
    atlas.paste(small.transpose(Image.Transpose.ROTATE_90),(608,0))
    encoded = encode(atlas,template)
    report.update(passed=True,cpu_only=True,runtime_tested=False,
                  source_sha256=hashlib.sha256(data).hexdigest(),
                  target_sha256=hashlib.sha256(encoded).hexdigest(),
                  atlas_size=[768,288],large_view=[0,0,608,288],
                  small_view_rotated_ccw=[608,0,768,288],
                  premultiplied_alpha=True,source_car_rgb_interior_preserved_before_resize=True,
                  camera_limit="Both slots reuse the original FM3 front-quarter image; no new side render",
                  texture=Texture(encoded).audit())
    return encoded, report
