"""Backfill the per-object GFSC time series for one calendar month, all tiles.

``docs/plan.md``: "Backfill chunk = one calendar month, all tiles", run as a
``workflow_dispatch`` matrix over months
(``.github/workflows/backfill-object-series.yml``), each chunk handing its
output to a boto3-only publish job exactly like the daily workflow does. This
module is the render-side half of one chunk: for every requested tile it
fetches that tile's own whole-month product window from HR-WSI (reusing
``fetch.discover_window_products``/``select_window_products`` unchanged - a
calendar month is at most 31 product dates, inside the existing per-tile
window ceiling) and samples every loaded product into
``series/<TILE>/<YYYY-MM>.bin``, the same format and sampling code the daily
increment uses (:mod:`nevaio_pipeline.object_series_sampling`).

**The one invariant that matters most: this module never creates, extends,
reorders, or rebuilds a slot map.** That lifecycle belongs entirely to
:mod:`nevaio_pipeline.render`'s daily increment (see
:mod:`nevaio_pipeline.object_slots`'s own module docstring and
``docs/worklog.md`` 2026-09-12 on the two silent-corruption bugs that hit this
project the same day this backfill was designed). Concretely:

- :func:`load_required_slot_map` loads a tile's already-published slot map and
  refuses to invent one. By the time any backfill runs, every tile that has a
  published object-index shard already has a published slot map too - the
  daily workflow created it - so a slot map that cannot be found here is not
  "first run", it is either a genuine bug or (far more likely) the calling
  workflow could not prove the file was actually absent rather than merely
  unreadable. Either way this module must not paper over it by building a
  fresh map, so it raises instead of returning ``None``.
- Sampling only ever *reads* the slot map (via
  :func:`nevaio_pipeline.object_slots.validate_slot_map`, never
  ``extend_slot_map``). If the loaded slot map is missing an id the current
  shard carries, that is also raised rather than silently extended - growing
  a slot map is an explicit, auditable step reserved for the daily job, never
  an implicit side effect of backfilling history.
- This module never writes a slot map file at all, so the workflow's publish
  step never has slot maps to publish for a backfill chunk (see
  ``backfill-object-series.yml``, which passes an empty ``--slots-dir`` to
  :mod:`nevaio_pipeline.publish_object_series`).

**A month file that already exists in R2 is merged into, never overwritten and
never simply skipped - revised 2026-09-12.** An earlier version of this module
skipped a tile-month outright whenever it was already published, on the
reasoning that overwriting risked truncating a file the daily job had since
grown. That reasoning about truncation was correct and is preserved below, but
the skip itself was wrong: the daily job's own AS-OF window only ever reaches
back :data:`nevaio_pipeline.config.ASOF_WINDOW_DAYS` days, so it routinely
publishes a month file that is only *partially* filled (e.g. a September run
first touching ``2026-08.bin`` only covers the last few days of August that
fell inside its window) - and that partial file is exactly what a backfill of
that month exists to complete. Skipping on "the file exists" made the backfill
a no-op for precisely the months it was needed for.

The fix is cell-level merge, at the day granularity the format already
guarantees is independent (object-major layout: :mod:`nevaio_pipeline.object_series`):

- **Never replace an already-written cell.** A cell is written by this merge
  only where the existing byte is the gap sentinel
  (:data:`nevaio_pipeline.asof.NODATA`, byte 0) *and* the freshly sampled byte
  is not. A cell this run resamples identically to what is already published
  (the common case, since both derive from the same immutable HR-WSI archive)
  changes nothing; a cell this run cannot certify stays exactly what was
  already there. This is what makes a re-dispatched chunk idempotent, not just
  resumable.
- **Never shrink.** The merged array's slot count is
  ``max(existing_slot_count, current_slot_map.slot_count)`` - the existing
  file's own encoded length, read directly off its own byte count, not assumed
  from this run's slot-map snapshot. If the daily job extended the tile's slot
  map and republished a longer file after this run fetched its own (older,
  smaller) slot map, the existing file's tail survives untouched: those bytes
  are real published data other readers' byte offsets already depend on, and
  this run has no business truncating them just because its own map snapshot
  did not yet know about them.
- **Resume stays cheap, but is no longer "skip if the key exists".** Before
  paying for a download and sample, :func:`backfill_tile_month` checks whether
  every product date the catalogue lists for this tile-month already has at
  least one non-gap cell in the *existing* file, at at least the current slot
  count. If so there is nothing this run could add, and it returns
  ``"already-complete"`` after one catalogue listing and no raster download.
  Otherwise it proceeds exactly as if nothing existed, and the merge above
  guarantees the result is still safe. Catalogue listing is cheap (an S3 LIST,
  not a download; see :func:`nevaio_pipeline.fetch.discover_window_products`)
  so this check costs about the same as the HEAD it replaces plus one GET of
  the (small) existing file the workflow needed to fetch for the merge anyway.

The existing bytes themselves are supplied by the calling workflow, fetched
into ``series_output_dir`` *before* this module runs (curl, never
``urllib.request`` - Cloudflare's r2.dev answers 403 to Python's default
User-Agent while serving the identical URL to curl, measured 2026-09-12 on the
daily workflow's own first run) - the same directory this module writes its
merged result back into, mirroring how :func:`nevaio_pipeline.render._update_object_series`
already treats a locally-present month file. A 404 on that fetch means no
existing file (this tile-month has genuinely never been published, which the
merge logic treats identically to an empty starting point); any other fetch
outcome cannot prove absence-vs-unreadable and the workflow skips the tile for
this run entirely, the same discipline applied to the slot map fetch below.

Pure Python plus ``numpy``/``affine``/``rasterio`` (via
:mod:`nevaio_pipeline.raster_io`), matching :mod:`nevaio_pipeline.render` - the
raster stack, not boto3, so this always runs on the untrusted render side of
the trust boundary, never the publish side.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
import argparse
import json
import re
from pathlib import Path
from typing import Sequence

import numpy as np
from numpy.typing import NDArray

from .asof import NODATA
from .fetch import discover_window_products, download_products
from .footprint import utm_zone
from .object_index import SHARD_DIRECTORY, entries_from_shard_document
from .object_series import CELL_SIZE, array_from_buffer, buffer_from_array, new_month_array
from .object_series_sampling import index_tile_objects, sample_daily_product
from .object_slots import SLOT_DIRECTORY, SlotMap, load_slot_map, validate_slot_map
from .raster_io import load_tile_products
from .render import _downloaded_triplets

_MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def parse_month(value: str) -> tuple[int, int]:
    match = _MONTH_PATTERN.match(value)
    if not match:
        raise ValueError(f"month must be YYYY-MM, got {value!r}")
    return int(match.group(1)), int(match.group(2))


def month_bounds(year: int, month: int) -> tuple[date, date, int]:
    """Return ``(first_day, last_day, days)`` of one calendar month."""

    days = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, days), days


def load_required_slot_map(object_index_dir: Path, tile: str) -> SlotMap:
    """Load ``tile``'s already-published slot map, refusing to create one.

    See the module docstring: unlike
    :func:`nevaio_pipeline.object_slots.load_or_create_slot_map` (the daily
    job's own entry point), an absent file here is a hard error, not "first
    run for this tile".
    """

    path = object_index_dir / SLOT_DIRECTORY / f"{tile}.json"
    slot_map = load_slot_map(path)
    if slot_map is None:
        raise ValueError(
            f"backfill found no slot map for tile {tile} at {path}, and refuses to "
            "create one. Every tile with a published object-index shard already has "
            "a published slot map - the daily workflow creates it - so this means "
            "either a real bug or (more likely) the fetch step could not prove the "
            "file was genuinely absent rather than merely unreadable, and should have "
            "skipped this tile before ever invoking this module for it "
            "(see .github/workflows/backfill-object-series.yml and "
            "nevaio_pipeline.object_slots)."
        )
    return slot_map


def _load_existing_month_array(month_path: Path, days: int) -> tuple[NDArray[np.uint8] | None, int]:
    """Read an already-published month file, if the workflow fetched one.

    Returns ``(array, slot_count)`` - ``array`` is ``None`` (``slot_count`` 0)
    when no file is there at all, which the merge below treats as an empty
    starting point. ``slot_count`` is read directly off the file's own byte
    length, never assumed from the current slot map - see the module
    docstring on why that distinction is load-bearing for never shrinking a
    published file.
    """

    if not month_path.is_file():
        return None, 0
    existing_bytes = month_path.read_bytes()
    cell_bytes_per_day = days * CELL_SIZE
    if len(existing_bytes) == 0 or len(existing_bytes) % cell_bytes_per_day != 0:
        raise ValueError(
            f"existing month file {month_path} is not a whole number of object "
            f"slots for a {days}-day month ({len(existing_bytes)} bytes)"
        )
    existing_slot_count = len(existing_bytes) // cell_bytes_per_day
    return array_from_buffer(existing_bytes, existing_slot_count, days), existing_slot_count


def _month_already_complete(
    existing_array: NDArray[np.uint8] | None,
    existing_slot_count: int,
    current_slot_count: int,
    product_dates: set,
) -> bool:
    """Cheap resume check: is there nothing this run could add?

    True only when the existing file already covers every slot the current
    slot map knows about (no growth needed) and every product date this run
    would sample already has at least one non-gap cell somewhere in the
    existing file. A day that was already sampled - by an earlier backfill
    attempt or by the daily job - writes a non-:data:`nevaio_pipeline.asof.NODATA`
    byte into at least one slot whenever any object had a certifiable or cloud
    pixel that day; the rare day where every single object's own pixel was
    genuinely unreadable looks identical to "never sampled" and is harmlessly
    resampled again (idempotent - see the module docstring).
    """

    if existing_array is None or existing_slot_count < current_slot_count:
        return False
    if not product_dates:
        return False
    for product_date in product_dates:
        day_index = product_date.day - 1
        if not np.any(existing_array[:, day_index, 0] != NODATA):
            return False
    return True


def _merge_month_arrays(
    existing_array: NDArray[np.uint8] | None,
    sampled_array: NDArray[np.uint8],
    final_slot_count: int,
    year: int,
    month: int,
) -> NDArray[np.uint8]:
    """Combine an existing published month with this run's freshly sampled one.

    Starts from an all-gap baseline at ``final_slot_count`` (never smaller than
    either input - see the module docstring), lays the existing file's bytes
    over it verbatim (including any tail beyond ``sampled_array``'s own slot
    count, which survives untouched), then fills in - cell by cell, never
    replacing what is already there - wherever the existing cell is still a
    gap and the freshly sampled cell is not.
    """

    merged = new_month_array(final_slot_count, year, month)
    if existing_array is not None:
        old_slots = existing_array.shape[0]
        merged[:old_slots] = existing_array
    sampled_slots = sampled_array.shape[0]
    target = merged[:sampled_slots]
    fillable = (target[..., 0] == NODATA) & (sampled_array[..., 0] != NODATA)
    np.copyto(target, sampled_array, where=fillable[..., None])
    return merged


def backfill_tile_month(
    tile: str,
    year: int,
    month: int,
    *,
    raw_dir: Path,
    object_index_dir: Path,
    series_output_dir: Path,
) -> str:
    """Sample one tile's whole calendar month, merging into ``series_output_dir``.

    Returns a short status string for the caller's receipt:

    - ``"sampled"`` - this run wrote (merged) new data.
    - ``"already-complete"`` - the file the workflow pre-fetched into
      ``series_output_dir`` already covers every product date this run would
      sample, at the current slot count; nothing was downloaded or written
      (see :func:`_month_already_complete`).
    - ``"no-shard"`` - this tile has no objects (true for 4 of the MVP's 58
      tiles, see ``docs/plan.md``).
    - ``"no-products"`` - HR-WSI has nothing for this tile in this month, a
      genuine archive gap (full history reaches back only to September 2016),
      not an error.

    A month file already present at ``series_output_dir/<TILE>/<YYYY-MM>.bin``
    (fetched there by the calling workflow) is merged into, never overwritten
    or discarded - see the module docstring for why skip-if-exists made a
    backfill a no-op for exactly the months it was needed for, and why
    overwrite was rejected in favour of a cell-level merge.
    """

    shard_path = object_index_dir / SHARD_DIRECTORY / f"{tile}.json"
    if not shard_path.is_file():
        return "no-shard"
    entries = entries_from_shard_document(json.loads(shard_path.read_text(encoding="utf-8")))
    if not entries:
        return "no-shard"
    current_ids = tuple(entry.id for entry in entries)

    slot_map = load_required_slot_map(object_index_dir, tile)
    validate_slot_map(slot_map, current_ids)  # read-only check; never extend here

    first_day, last_day, days = month_bounds(year, month)
    window_days = (last_day - first_day).days + 1  # == days: exactly this month, no more
    catalog = discover_window_products([tile], last_day, window_days, require_all=False)
    products = catalog.get(tile, ())
    if not products:
        return "no-products"

    month_path = series_output_dir / tile / f"{year:04d}-{month:02d}.bin"
    existing_array, existing_slot_count = _load_existing_month_array(month_path, days)

    if _month_already_complete(
        existing_array, existing_slot_count, slot_map.slot_count,
        {p.product_date for p in products},
    ):
        return "already-complete"

    download_products(products, raw_dir)
    triplets = _downloaded_triplets(raw_dir, {tile: products})
    window = triplets.get(tile, ())
    # Belt-and-braces, not load-bearing: discover_window_products' own window
    # already spans exactly this month (window_days == days), so nothing
    # outside (year, month) should ever appear here.
    window = tuple(p for p in window if (p.product_date.year, p.product_date.month) == (year, month))
    if not window:
        return "no-products"

    loaded = load_tile_products(window)
    pixels = index_tile_objects(
        entries,
        slot_map,
        transform=loaded.grid.transform,
        zone=utm_zone(tile),
        width=loaded.grid.width,
        height=loaded.grid.height,
    )

    sampled_array = new_month_array(slot_map.slot_count, year, month)
    for product in loaded.products:
        sample_daily_product(sampled_array, pixels, product, days)

    final_slot_count = max(slot_map.slot_count, existing_slot_count)
    merged = _merge_month_arrays(existing_array, sampled_array, final_slot_count, year, month)

    month_path.parent.mkdir(parents=True, exist_ok=True)
    month_path.write_bytes(buffer_from_array(merged))
    return "sampled"


def backfill_month(
    *,
    year: int,
    month: int,
    tiles: Sequence[str],
    raw_dir: Path,
    object_index_dir: Path,
    series_output_dir: Path,
) -> dict[str, object]:
    """Backfill one calendar month across every requested tile.

    ``tiles`` is normally the subset of :data:`nevaio_pipeline.config.MVP_MGRS_TILES`
    the calling workflow has already resolved as worth attempting this run -
    it has already skipped any tile whose slot map (or pre-fetch of its
    existing month file) could not prove absence-vs-unreadable (see the
    module docstring) - so an empty list here is a legitimate, harmless no-op,
    not an error. A tile whose month file is already complete is still passed
    through here; :func:`backfill_tile_month` recognises that cheaply on its
    own (``"already-complete"``) rather than the caller pre-filtering it.
    """

    receipt: dict[str, object] = {
        "month": f"{year:04d}-{month:02d}",
        "tilesRequested": list(tiles),
        "sampled": [],
        "alreadyComplete": [],
        "noShard": [],
        "noProducts": [],
    }
    for tile in tiles:
        status = backfill_tile_month(
            tile,
            year,
            month,
            raw_dir=raw_dir,
            object_index_dir=object_index_dir,
            series_output_dir=series_output_dir,
        )
        {
            "sampled": receipt["sampled"],
            "already-complete": receipt["alreadyComplete"],
            "no-shard": receipt["noShard"],
            "no-products": receipt["noProducts"],
        }[status].append(tile)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="calendar month to backfill, YYYY-MM")
    parser.add_argument(
        "--tiles",
        nargs="*",
        default=[],
        help=(
            "Tiles to attempt this run (the calling workflow has already resolved "
            "resume/skip - see module docstring). Omit or pass none for a harmless no-op."
        ),
    )
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument(
        "--object-index-dir",
        type=Path,
        required=True,
        help="Directory holding objects/<TILE>.json shards and slots/<TILE>.json slot maps, already fetched.",
    )
    parser.add_argument(
        "--series-output-dir",
        type=Path,
        required=True,
        help=(
            "Where series/<TILE>/<YYYY-MM>.bin lives. Read as well as written: an "
            "already-published month file the calling workflow pre-fetched here is "
            "merged into (never overwritten), and the merged result is written back "
            "to the same path - see the module docstring."
        ),
    )
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    year, month = parse_month(args.month)
    receipt = backfill_month(
        year=year,
        month=month,
        tiles=args.tiles,
        raw_dir=args.raw_dir,
        object_index_dir=args.object_index_dir,
        series_output_dir=args.series_output_dir,
    )
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
