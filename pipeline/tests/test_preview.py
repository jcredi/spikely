from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from affine import Affine

from pipeline.preview import _downloaded_triplets, _local_latest, _parse_date, build_preview
from pipeline.fetch import CatalogProduct
from pipeline.raster_io import ProductTriplet, RasterGrid


def triplet(tile: str, day: date, version: str) -> ProductTriplet:
    product = f"CLMS_WSI_GFSC_060m_T{tile}_{day:%Y%m%d}P7D_COMB_{version}"
    base = Path(product)
    return ProductTriplet(product, tile, day, version, base / "gf", base / "qa", base / "at")


class PreviewHelpersTests(unittest.TestCase):
    def test_parse_date_accepts_iso_and_rejects_other_formats(self) -> None:
        self.assertEqual(_parse_date("2026-02-10"), date(2026, 2, 10))
        with self.assertRaisesRegex(Exception, "YYYY-MM-DD"):
            _parse_date("10/02/2026")

    def test_local_latest_filters_future_dates_and_resolves_versions(self) -> None:
        as_of = date(2026, 2, 10)
        discovered = [
            triplet("32TPS", date(2026, 2, 9), "V100"),
            triplet("32TPS", as_of, "V101"),
            triplet("32TPS", as_of, "V102"),
            triplet("32TPS", date(2026, 2, 11), "V999"),
        ]
        with patch("pipeline.preview.discover_product_triplets", return_value=discovered):
            selected = _local_latest(Path("raw"), ["32TPS"], as_of)
        self.assertEqual(selected["32TPS"].version, "V102")

    def test_local_latest_reports_all_missing_tiles(self) -> None:
        with patch("pipeline.preview.discover_product_triplets", return_value=[]):
            with self.assertRaisesRegex(ValueError, "32TPS, 33TUM"):
                _local_latest(Path("raw"), ["33TUM", "32TPS"], date(2026, 2, 10))

    def test_downloaded_triplets_maps_catalog_products_and_reports_missing(self) -> None:
        found = triplet("32TPS", date(2026, 2, 10), "V100")
        catalog = CatalogProduct("32TPS", found.product_date, found.version, found.product, {})
        with patch("pipeline.preview.discover_product_triplets", return_value=[found]):
            selected = _downloaded_triplets(Path("raw"), {"32TPS": catalog})
        self.assertIs(selected["32TPS"], found)

        missing = CatalogProduct("33TUM", found.product_date, "V100", "missing-product", {})
        with patch("pipeline.preview.discover_product_triplets", return_value=[found]):
            with self.assertRaisesRegex(ValueError, "missing-product"):
                _downloaded_triplets(Path("raw"), {"33TUM": missing})

    def test_build_preview_writes_latest_manifest_and_hands_off_completed_run(self) -> None:
        first = triplet("32TPS", date(2026, 2, 9), "V100")
        second = triplet("33TUM", date(2026, 2, 10), "V100")
        grid = RasterGrid("EPSG:3857", Affine(1, 0, 0, 0, -1, 1), 1, 1)

        def persist(path, _tile) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            with (
                patch("pipeline.preview._local_latest", return_value={"32TPS": first, "33TUM": second}) as local,
                patch("pipeline.preview.load_tile_products", return_value=SimpleNamespace(grid=grid, products=(object(),))),
                patch("pipeline.preview.compose_as_of", return_value=object()),
                patch("pipeline.preview.save_snapshot", side_effect=persist),
                patch("pipeline.preview.render_snapshots", return_value=[Path("one.png"), Path("two.png")]),
                patch("pipeline.preview._bounds_wgs84", return_value=[5.0, 40.0, 16.0, 48.0]),
                patch("pipeline.preview.publish_to_r2") as publish,
            ):
                metadata = build_preview(
                    as_of_date=date(2026, 2, 10),
                    tiles=["33tum", "32TPS", "32TPS"],
                    raw_dir=root / "raw",
                    work_dir=root / "work",
                    output_dir=output,
                    fetch=False,
                    publish=True,
                )

            local.assert_called_once_with(root / "raw", ("32TPS", "33TUM"), date(2026, 2, 10))
            self.assertEqual(metadata["sourceTiles"], ["32TPS", "33TUM"])
            self.assertEqual(metadata["tileCount"], 2)
            self.assertEqual(metadata["bounds"], [5.0, 40.0, 16.0, 48.0])
            run_dir = output / "runs" / str(metadata["runId"])
            self.assertEqual(json.loads((run_dir / "run.json").read_text()), metadata)
            latest = json.loads((output / "latest.json").read_text())
            self.assertEqual(latest["tiles"], [f"runs/{metadata['runId']}/tiles/{{z}}/{{x}}/{{y}}.png"])
            publish.assert_called_once_with(run_dir, metadata)


if __name__ == "__main__":
    unittest.main()
