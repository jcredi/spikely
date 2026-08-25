# GFSC data pipeline

Production snow-data processing lives here. The first vertical slice is the
pure per-pixel AS-OF compositor in `asof.py`; it implements the frozen rules in
`docs/spec.md` section 9.2 over already aligned GF, GF-QA, and AT arrays.
`raster_io.py` discovers real daily GeoTIFF triplets and rejects incomplete,
misaligned, or unexpected source metadata before handing arrays to that core.
`mosaic.py` reprojects independently composed MGRS tiles with nearest-neighbour
resampling and merges overlaps using the frozen rule in spec section 9.3.
`tiles.py` colorizes a merged composite per the frozen visual encoding in spec
sections 5.2 and 5.4 and slices it into standard `{z}/{x}/{y}.png` Web Mercator
tiles.

It deliberately does not yet fetch products, schedule jobs, or publish
artifacts to storage. Those layers should wrap the semantic core rather than
duplicate its decisions.

Run its tests from the repository root with the existing Python environment:

```sh
recon/.venv/bin/python -m unittest discover -s pipeline/tests
```
