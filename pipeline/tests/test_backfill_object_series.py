from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from affine import Affine

from nevaio_pipeline.asof import DailyProduct
from nevaio_pipeline.backfill_object_series import (
    backfill_month,
    backfill_tile_month,
    load_required_slot_map,
    month_bounds,
    parse_month,
)
from nevaio_pipeline.footprint import unproject_utm
from nevaio_pipeline.object_index import ObjectIndexEntry, SHARD_DIRECTORY
from nevaio_pipeline.object_series import array_from_buffer, buffer_from_array, decode_cell, new_month_array, SeriesMarkState
from nevaio_pipeline.object_slots import SLOT_DIRECTORY, SlotMap, write_slot_map
from nevaio_pipeline.raster_io import LoadedTile, ProductTriplet, RasterGrid

TILE = "32TPS"
ZONE = 32
WIDTH = HEIGHT = 6
TRANSFORM = Affine(60.0, 0, 500_000.0, 0, -60.0, 5_000_000.0)


def at_epoch(day: date, hour: int = 10) -> int:
    return int(datetime(day.year, day.month, day.day, hour, tzinfo=UTC).timestamp())


def lonlat_at(col: int, row: int) -> tuple[float, float]:
    easting, northing = TRANSFORM @ (col + 0.5, row + 0.5)
    return unproject_utm(easting, northing, ZONE)


def entry(id_: str, col: float, row: float) -> ObjectIndexEntry:
    longitude, latitude = lonlat_at(int(col), int(row))
    return ObjectIndexEntry(id=id_, kind="peak", name=id_, longitude=longitude, latitude=latitude, elevation_meters=None)


def write_shard(object_index_dir: Path, tile: str, entries: list[ObjectIndexEntry]) -> None:
    shard_document = {
        "schemaVersion": 1,
        "tile": tile,
        "objects": [e.to_document() for e in entries],
    }
    shard_dir = object_index_dir / SHARD_DIRECTORY
    shard_dir.mkdir(parents=True, exist_ok=True)
    (shard_dir / f"{tile}.json").write_text(json.dumps(shard_document))


def product(day: date, marks: dict[tuple[int, int], tuple[int, int, int]]) -> DailyProduct:
    gf = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    qa = np.full((HEIGHT, WIDTH), 255, dtype=np.uint8)
    at = np.zeros((HEIGHT, WIDTH), dtype=np.uint32)
    for (row, col), (gf_value, qa_value, at_value) in marks.items():
        gf[row, col] = gf_value
        qa[row, col] = qa_value
        at[row, col] = at_value
    return DailyProduct(day, gf, qa, at)


def triplet(tile: str, day: date, version: str = "V100") -> ProductTriplet:
    product_name = f"CLMS_WSI_GFSC_060m_T{tile}_{day:%Y%m%d}P7D_COMB_{version}"
    base = Path(product_name)
    return ProductTriplet(product_name, tile, day, version, base / "gf", base / "qa", base / "at")


class ParseAndBoundsTests(unittest.TestCase):
    def test_parse_month_accepts_iso_and_rejects_other_shapes(self) -> None:
        self.assertEqual(parse_month("2026-08"), (2026, 8))
        with self.assertRaisesRegex(ValueError, "YYYY-MM"):
            parse_month("2026-8")
        with self.assertRaisesRegex(ValueError, "YYYY-MM"):
            parse_month("08-2026")

    def test_month_bounds_spans_the_whole_calendar_month(self) -> None:
        first, last, days = month_bounds(2026, 2)
        self.assertEqual((first, last, days), (date(2026, 2, 1), date(2026, 2, 28), 28))

        first, last, days = month_bounds(2026, 8)
        self.assertEqual((first, last, days), (date(2026, 8, 1), date(2026, 8, 31), 31))


