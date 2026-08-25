"""Render a merged AS-OF composite into browser-ready Web Mercator XYZ tiles.

Two independent steps, kept separate so the frozen color ramp stays testable
without any raster I/O: ``render_rgba`` turns a composite's semantic fields
into the fixed visual encoding from docs/spec.md sections 5.2 and 5.4; the
rest of this module slices that RGBA raster into the standard slippy-map tile
grid (https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames), writing
``{z}/{x}/{y}.png`` under an output root. Fully-transparent tiles are not
written - a mosaic's footprint is rarely the whole world.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from affine import Affine
from rasterio.warp import Resampling, reproject, transform_bounds

from .asof import AsOfComposite, PixelState
from .raster_io import RasterGrid

TILE_SIZE = 256

# EPSG:3857 half-circumference at the equator - the standard Web Mercator
# world extent, in map units (metres). This is a fixed property of the
# projection, not a derived/tunable value.
ORIGIN_SHIFT = 20_037_508.342789244
_WORLD_SPAN = 2 * ORIGIN_SHIFT

# Frozen visual encoding, docs/spec.md section 5.2: piecewise-linear sRGB from
# #82A0BE at 0%, through #C8DEF0 at 50%, to #FFFFFF at 100%; alpha 26/150/224
# at the same stops. Index 101-255 (categorical GF codes, NO_VALUE) render
# transparent here and are overridden below for CLOUD.
_STOPS = (0.0, 0.5, 1.0)


def _build_base_lut() -> NDArray[np.uint8]:
    lut = np.zeros((256, 4), dtype=np.uint8)
    f = np.linspace(0.0, 1.0, 101)
    lut[0:101, 0] = np.round(np.interp(f, _STOPS, [0x82, 0xC8, 0xFF]))
    lut[0:101, 1] = np.round(np.interp(f, _STOPS, [0xA0, 0xDE, 0xFF]))
    lut[0:101, 2] = np.round(np.interp(f, _STOPS, [0xBE, 0xF0, 0xFF]))
    lut[0:101, 3] = np.round(np.interp(f, _STOPS, [26, 150, 224]))
    return lut


_BASE_LUT = _build_base_lut()

# docs/spec.md section 5.4: cloud is violet #A855F7 at a fixed alpha 0.45,
# independent of freshness - unlike a valid observation it has no age to age.
_CLOUD_RGBA = np.array((0xA8, 0x55, 0xF7, round(0.45 * 255)), dtype=np.uint8)


def render_rgba(composite: AsOfComposite) -> NDArray[np.uint8]:
    """Colorize a composite's fsc/state/freshness fields per spec 5.2/5.4.

    Water, stale, and no-data all render fully transparent (spec 5.4: "render
    the snow layer transparent"); only their category is distinguished
    elsewhere (point/history details, not this raster).
    """

    base = _BASE_LUT[composite.fsc]
    alpha = np.round(base[..., 3].astype(np.float32) * composite.freshness)
    rgba = base.copy()
    rgba[..., 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    rgba[composite.state == PixelState.CLOUD] = _CLOUD_RGBA
    return rgba


def _tile_transform(z: int, x: int, y: int) -> tuple[Affine, tuple[float, float, float, float]]:
    tile_span = _WORLD_SPAN / (2**z)
    west = -ORIGIN_SHIFT + x * tile_span
    north = ORIGIN_SHIFT - y * tile_span
    resolution = tile_span / TILE_SIZE
    transform = Affine(resolution, 0.0, west, 0.0, -resolution, north)
    return transform, (west, north - tile_span, west + tile_span, north)


def _tile_range(grid: RasterGrid, z: int) -> tuple[range, range]:
    corners_x = (grid.transform.c, (grid.transform * (grid.width, grid.height))[0])
    corners_y = (grid.transform.f, (grid.transform * (grid.width, grid.height))[1])
    left, right = min(corners_x), max(corners_x)
    bottom, top = min(corners_y), max(corners_y)
    west, south, east, north = transform_bounds(grid.crs, "EPSG:3857", left, bottom, right, top)

    n = 2**z
    tile_span = _WORLD_SPAN / n
    epsilon = tile_span * 1e-9
    x_min = max(0, math.floor((west + ORIGIN_SHIFT) / tile_span))
    x_max = min(n - 1, math.floor((east + ORIGIN_SHIFT - epsilon) / tile_span))
    y_min = max(0, math.floor((ORIGIN_SHIFT - north) / tile_span))
    y_max = min(n - 1, math.floor((ORIGIN_SHIFT - south - epsilon) / tile_span))
    return range(x_min, x_max + 1), range(y_min, y_max + 1)


def _warp_tile(rgba: NDArray[np.uint8], grid: RasterGrid, z: int, x: int, y: int) -> NDArray[np.uint8] | None:
    dst_transform, _ = _tile_transform(z, x, y)
    dst = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
    for band in range(4):
        # 0 never occurs in a legitimately encoded pixel (color channels start
        # at 130/160/190 and alpha at 26; only a fully transparent pixel is
        # all-zero), so 0 doubles safely as the nodata sentinel on both sides.
        # Without src_nodata, GDAL's dst_nodata handling bumps any resampled
        # value that collides with it by 1 to disambiguate from "no data" -
        # turning legitimate (0,0,0,0) transparency into (1,1,1,1).
        reproject(
            source=rgba[..., band],
            destination=dst[..., band],
            src_transform=grid.transform,
            src_crs=grid.crs,
            src_nodata=0,
            dst_transform=dst_transform,
            dst_crs="EPSG:3857",
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
    if not dst[..., 3].any():
        return None
    return dst


def write_xyz_tiles(
    composite: AsOfComposite,
    grid: RasterGrid,
    zooms: Sequence[int],
    out_dir: Path,
) -> list[Path]:
    """Warp and write one composite as an XYZ tile set under ``out_dir``.

    Only tiles with at least one non-transparent pixel are written, so a
    mosaic's footprint (never the whole world) doesn't leave behind an empty
    tile tree. Returns the paths actually written.
    """

    rgba = render_rgba(composite)
    written: list[Path] = []
    for z in zooms:
        x_range, y_range = _tile_range(grid, z)
        for x in x_range:
            for y in y_range:
                tile = _warp_tile(rgba, grid, z, x, y)
                if tile is None:
                    continue
                path = out_dir / str(z) / str(x) / f"{y}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(tile, mode="RGBA").save(path, optimize=True)
                written.append(path)
    return written
