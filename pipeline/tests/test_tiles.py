from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from affine import Affine
import numpy as np
from PIL import Image

from pipeline.asof import AsOfComposite, NO_AGE, NO_PRODUCT_DAY, NO_VALUE, PixelState
from pipeline.raster_io import RasterGrid
from pipeline.tiles import ORIGIN_SHIFT, render_rgba, write_xyz_tiles


def composite(state: int, *, fsc: int = NO_VALUE, freshness: float = 0.0, shape=(1, 1)) -> AsOfComposite:
    return AsOfComposite(
        as_of_date=date(2026, 2, 11),
        fsc=np.full(shape, fsc, dtype=np.uint8),
        quality=np.full(shape, 255, dtype=np.uint8),
        acquisition_time=np.zeros(shape, dtype=np.uint64),
        age_days=np.full(shape, NO_AGE, dtype=np.int32),
        source_product_day=np.full(shape, NO_PRODUCT_DAY, dtype=np.int32),
        state=np.full(shape, state, dtype=np.uint8),
        freshness=np.full(shape, freshness, dtype=np.float32),
    )


class RenderRgbaTests(unittest.TestCase):
    def test_color_ramp_at_frozen_stops(self) -> None:
        c = composite(PixelState.VALID, fsc=0, freshness=1.0)
        np.testing.assert_array_equal(render_rgba(c)[0, 0], [130, 160, 190, 26])

        c = composite(PixelState.VALID, fsc=50, freshness=1.0)
        np.testing.assert_array_equal(render_rgba(c)[0, 0], [200, 222, 240, 150])

        c = composite(PixelState.VALID, fsc=100, freshness=1.0)
        np.testing.assert_array_equal(render_rgba(c)[0, 0], [255, 255, 255, 224])

    def test_freshness_attenuates_alpha_only(self) -> None:
        aging = render_rgba(composite(PixelState.VALID, fsc=100, freshness=0.75))[0, 0]
        stale_band = render_rgba(composite(PixelState.VALID, fsc=100, freshness=0.45))[0, 0]

        np.testing.assert_array_equal(aging, [255, 255, 255, 168])
        np.testing.assert_array_equal(stale_band, [255, 255, 255, 101])

    def test_cloud_is_fixed_violet_regardless_of_freshness(self) -> None:
        rgba = render_rgba(composite(PixelState.CLOUD, freshness=0.0))[0, 0]
        np.testing.assert_array_equal(rgba, [168, 85, 247, 115])

    def test_water_stale_and_nodata_are_transparent(self) -> None:
        for state in (PixelState.WATER, PixelState.STALE, PixelState.NODATA):
            rgba = render_rgba(composite(state, freshness=0.0))[0, 0]
            np.testing.assert_array_equal(rgba, [0, 0, 0, 0])


def _world_grid() -> RasterGrid:
    """A 256x256 grid whose footprint is exactly the z0 tile (the whole world)."""

    resolution = (2 * ORIGIN_SHIFT) / 256
    transform = Affine.translation(-ORIGIN_SHIFT, ORIGIN_SHIFT) * Affine.scale(resolution, -resolution)
    return RasterGrid("EPSG:3857", transform, 256, 256)


class WriteXyzTilesTests(unittest.TestCase):
    def test_full_world_tile_written_at_z0(self) -> None:
        grid = _world_grid()
        c = composite(PixelState.VALID, fsc=100, freshness=1.0, shape=(256, 256))

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            written = write_xyz_tiles(c, grid, zooms=[0], out_dir=out_dir)

            self.assertEqual(written, [out_dir / "0" / "0" / "0.png"])
            tile = np.array(Image.open(written[0]).convert("RGBA"))
            self.assertEqual(tile.shape, (256, 256, 4))
            self.assertTrue((tile == [255, 255, 255, 224]).all())

    def test_full_world_source_covers_all_four_z1_tiles(self) -> None:
        grid = _world_grid()
        c = composite(PixelState.VALID, fsc=0, freshness=1.0, shape=(256, 256))

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            written = write_xyz_tiles(c, grid, zooms=[1], out_dir=out_dir)

            expected = {
                out_dir / "1" / str(x) / f"{y}.png" for x in (0, 1) for y in (0, 1)
            }
            self.assertEqual(set(written), expected)

    def test_fully_transparent_composite_writes_nothing(self) -> None:
        grid = _world_grid()
        c = composite(PixelState.NODATA, freshness=0.0, shape=(256, 256))

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            written = write_xyz_tiles(c, grid, zooms=[0, 1], out_dir=out_dir)

            self.assertEqual(written, [])
            self.assertFalse(any(out_dir.iterdir()))

    def test_partial_footprint_leaves_rest_of_tile_transparent(self) -> None:
        # A small source raster placed in one quadrant of the z1/x0/y0 tile.
        resolution = (2 * ORIGIN_SHIFT) / 256
        transform = Affine.translation(-ORIGIN_SHIFT, ORIGIN_SHIFT) * Affine.scale(resolution, -resolution)
        grid = RasterGrid("EPSG:3857", transform, 64, 64)
        c = composite(PixelState.VALID, fsc=100, freshness=1.0, shape=(64, 64))

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            written = write_xyz_tiles(c, grid, zooms=[1], out_dir=out_dir)

            self.assertEqual(written, [out_dir / "1" / "0" / "0.png"])
            tile = np.array(Image.open(written[0]).convert("RGBA"))
            self.assertTrue((tile[0:128, 0:128] == [255, 255, 255, 224]).all())
            self.assertTrue((tile[128:, :] == 0).all())
            self.assertTrue((tile[:, 128:] == 0).all())


if __name__ == "__main__":
    unittest.main()
