# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioned from `0.1.0` (2026-08-25), the first deploy.

## [Unreleased]

### Added
- GFSC XYZ tile renderer (`pipeline/tiles.py`) that colorizes a merged AS-OF
  composite per the frozen spec 5.2/5.4 visual encoding (snow-cover ramp,
  freshness-attenuated alpha, violet cloud, transparent water/stale/no-data)
  and slices it into standard `{z}/{x}/{y}.png` Web Mercator tiles, skipping
  fully-transparent ones. Eight focused tests, bringing the pipeline suite to
  25 tests.
- Latest-product-only GFSC preview pipeline: `pipeline/config.py` (62-tile
  Alps+Apennines MGRS coverage), `fetch.py` (newest-product-only Copernicus
  catalogue discovery/download), `snapshots.py` (memory-bounded per-metatile
  rendering), `preview.py` (end-to-end orchestration), and `publish.py`
  (atomic Cloudflare R2 upload - immutable run first, `latest.json` pointer
  last). Sixteen new tests, bringing the pipeline suite to 41.
- `.github/workflows/publish-latest-preview.yml`, a manual-dispatch-only
  GitHub Actions job that runs the preview pipeline and publishes to R2, and
  `docs/r2-setup.md` documenting bucket/token/CORS/GitHub secrets setup.
- Frontend now loads the R2/local `latest.json` XYZ tile manifest
  (`app/src/map/snowOverlay.ts`, `config.ts`, `main.ts`), falling back to the
  checked-in one-tile sample overlay if the manifest is unavailable.

### Added
- Full 58/62-tile MVP-area GFSC preview published to production R2, with the
  bucket's CORS policy applied and `VITE_SNOW_MANIFEST_URL` set on Netlify -
  `https://spikely.netlify.app` now serves the real snow-cover overlay,
  visually verified across multiple regions and zoom levels against the live
  site. See `docs/worklog.md` (2026-08-27).

### Changed
- Spec v1.3: deferred arbitrary historical AS-OF map-date browsing out of MVP
  scope (OSM-object historical chart is unaffected and stays required).
  Decided the MVP data-pipeline/storage architecture - a daily GitHub Actions
  job renders one static "latest conditions" tile set and republishes it
  through the existing Netlify deploy, no object storage or on-demand
  tile-rendering service for now - and set the EUR 20/month operating-cost
  ceiling. See `docs/worklog.md` (2026-08-26) for the full brainstorm.
- Spec v1.4: revised the above storage decision the same day, before any of
  it was built - the MVP pipeline instead publishes to Cloudflare R2 (chosen
  over Netlify Blobs and over the static-republish plan). Implemented and
  verified end-to-end against a real bucket with a live 3-tile smoke test.
  See `docs/worklog.md` (2026-08-26, "R2-based latest-only preview pipeline").
- Spec v1.5: recorded the 2026-08-27 production verification and the still-open
  items (cron schedule, AS-OF multi-day fallback, 4 tiles missing a current
  product). See `docs/worklog.md` (2026-08-27).

## [0.1.0] - 2026-08-25

### Added
- Production GFSC AS-OF semantic core (`pipeline/asof.py`) with deterministic
  AT/quality/product-date selection, categorical states, staleness output, and
  focused unit tests.
- GFSC GeoTIFF adapter (`pipeline/raster_io.py`) that discovers complete daily
  GF/GF-QA/AT triplets and rejects inconsistent source grids or metadata.
- GFSC overlap/UTM-seam mosaic (`pipeline/mosaic.py`) that applies the frozen
  water/freshness/quality fallback rule on a common output grid.
- MapLibre GL JS map shell (`app/`): MapTiler Outdoor basemap, pan/zoom,
  mobile-safe-area layout.
- GFSC snow-cover overlay: one reprojected Copernicus product (Ortles-Cevedale,
  6 Feb 2026) rendered as a MapLibre `image` source (`app/src/map/snowOverlay.ts`).
- Snow layer on/off toggle (`app/src/ui/snowControl.ts`).
- Copernicus attribution alongside the MapTiler/OSM credit.
- `recon/make_overlay.py` - reprojects a GFSC `GF.tif` to EPSG:3857, writes a
  paletted PNG + JSON sidecar, self-verifies georeferencing against the source
  raster. Scaffolding: superseded once the real data pipeline exists.
- `app/scripts/screenshot.mjs` - Playwright harness for visually verifying the
  overlay against the basemap at hiking-relevant zoom levels.
- GFSC reconnaissance (`recon/`): HR-WSI S3 client, 580 downloaded sample
  products across 4 areas, value codebook and data-quality findings
  (`recon/findings.md`).
- Netlify deployment: `app/` connected to this GitHub repo, auto-deploying
  `main` to https://spikely.netlify.app on every push.

### Changed
- Hillshade layer moved above the snow overlay so shaded relief remains
  visible under snow at full opacity, instead of lowering snow opacity.
- Frozen the GFSC MVP semantics from reconnaissance: exact coverage/freshness
  rendering, all-tier quality handling, categorical cloud/water/no-data states,
  a 14-day AS-OF staleness ceiling, and no historical-chart interpolation or
  carry-forward.
- Updated the reconnaissance overlay's cloud color from rock-like grey to the
  frozen violet category and regenerated its sample artifact.
- Removed the convergence-only "Zoom to data" button now that its throwaway
  purpose is complete.

### Changed (recordkeeping)
- Agent instructions split out of `.claude/CLAUDE.md` into a shared
  `docs/agent-guide.md`. `.claude/CLAUDE.md` and the new root `AGENTS.md`
  (OpenAI Codex's entry point) are now one-line adapters pointing to it, so
  Claude Code and Codex read the same guidance.
