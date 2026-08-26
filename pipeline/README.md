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

`preview.py` is the intentionally narrower first end-to-end run. It discovers
and downloads exactly one newest complete GFSC product per MGRS tile, renders
the full MVP area, and can publish immutable XYZ tiles plus an atomic
`latest.json` pointer to Cloudflare R2. This preview does **not** yet apply the
production 14-day cross-product AS-OF fallback; its manifest labels that
limitation explicitly.

Run its tests from the repository root with the existing Python environment:

```sh
recon/.venv/bin/python -m unittest discover -s pipeline/tests
```

Build a local full-area preview without publishing it:

```sh
recon/.venv/bin/python -m pipeline.preview \
  --raw-dir /tmp/spikely-gfsc/raw \
  --work-dir /tmp/spikely-gfsc/work \
  --output-dir /tmp/spikely-gfsc/output
```

The GitHub Actions entry point is `Publish latest GFSC preview`. It is manual
only: there is deliberately no cron schedule or historical backfill until the
latest-data preview has been inspected in the app. Cloudflare bucket, token,
GitHub variable, invocation, and verification instructions are in
[`docs/r2-setup.md`](../docs/r2-setup.md).
