from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from affine import Affine
import numpy as np
import rasterio
from rasterio.crs import CRS

from pipeline.raster_io import discover_product_triplets, load_tile_products


class RasterIoTests(unittest.TestCase):
    tile = "32TPS"
    product_date = date(2026, 2, 6)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_discovers_and_loads_a_valid_triplet(self) -> None:
        product_dir = self._write_product()

        triplets = discover_product_triplets(self.root)
        loaded = load_tile_products(triplets)

        self.assertEqual(product_dir.name, triplets[0].product)
        self.assertEqual(loaded.tile, self.tile)
        self.assertEqual(loaded.grid.crs, "EPSG:32632")
        self.assertEqual(loaded.grid.width, 2)
        self.assertEqual(loaded.grid.height, 2)
        self.assertEqual(len(loaded.products), 1)
        np.testing.assert_array_equal(loaded.products[0].gf, [[0, 50], [100, 255]])
        np.testing.assert_array_equal(loaded.products[0].quality, [[0, 1], [3, 255]])
        np.testing.assert_array_equal(
            loaded.products[0].acquisition_time,
            [[1_770_000_000, 1_770_000_001], [1_770_000_002, 0]],
        )

    def test_rejects_an_incomplete_product(self) -> None:
        product_dir = self._write_product()
        (product_dir / f"{product_dir.name}_AT.tif").unlink()

        with self.assertRaisesRegex(ValueError, "incomplete GFSC product.*AT"):
            discover_product_triplets(self.root)

    def test_rejects_grid_mismatch_between_layers(self) -> None:
        self._write_product(at_transform=Affine.translation(600_060, 5_100_000) * Affine.scale(60, -60))

        with self.assertRaisesRegex(ValueError, "grid mismatch"):
            load_tile_products(discover_product_triplets(self.root))

    def test_rejects_unexpected_layer_metadata(self) -> None:
        self._write_product(gf_nodata=0)

        with self.assertRaisesRegex(ValueError, "GF raster has nodata 0.0, expected 255"):
            load_tile_products(discover_product_triplets(self.root))

    def test_rejects_duplicate_dates_and_mixed_tiles(self) -> None:
        self._write_product(version="V101")
        self._write_product(version="V102")

        with self.assertRaisesRegex(ValueError, "multiple GFSC product versions"):
            discover_product_triplets(self.root)

        other_root = self.root / "other"
        self._write_product(root=other_root, tile="33TUM")
        first = discover_product_triplets(self.root / "CLMS_WSI_GFSC_060m_T32TPS_20260206P7D_COMB_V101")
        second = discover_product_triplets(other_root)
        with self.assertRaisesRegex(ValueError, "exactly one MGRS tile"):
            load_tile_products([*first, *second])

    def _write_product(
        self,
        *,
        root: Path | None = None,
        tile: str | None = None,
        version: str = "V102",
        gf_nodata: int = 255,
        at_transform: Affine | None = None,
    ) -> Path:
        destination = root or self.root
        use_tile = tile or self.tile
        stem = f"CLMS_WSI_GFSC_060m_T{use_tile}_20260206P7D_COMB_{version}"
        product_dir = destination / stem
        product_dir.mkdir(parents=True, exist_ok=True)
        transform = Affine.translation(600_000, 5_100_000) * Affine.scale(60, -60)
        arrays = {
            "GF": (np.array([[0, 50], [100, 255]], dtype=np.uint8), "uint8", gf_nodata, transform),
            "GF-QA": (np.array([[0, 1], [3, 255]], dtype=np.uint8), "uint8", 255, transform),
            "AT": (
                np.array([[1_770_000_000, 1_770_000_001], [1_770_000_002, 0]], dtype=np.uint32),
                "uint32",
                0,
                at_transform or transform,
            ),
        }
        for layer, (array, dtype, nodata, layer_transform) in arrays.items():
            with rasterio.open(
                product_dir / f"{stem}_{layer}.tif",
                "w",
                driver="GTiff",
                width=2,
                height=2,
                count=1,
                dtype=dtype,
                crs=CRS.from_epsg(32632),
                transform=layer_transform,
                nodata=nodata,
            ) as dataset:
                dataset.write(array, 1)
        return product_dir
