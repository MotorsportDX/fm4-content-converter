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
from .texture_audit import Texture, tiled_address


MAX_CROPPED_BORDER = 0.1  # share of border pixels a cropped car may cover

# FM3 renders its thumbnails high-key on white; FM4's own are darker, with more
# contrast and saturation. FM4's car select shows the atlas' large view as the
# car picture, so FM3 pixels look washed out next to FM4 cars. Measured on the
# 315 cars both games ship (outputs/fm-car-converter/exterior-paint-v1/
# thumb_lcurve.py): median quantile map of car-pixel linear luminance, FM3 ->
# FM4, over the 30..99.5% quantiles (FM4's ground shadow excluded), fitted on
# half the cars; held-out luminance error 85.8 -> 9.9 sRGB levels. Hue is kept;
# chroma then scales by the median FM4/FM3 saturation ratio (held-out 0.144 ->
# 0.092). A tone map cannot add FM4's highlights or ground shadow.
FM4_LUMINANCE = ((0.0, 0.0), (0.001, 0.0001), (0.0021, 0.0002), (0.0043, 0.0003),
                 (0.0089, 0.0006), (0.0183, 0.0008), (0.0264, 0.0009), (0.0379, 0.0013),
                 (0.0546, 0.0018), (0.0785, 0.0024), (0.1129, 0.0035), (0.1624, 0.0059),
                 (0.2336, 0.0106), (0.336, 0.0186), (0.4833, 0.0373), (0.6952, 0.1012),
                 (1.0, 0.4624))
FM4_SATURATION_GAIN = 2.119
LUMA = np.array([0.2126, 0.7152, 0.0722])


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
    border = ([(x,0) for x in range(w)] + [(x,h-1) for x in range(w)]
              + [(0,y) for y in range(1,h-1)] + [(w-1,y) for y in range(1,h-1)])
    # Some FM3 renders crop the car at an edge (MAS_35_MC12_05's wing): the
    # matte is still the white border, minus the pixels the car covers there.
    cropped = sum(not eligible[y,x] for x,y in border)
    if cropped > len(border)*MAX_CROPPED_BORDER:
        raise ThumbnailError("Source thumbnail lacks the reviewed white border")
    background = np.zeros((h,w), dtype=bool)
    queue = deque((x,y) for x,y in border if eligible[y,x])
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
                 "border_pixels_covered_by_car":int(cropped),
                 "unmatted_boundary_pixels":int(adjacent.sum())}


def fm4_tone(cutout):
    """Map the FM3 render's colours to FM4's thumbnail look (FM4_LUMINANCE)."""
    rgba = np.array(cutout).astype(float)
    c = rgba[:,:,:3]/255
    linear = np.where(c <= 0.04045, c/12.92, ((c+0.055)/1.055)**2.4)
    luminance = linear @ LUMA
    xs, ys = zip(*FM4_LUMINANCE)
    scaled = linear*(np.interp(luminance, xs, ys)/np.maximum(luminance, 1e-6))[:,:,None]
    grey = (scaled @ LUMA)[:,:,None]
    linear = np.clip(grey+(scaled-grey)*FM4_SATURATION_GAIN, 0, 1)
    c = np.where(linear <= 0.0031308, 12.92*linear, 1.055*linear**(1/2.4)-0.055)
    rgba[:,:,:3] = np.round(c*255)
    return Image.fromarray(rgba.astype(np.uint8))


# Car bounding box in FM4's own 503 atlases, as fractions of the view: median
# area, 90th-percentile width and height caps, median bottom margin
# (outputs/fm-car-converter/exterior-paint-v1/view_layout.py). The small view is
# FM4's side profile, long and low; the reused FM3 front-quarter image is
# shorter and taller, so it gets FM4's car area rather than its width.
LARGE_LAYOUT = (0.557, 0.931, 0.792, 0.014)
SMALL_LAYOUT = (0.202, 0.656, 0.406, 0.087)


def fit_view(cutout, size, layout):
    area, width, height, bottom = layout
    foreground = cutout.crop(cutout.getbbox())
    scale = min((area*size[0]*size[1]/(foreground.width*foreground.height))**0.5,
                size[0]*width/foreground.width, size[1]*height/foreground.height)
    dimensions = (max(1,round(foreground.width*scale)),max(1,round(foreground.height*scale)))
    foreground = foreground.resize(dimensions,Image.Resampling.LANCZOS)
    view = Image.new("RGBA",size)
    view.paste(foreground,((size[0]-foreground.width)//2,size[1]-foreground.height-round(size[1]*bottom)))
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
    cutout = fm4_tone(cutout)
    large = fit_view(cutout,(608,288),LARGE_LAYOUT)
    small = fit_view(cutout,(288,160),SMALL_LAYOUT)
    atlas = Image.new("RGBA",(768,288))
    atlas.paste(large,(0,0))
    atlas.paste(small.transpose(Image.Transpose.ROTATE_90),(608,0))
    encoded = encode(atlas,template)
    report.update(passed=True,cpu_only=True,runtime_tested=False,
                  source_sha256=hashlib.sha256(data).hexdigest(),
                  target_sha256=hashlib.sha256(encoded).hexdigest(),
                  atlas_size=[768,288],large_view=[0,0,608,288],
                  small_view_rotated_ccw=[608,0,768,288],
                  premultiplied_alpha=True,source_car_rgb_interior_preserved_before_resize=False,
                  fm4_tone={"luminance_knots":len(FM4_LUMINANCE),"saturation_gain":FM4_SATURATION_GAIN},
                  camera_limit="Both slots reuse the original FM3 front-quarter image; no new side render",
                  texture=Texture(encoded).audit())
    return encoded, report
