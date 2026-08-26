"""Build and optionally publish a full-area, newest-product-only GFSC preview."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, date, datetime
import json
from pathlib import Path
from typing import Sequence

from rasterio.transform import array_bounds
from rasterio.warp import transform_bounds

from .asof import compose_as_of
from .config import MVP_MGRS_TILES, PREVIEW_MAX_ZOOM, PREVIEW_MIN_ZOOM
from .fetch import CatalogProduct, discover_latest_products, download_products
from .mosaic import TileComposite
from .publish import publish_to_r2
from .raster_io import ProductTriplet, discover_product_triplets, load_tile_products
from .snapshots import render_snapshots, save_snapshot, snapshot_info


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


def _local_latest(
    raw_dir: Path, tiles: Sequence[str], as_of_date: date
) -> dict[str, ProductTriplet]:
    grouped: dict[str, list[ProductTriplet]] = defaultdict(list)
    for triplet in discover_product_triplets(raw_dir):
        if triplet.tile in tiles and triplet.product_date <= as_of_date:
            grouped[triplet.tile].append(triplet)
    missing = sorted(set(tiles) - grouped.keys())
    if missing:
        raise ValueError(f"no local product found for: {', '.join(missing)}")
    return {
        tile: max(triplets, key=lambda item: (item.product_date, item.version))
        for tile, triplets in grouped.items()
    }


def _downloaded_triplets(
    raw_dir: Path,
    selected: dict[str, CatalogProduct],
) -> dict[str, ProductTriplet]:
    by_product = {triplet.product: triplet for triplet in discover_product_triplets(raw_dir)}
    missing = [product.product for product in selected.values() if product.product not in by_product]
    if missing:
        raise ValueError(f"downloaded product discovery failed for: {', '.join(missing)}")
    return {tile: by_product[product.product] for tile, product in selected.items()}


def _bounds_wgs84(snapshot_paths: Sequence[Path]) -> list[float]:
    transformed: list[tuple[float, float, float, float]] = []
    for path in snapshot_paths:
        grid = snapshot_info(path).grid
        west, south, east, north = array_bounds(grid.height, grid.width, grid.transform)
        transformed.append(
            transform_bounds(grid.crs, "EPSG:4326", west, south, east, north)
        )
    return [
        min(item[0] for item in transformed),
        min(item[1] for item in transformed),
        max(item[2] for item in transformed),
        max(item[3] for item in transformed),
    ]


def build_preview(
    *,
    as_of_date: date,
    tiles: Sequence[str],
    raw_dir: Path,
    work_dir: Path,
    output_dir: Path,
    lookback_days: int = 21,
    fetch: bool = True,
    publish: bool = False,
) -> dict[str, object]:
    """Run newest-product discovery through render and optional R2 publish."""

    normalized_tiles = tuple(sorted({tile.upper() for tile in tiles}))
    if fetch:
        catalog = discover_latest_products(
            normalized_tiles,
            as_of_date,
            lookback_days,
            require_all=False,
        )
        if not catalog:
            raise ValueError("no recent complete GFSC products found for the requested area")
        download_products(catalog.values(), raw_dir)
        triplets = _downloaded_triplets(raw_dir, catalog)
    else:
        triplets = _local_latest(raw_dir, normalized_tiles, as_of_date)

    active_tiles = tuple(sorted(triplets))
    missing_tiles = sorted(set(normalized_tiles) - triplets.keys())

    generated_at = datetime.now(UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = work_dir / "snapshots" / run_id
    snapshot_paths: list[Path] = []
    product_dates: dict[str, str] = {}
    for tile in active_tiles:
        triplet = triplets[tile]
        loaded = load_tile_products([triplet])
        composite = compose_as_of(loaded.products, as_of_date)
        snapshot_path = snapshot_dir / f"{tile}.npz"
        save_snapshot(
            snapshot_path,
            TileComposite(tile=tile, grid=loaded.grid, composite=composite),
        )
        snapshot_paths.append(snapshot_path)
        product_dates[tile] = triplet.product_date.isoformat()

    run_dir = output_dir / "runs" / run_id
    tile_paths = render_snapshots(
        snapshot_paths,
        run_dir / "tiles",
        PREVIEW_MIN_ZOOM,
        PREVIEW_MAX_ZOOM,
    )
    metadata: dict[str, object] = {
        "schemaVersion": 1,
        "runId": run_id,
        "mode": "latest-product-only-preview",
        "asOfDate": as_of_date.isoformat(),
        "generatedAt": generated_at.isoformat(),
        "minzoom": PREVIEW_MIN_ZOOM,
        "maxzoom": PREVIEW_MAX_ZOOM,
        "bounds": _bounds_wgs84(snapshot_paths),
        "tileCount": len(tile_paths),
        "requestedSourceTileCount": len(normalized_tiles),
        "sourceTileCount": len(active_tiles),
        "sourceTiles": list(active_tiles),
        "missingSourceTiles": missing_tiles,
        "productDates": product_dates,
        "notice": (
            "Preview uses one newest GFSC product per MGRS tile. It does not yet "
            "apply Spikely's cross-product 14-day AS-OF fallback."
        ),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")

    local_latest = dict(metadata)
    local_latest["tiles"] = [f"runs/{run_id}/tiles/{{z}}/{{x}}/{{y}}.png"]
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(json.dumps(local_latest, indent=2) + "\n")
    if publish:
        publish_to_r2(run_dir, metadata)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=_parse_date, default=date.today())
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--lookback-days", type=int, default=21)
    parser.add_argument("--tiles", nargs="+", default=MVP_MGRS_TILES)
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Use the newest matching products already below --raw-dir.",
    )
    parser.add_argument(
        "--publish-r2",
        action="store_true",
        help="Publish the completed immutable run and latest.json pointer to R2.",
    )
    args = parser.parse_args()
    metadata = build_preview(
        as_of_date=args.as_of,
        tiles=args.tiles,
        raw_dir=args.raw_dir,
        work_dir=args.work_dir,
        output_dir=args.output_dir,
        lookback_days=args.lookback_days,
        fetch=not args.skip_fetch,
        publish=args.publish_r2,
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
