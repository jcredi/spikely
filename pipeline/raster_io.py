"""GFSC GeoTIFF discovery and aligned-grid loading for the production pipeline.

This adapter knows the GFSC on-disk convention, validates every input layer,
and returns arrays for ``pipeline.asof``. It deliberately does not choose
between MGRS tiles or product versions, reproject, or write rendered tiles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import re
from typing import Iterable, Sequence

import numpy as np
import rasterio
from affine import Affine
from numpy.typing import NDArray

from .asof import DailyProduct

_LAYER_PATTERN = re.compile(
    r"^(?P<product>CLMS_WSI_GFSC_060m_T(?P<tile>\d{2}[A-Z0-9]{3})_"
    r"(?P<date>\d{8})P7D_COMB_(?P<version>[^_]+))_"
    r"(?P<layer>GF|GF-QA|AT)\.tif$"
)
_REQUIRED_LAYERS = frozenset({"GF", "GF-QA", "AT"})
_EXPECTED_DTYPE = {"GF": "uint8", "GF-QA": "uint8", "AT": "uint32"}
_EXPECTED_NODATA = {"GF": 255, "GF-QA": 255, "AT": 0}


@dataclass(frozen=True)
class ProductTriplet:
    """The three required source rasters for one daily GFSC product."""

    product: str
    tile: str
    product_date: date
    version: str
    gf_path: Path
    quality_path: Path
    acquisition_time_path: Path


@dataclass(frozen=True)
class RasterGrid:
    """Grid properties that must match across layers and products for one tile."""

    crs: str
    transform: Affine
    width: int
    height: int


@dataclass(frozen=True)
class LoadedTile:
    """Aligned daily arrays ready for deterministic AS-OF composition."""

    tile: str
    grid: RasterGrid
    products: tuple[DailyProduct, ...]


def discover_product_triplets(root: Path, *, tile: str | None = None) -> list[ProductTriplet]:
    """Discover complete GF/GF-QA/AT triplets below ``root``.

    Incomplete products and duplicate `(tile, product-date)` inputs are errors:
    callers must resolve a failed download or product-version choice explicitly
    rather than silently omitting or arbitrarily selecting observations.
    """

    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"GFSC root is not a directory: {root}")

    requested_tile = tile.upper() if tile else None
    grouped: dict[tuple[Path, str], dict[str, object]] = {}
    for path in sorted(root.rglob("*.tif")):
        match = _LAYER_PATTERN.match(path.name)
        if not match:
            continue
        metadata = match.groupdict()
        if requested_tile and metadata["tile"] != requested_tile:
            continue
        key = (path.parent, metadata["product"])
        entry = grouped.setdefault(key, {"metadata": metadata, "layers": {}})
        layers = entry["layers"]
        assert isinstance(layers, dict)
        layer = metadata["layer"]
        if layer in layers:
            raise ValueError(f"duplicate {layer} raster for product {metadata['product']}")
        layers[layer] = path

    triplets: list[ProductTriplet] = []
    seen_tile_dates: set[tuple[str, date]] = set()
    for (_, product), entry in grouped.items():
        metadata = entry["metadata"]
        layers = entry["layers"]
        assert isinstance(metadata, dict)
        assert isinstance(layers, dict)
        missing = _REQUIRED_LAYERS - layers.keys()
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"incomplete GFSC product {product}: missing {joined}")

        product_date = datetime.strptime(str(metadata["date"]), "%Y%m%d").date()
        tile_date = (str(metadata["tile"]), product_date)
        if tile_date in seen_tile_dates:
            raise ValueError(
                "multiple GFSC product versions for "
                f"tile {tile_date[0]} on {product_date.isoformat()}"
            )
        seen_tile_dates.add(tile_date)
        triplets.append(
            ProductTriplet(
                product=product,
                tile=tile_date[0],
                product_date=product_date,
                version=str(metadata["version"]),
                gf_path=_layer_path(layers, "GF"),
                quality_path=_layer_path(layers, "GF-QA"),
                acquisition_time_path=_layer_path(layers, "AT"),
            )
        )

    if not triplets:
        scope = f" for tile {requested_tile}" if requested_tile else ""
        raise ValueError(f"no GFSC product triplets found below {root}{scope}")
    return sorted(triplets, key=lambda item: (item.tile, item.product_date, item.version))


def _layer_path(layers: dict[object, object], layer: str) -> Path:
    path = layers[layer]
    assert isinstance(path, Path)
    return path


def load_tile_products(triplets: Sequence[ProductTriplet]) -> LoadedTile:
    """Read and validate one MGRS tile's triplets into aligned daily arrays."""

    if not triplets:
        raise ValueError("at least one GFSC triplet is required")

    tiles = {triplet.tile for triplet in triplets}
    if len(tiles) != 1:
        joined = ", ".join(sorted(tiles))
        raise ValueError(f"load_tile_products accepts exactly one MGRS tile, got {joined}")
    tile = next(iter(tiles))

    dates = [triplet.product_date for triplet in triplets]
    if len(dates) != len(set(dates)):
        raise ValueError(f"duplicate product dates for tile {tile}")

    grid: RasterGrid | None = None
    products: list[DailyProduct] = []
    for triplet in sorted(triplets, key=lambda item: item.product_date):
        gf, gf_grid = _read_layer(triplet.gf_path, "GF")
        quality, quality_grid = _read_layer(triplet.quality_path, "GF-QA")
        acquisition_time, at_grid = _read_layer(triplet.acquisition_time_path, "AT")
        _require_matching_grid(triplet.product, gf_grid, quality_grid)
        _require_matching_grid(triplet.product, gf_grid, at_grid)
        if grid is None:
            grid = gf_grid
        else:
            _require_matching_grid(triplet.product, grid, gf_grid)
        products.append(DailyProduct(triplet.product_date, gf, quality, acquisition_time))

    assert grid is not None
    return LoadedTile(tile=tile, grid=grid, products=tuple(products))


def _read_layer(path: Path, layer: str) -> tuple[NDArray[np.integer], RasterGrid]:
    with rasterio.open(path) as dataset:
        if dataset.count != 1:
            raise ValueError(f"{layer} raster must have one band: {path}")
        if dataset.crs is None:
            raise ValueError(f"{layer} raster has no CRS: {path}")
        if dataset.dtypes[0] != _EXPECTED_DTYPE[layer]:
            raise ValueError(
                f"{layer} raster has dtype {dataset.dtypes[0]}, "
                f"expected {_EXPECTED_DTYPE[layer]}: {path}"
            )
        if dataset.nodata != _EXPECTED_NODATA[layer]:
            raise ValueError(
                f"{layer} raster has nodata {dataset.nodata!r}, "
                f"expected {_EXPECTED_NODATA[layer]}: {path}"
            )
        array = dataset.read(1)
        grid = RasterGrid(
            crs=dataset.crs.to_string(),
            transform=dataset.transform,
            width=dataset.width,
            height=dataset.height,
        )
    return array, grid


def _require_matching_grid(product: str, expected: RasterGrid, actual: RasterGrid) -> None:
    if actual != expected:
        raise ValueError(
            f"GFSC raster grid mismatch in {product}: expected {expected}, got {actual}"
        )