class LoadRequiredSlotMapTests(unittest.TestCase):
    def test_refuses_to_invent_a_slot_map(self) -> None:
        """The one invariant that matters most: backfill never creates one."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "refuses to create one"):
                load_required_slot_map(root, TILE)

    def test_loads_an_already_published_slot_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_slot_map(root, SlotMap(tile=TILE, slot_ids=("node/1", "node/2")))
            slot_map = load_required_slot_map(root, TILE)
            self.assertEqual(slot_map.slot_for("node/1"), 0)
            self.assertEqual(slot_map.slot_for("node/2"), 1)


class BackfillTileMonthTests(unittest.TestCase):
    def _run(self, tmp: Path, *, window: tuple, entries: list[ObjectIndexEntry]) -> str:
        index_dir = tmp / "index"
        series_dir = tmp / "series"
        raw_dir = tmp / "raw"
        write_shard(index_dir, TILE, entries)
        write_slot_map(
            index_dir, SlotMap(tile=TILE, slot_ids=tuple(e.id for e in entries))
        )
        grid = RasterGrid(f"EPSG:{32600 + ZONE}", TRANSFORM, WIDTH, HEIGHT)
        catalog_products = tuple(SimpleNamespace(product_date=t.product_date) for t, _ in window)  # CatalogProduct stand-ins
        with (
            patch(
                "nevaio_pipeline.backfill_object_series.discover_window_products",
                return_value={TILE: catalog_products},
            ),
            patch("nevaio_pipeline.backfill_object_series.download_products"),
            patch(
                "nevaio_pipeline.backfill_object_series._downloaded_triplets",
                return_value={TILE: tuple(t for t, _ in window)},
            ),
            patch(
                "nevaio_pipeline.backfill_object_series.load_tile_products",
                return_value=LoadedTile(tile=TILE, grid=grid, products=tuple(p for _, p in window)),
            ),
        ):
            return backfill_tile_month(
                TILE, 2026, 3, raw_dir=raw_dir, object_index_dir=index_dir, series_output_dir=series_dir
            )

    def test_no_shard_is_a_harmless_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = backfill_tile_month(
                TILE, 2026, 3,
                raw_dir=root / "raw", object_index_dir=root / "index", series_output_dir=root / "series",
            )
            self.assertEqual(status, "no-shard")
            self.assertFalse((root / "series").exists())

    def test_a_shard_with_no_published_slot_map_is_a_hard_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_shard(root / "index", TILE, [entry("node/1", col=0.0, row=0.0)])
            with self.assertRaisesRegex(ValueError, "refuses to create one"):
                backfill_tile_month(
                    TILE, 2026, 3,
                    raw_dir=root / "raw", object_index_dir=root / "index", series_output_dir=root / "series",
                )

    def test_a_slot_map_missing_a_current_object_id_is_a_hard_error_not_an_extend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_shard(root / "index", TILE, [entry("node/1", col=0.0, row=0.0), entry("node/2", col=1.0, row=1.0)])
            write_slot_map(root / "index", SlotMap(tile=TILE, slot_ids=("node/1",)))
            with self.assertRaisesRegex(ValueError, "must be extended first"):
                backfill_tile_month(
                    TILE, 2026, 3,
                    raw_dir=root / "raw", object_index_dir=root / "index", series_output_dir=root / "series",
                )

    def test_no_archive_products_is_a_harmless_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = self._run(root, window=(), entries=[entry("node/1", col=0.0, row=0.0)])
            self.assertEqual(status, "no-products")
            self.assertFalse((root / "series" / TILE).exists())

    def test_samples_the_whole_month_into_one_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            e = entry("node/1", col=2.0, row=3.0)
            day1 = date(2026, 3, 1)
            day2 = date(2026, 3, 15)
            p1 = product(day1, {(3, 2): (40, 1, at_epoch(day1))})
            p2 = product(day2, {(3, 2): (55, 2, at_epoch(day2))})
            window = ((triplet(TILE, day1), p1), (triplet(TILE, day2), p2))
            status = self._run(root, window=window, entries=[e])
            self.assertEqual(status, "sampled")

            month_path = root / "series" / TILE / "2026-03.bin"
            self.assertTrue(month_path.is_file())
            array = array_from_buffer(month_path.read_bytes(), slot_count=1, days=31)
            first = decode_cell(bytes(array[0, 0]))
            self.assertEqual(first.state, SeriesMarkState.VALID)
            self.assertEqual(first.gf, 40)
            fifteenth = decode_cell(bytes(array[0, 14]))
            self.assertEqual(fifteenth.gf, 55)
            # An unsampled day in the month stays a gap, never all-zero bytes.
            gap = decode_cell(bytes(array[0, 1]))
            self.assertEqual(gap.state, SeriesMarkState.NO_DATA)

    def test_never_writes_a_slot_map_file(self) -> None:
        """Backfill only ever reads the slot map - see the module docstring."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            e = entry("node/1", col=0.0, row=0.0)
            day = date(2026, 3, 1)
            p = product(day, {(0, 0): (10, 0, at_epoch(day))})
            window = ((triplet(TILE, day), p),)
            before = (root / "index" / SLOT_DIRECTORY / f"{TILE}.json")
            self._run(root, window=window, entries=[e])
            after_bytes = before.read_text()
            # write_slot_map's own document is stable/sorted-keys, so a
            # rewrite (even an identical one) would still be detectable if it
            # touched anything about the map's shape; more directly, confirm
            # backfill_object_series module never imports the writer at all.
            import nevaio_pipeline.backfill_object_series as module

            self.assertFalse(hasattr(module, "write_slot_map"))
            self.assertFalse(hasattr(module, "extend_slot_map"))
            self.assertIn("node/1", after_bytes)


