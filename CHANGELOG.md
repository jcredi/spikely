# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project doesn't use version numbers yet (pre-release, no deploy) - entries
accumulate under [Unreleased] until the first deploy, which becomes `0.1.0`.

## [Unreleased]

### Added
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
