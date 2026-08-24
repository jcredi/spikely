# Recon findings (running notes)

## 2026-08-25 - setup, before any real GFSC download

- No personal Copernicus/WEkEO/CDSE registration needed for GFSC via the HR-WSI S3
  client (`recon/vendor/hrwsi/`). The script uses a read-only access key hardcoded
  in `s3_hrwsi_downloader.py` itself, pointing at a CloudFerro S3 endpoint
  (`s3.WAW3-2.cloudferro.com`, bucket `HRWSI`) - consistent with Copernicus's
  full/open/free data policy. Confirmed by reading the script source directly,
  not just the README.
- Client's own install docs are conda-only (`env.yaml`); all its deps
  (boto3, geopandas, pyproj, pyogrio, shapely, retry, tqdm) have PyPI wheels for
  Python 3.14 (confirmed via `pip install --dry-run`), so `recon/.venv` + pip is
  fine, no conda needed.
- Verified the "MGRS tile-boundary" sample point against the client's own
  `MGRS_tiles.gpkg` rather than guessing: tiles overlap by design (~10km margin),
  so a boundary point needs to fall inside the overlap of two tiles' polygons, not
  just near a visual edge. My first guess (11.95, 46.45) landed cleanly inside
  `32TQS` only - not a boundary case at all. Computed actual tile overlaps instead:
  - `32TPS` & `32TQS` overlap centered ~(11.667, 46.430)
  - `32TQS` & `33TUM` overlap centered ~(12.713, 46.431) - this one is the more
    interesting case since it's also a UTM zone 32/33 seam, not just an MGRS grid
    edge within one zone
  - Picked **(12.5, 46.6)**, near Sesto / Val Comelico in the Dolomites - confirmed
    it falls inside both `32TQS` and `33TUM`.

## 2026-08-25 - first real GFSC downloads (window: 2026-01-15 to 2026-04-15)

Downloaded all 4 sample areas via `-query_and_download`, `-wkt` boxes, `-epsg 4326`:

| Area | Tile(s) resolved | Products | Size |
|---|---|---|---|
| `ortles-cevedale-glaciers` | 32TPS | 91 | 334 MB |
| `paneveggio-forest` | 32TPS, 32TQS | 182 | 598 MB |
| `gran-sasso-apennines` | 33TUH, 33TUG | 125 | 145 MB |
| `dolomites-tile-boundary` | 33TUM, 32TQS | 182 | 508 MB |

The Dolomites query resolving to exactly `33TUM` + `32TQS` empirically confirms the tile-boundary
point computed above was correct.

### Format, resolution, projection

Each product = one MGRS/S2 tile (110x110 km, 1830x1830 px at 60m) in native UTM zone
(EPSG:326XX), delivered daily as 4 GeoTIFFs + 1 XML per date:
`AT` (uint32), `GF` (uint8), `GF-QA` (uint8), `QAFLAGS` (uint8), `_MTD.xml`.
Filename pattern: `CLMS_WSI_GFSC_060m_<TILE>_<YYYYMMDD>P7D_COMB_<VERSION>_<LAYER>`. The `P7D`
is not a typo/mystery - **confirmed from the official Product User Manual** (fetched
directly, Table 7 / p.44-48, linked from spec.md section 4.1) that it means "aggregation
duration in days retrospectively from the product date" - i.e. gap-filling looks back up to
7 days.

### Authoritative value codebook (from the PUM, not guessed)

- **GF** (the 0-100% layer) also carries non-percentage codes: `205` = cloud/cloud-shadow,
  `210` = inland water (static mask), `255` = no data.
- **GF-QA**: `0`=high, `1`=medium, `2`=low, `3`=minimal quality, plus the same `205`/`210`/`255`
  codes for cloud/water/nodata pixels.
- **QAFLAGS** (bitmask): bit0=hillshade coverage, bit1=tree-cover-density (TCD) too high
  (>90%) for accurate forest correction, bit2=snow estimated despite cloud (except high
  cloud), bit3=TCD undefined, bit4=shaded-snow via hillshade threshold, bit5-6=unused,
  **bit7=sensor type (0=optical/FSC, 1=radar/SWS)**.
- **AT**: per-pixel Unix timestamp of the actual satellite acquisition used - confirmed by
  decoding real values (e.g. `1770787121` -> 2026-02-11 05:18 UTC). This is a much finer
  freshness signal than the quality tier alone - it lets us compute real observation age per
  pixel relative to any AS-OF date, directly (spec section 5.2/9.2).
  - Explains an earlier puzzle: in the Ortles sample, `QAFLAGS=128` (bit7 set, i.e.
    radar/SWS-sourced) lined up exactly with `GF=100` pixels and nothing else - consistent
    with the PUM's statement that "wet snow pixels from SWS are considered 100% FSC for
    gap-filling purposes." Not a coincidence, not a bug - documented behavior.

### Point time series (Paneveggio forest, 11.75, 46.30, all 91 days)

Real per-day extraction at one pixel, full window - see this as the first concrete answer to
`docs/plan.md` step 4 ("what does a real time series at one point look like"):

- **Quality tier was `3` (minimal) on every single valid day, no exceptions.** Never 0/1/2.
  This one point is forested, and QAFLAGS bit1 (TCD>90%) plus the PUM's own text ("spatial
  gap filling is mainly applicable... in non-forested, non-urban... areas") suggests this
  isn't a fluke - forested terrain may systematically cap out at "minimal" quality. This
  matters a lot for spec section 15 item 2 (quality-tier treatment): a policy of "only show
  high/medium quality" would blank out forested regions entirely, not just degrade them.
- **NODATA gaps up to 14 consecutive days** (2026-02-08 to 2026-02-21) at this single pixel -
  longer than the PUM's stated 7-day max compositing window and its "5 days under good
  conditions" claim. This is a real, observed instance of the "prolonged cloud gap" spec
  section 15 item 4 explicitly flags as an open decision - worth widening the historical-chart
  interpolation/carry-forward discussion around this kind of multi-week gap, not just 2-3 day
  gaps.
  - CLOUD (`205`, distinct from NODATA/`255`) also appeared in its own multi-day blocks
    (e.g. 2026-02-22 to 2026-02-27), so the two states are genuinely distinguishable in
    practice, not just in theory.
  - Where a value *was* available, only `33%` and `100%` appeared at this point (no smooth
    gradient) - plausible for one pixel's real snow accumulation/melt pattern, but shouldn't
    be generalized from a single point.

### Open follow-ups

- Haven't yet checked the glacier (Ortles) or Apennine (Gran Sasso) time series the same way -
  worth doing before finalizing the AS-OF/quality rules in spec section 15.
- Haven't yet rendered/reprojected anything for the map (that's the "first real snow tile"
  convergence milestone in `docs/plan.md`, not part of this reconnaissance pass).