class MergeIntoExistingMonthTests(unittest.TestCase):
    """The coordinator's fix: merge into a published month, never skip or overwrite it."""

    def _write_existing(self, series_dir: Path, slot_count: int, cells: dict[tuple[int, int], tuple[int, int]]) -> Path:
        """Write a raw existing month file: cells[(slot, day_index)] = (gf, packed_byte)."""

        array = new_month_array(slot_count, 2026, 3)
        for (slot, day_index), (gf, packed) in cells.items():
            array[slot, day_index, 0] = gf
            array[slot, day_index, 1] = packed
        path = series_dir / TILE / "2026-03.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(buffer_from_array(array))
        return path

    def _run_with_window(
        self, root: Path, window: tuple, entries: list[ObjectIndexEntry], slot_ids: tuple[str, ...] | None = None
    ) -> str:
        index_dir = root / "index"
        series_dir = root / "series"
        write_shard(index_dir, TILE, entries)
        write_slot_map(index_dir, SlotMap(tile=TILE, slot_ids=slot_ids or tuple(e.id for e in entries)))
        grid = RasterGrid(f"EPSG:{32600 + ZONE}", TRANSFORM, WIDTH, HEIGHT)
        catalog_products = tuple(SimpleNamespace(product_date=t.product_date) for t, _ in window)
        with (
            patch(
                "nevaio_pipeline.backfill_object_series.discover_window_products",
                return_value={TILE: catalog_products},
            ),
            patch("nevaio_pipeline.backfill_object_series.download_products") as download,
            patch(
                "nevaio_pipeline.backfill_object_series._downloaded_triplets",
                return_value={TILE: tuple(t for t, _ in window)},
            ),
            patch(
                "nevaio_pipeline.backfill_object_series.load_tile_products",
                return_value=LoadedTile(tile=TILE, grid=grid, products=tuple(p for _, p in window)),
            ),
        ):
            status = backfill_tile_month(
                TILE, 2026, 3, raw_dir=root / "raw", object_index_dir=index_dir, series_output_dir=series_dir
            )
            return status, download

    def test_fills_only_the_missing_days_of_a_partial_existing_month(self) -> None:
        """The bug report: a daily-job month file with only its tail filled in."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            series_dir = root / "series"
            e = entry("node/1", col=0.0, row=0.0)
            # Existing: only day 13 (index 12) has real data, days 1-12 empty -
            # exactly the reported shape (a September daily run only reaching
            # the last few days of August).
            self._write_existing(series_dir, slot_count=1, cells={(0, 12): (60, 0)})

            day1 = date(2026, 3, 1)
            day13 = date(2026, 3, 13)
            p1 = product(day1, {(0, 0): (10, 0, at_epoch(day1))})
            p13 = product(day13, {(0, 0): (99, 0, at_epoch(day13))})  # would differ from existing
            window = ((triplet(TILE, day1), p1), (triplet(TILE, day13), p13))

            status, download = self._run_with_window(root, window, [e])
            self.assertEqual(status, "sampled")
            download.assert_called_once()

            array = array_from_buffer((series_dir / TILE / "2026-03.bin").read_bytes(), slot_count=1, days=31)
            # The previously missing day is now filled in.
            self.assertEqual(decode_cell(bytes(array[0, 0])).gf, 10)
            # The already-published day is untouched, byte for byte - not
            # replaced with this run's own (different) resampled value.
            self.assertEqual(decode_cell(bytes(array[0, 12])).gf, 60)

    def test_a_slot_beyond_the_current_slot_map_is_preserved_not_truncated(self) -> None:
        """A published file longer than this run's own slot-map snapshot.

        Simulates the daily job extending the slot map and republishing a
        longer file after this run already fetched an older, smaller slot map
        - the race the module docstring calls out. The extra slot's bytes are
        real published data other readers' offsets depend on and must survive
        untouched, even though this run's own slot map has never heard of it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            series_dir = root / "series"
            e = entry("node/1", col=0.0, row=0.0)
            # Existing file has 2 slots; this run's slot map only knows slot 0.
            self._write_existing(series_dir, slot_count=2, cells={(1, 9): (77, 0)})

            day = date(2026, 3, 1)
            p = product(day, {(0, 0): (5, 0, at_epoch(day))})
            window = ((triplet(TILE, day), p),)

            status, _ = self._run_with_window(root, window, [e], slot_ids=("node/1",))
            self.assertEqual(status, "sampled")

            array = array_from_buffer((series_dir / TILE / "2026-03.bin").read_bytes(), slot_count=2, days=31)
            self.assertEqual(array.shape[0], 2)
            # Slot 1's data - entirely unknown to this run's slot map - survives.
            self.assertEqual(decode_cell(bytes(array[1, 9])).gf, 77)
            # Slot 0 got this run's own sample.
            self.assertEqual(decode_cell(bytes(array[0, 0])).gf, 5)

    def test_already_complete_skips_sampling_entirely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            series_dir = root / "series"
            e = entry("node/1", col=0.0, row=0.0)
            day1 = date(2026, 3, 1)
            self._write_existing(series_dir, slot_count=1, cells={(0, 0): (60, 0)})

            window = ((triplet(TILE, day1), product(day1, {})),)
            status, download = self._run_with_window(root, window, [e])

            self.assertEqual(status, "already-complete")
            download.assert_not_called()
            # The file is untouched.
            array = array_from_buffer((series_dir / TILE / "2026-03.bin").read_bytes(), slot_count=1, days=31)
            self.assertEqual(decode_cell(bytes(array[0, 0])).gf, 60)

    def test_a_rerun_after_a_full_merge_changes_nothing(self) -> None:
        """Idempotency: a re-dispatched chunk must not perturb a completed month."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            series_dir = root / "series"
            e = entry("node/1", col=2.0, row=3.0)
            day1 = date(2026, 3, 1)
            day15 = date(2026, 3, 15)
            p1 = product(day1, {(3, 2): (40, 1, at_epoch(day1))})
            p15 = product(day15, {(3, 2): (55, 2, at_epoch(day15))})
            window = ((triplet(TILE, day1), p1), (triplet(TILE, day15), p15))

            first_status, _ = self._run_with_window(root, window, [e])
            self.assertEqual(first_status, "sampled")
            first_bytes = (series_dir / TILE / "2026-03.bin").read_bytes()

            second_status, second_download = self._run_with_window(root, window, [e])
            self.assertEqual(second_status, "already-complete")
            second_download.assert_not_called()
            second_bytes = (series_dir / TILE / "2026-03.bin").read_bytes()
            self.assertEqual(first_bytes, second_bytes)


class BackfillMonthTests(unittest.TestCase):
    def test_empty_tiles_is_a_harmless_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = backfill_month(
                year=2026, month=3, tiles=(),
                raw_dir=root / "raw", object_index_dir=root / "index", series_output_dir=root / "series",
            )
            self.assertEqual(receipt["tilesRequested"], [])
            self.assertEqual(receipt["sampled"], [])
            self.assertFalse((root / "series").exists())

    def test_aggregates_status_across_tiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_shard(root / "index", "31TFK", [entry("node/1", col=0.0, row=0.0)])
            write_slot_map(root / "index", SlotMap(tile="31TFK", slot_ids=("node/1",)))
            with patch(
                "nevaio_pipeline.backfill_object_series.discover_window_products",
                return_value={},
            ):
                receipt = backfill_month(
                    year=2026, month=3, tiles=["31TFK", "31TFL"],
                    raw_dir=root / "raw", object_index_dir=root / "index", series_output_dir=root / "series",
                )
            self.assertEqual(receipt["noProducts"], ["31TFK"])
            self.assertEqual(receipt["noShard"], ["31TFL"])
            self.assertEqual(receipt["sampled"], [])


if __name__ == "__main__":
    unittest.main()
