# GFSC data pipeline

Production snow-data processing lives here. The first vertical slice is the
pure per-pixel AS-OF compositor in `asof.py`; it implements the frozen rules in
`docs/spec.md` section 9.2 over already aligned GF, GF-QA, and AT arrays.

It deliberately does not yet fetch products, resolve MGRS overlaps, reproject,
write XYZ tiles, schedule jobs, or publish artifacts. Those layers should wrap
the semantic core rather than duplicate its decisions.

Run its tests from the repository root with the existing Python environment:

```sh
recon/.venv/bin/python -m unittest pipeline.tests.test_asof
```
