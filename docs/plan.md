# Current plan

**Status:** Real GFSC pipeline in progress - AS-OF core, raster adapter, and seam policy implemented.
**Date:** 2026-08-26

## Why this replaces the original reconnaissance plan

The original plan (`docs/archive/original-reconnaissance-plan.md`) sequenced about eight documentation-heavy phases before any visible output. Good instincts (decide from real data, not assumptions) but too much process before anything runs. This doc replaces it as the thing to actually follow. The original is kept for reference only - its sample-area table, freshness-analysis structure, and quality-code questions are still useful *inputs* to Track B below, just not a phase gate.

Two independent tracks run in parallel and converge at one milestone: a real GFSC tile rendered on a real map.

## Track A - Map shell (`app/`)

Goal: a mobile-friendly topo map, no snow data yet.

- MapLibre GL JS + an OSM-based outdoor/topo basemap (exact provider TBD - compare a couple of free options, at least one with contour/hillshade support, and pick one)
- Pan/zoom, responsive layout, deployable as a static site
- No dependency on Track B - this can start immediately

## Track B - GFSC reconnaissance (`recon/`)

Goal: understand what the real GFSC data looks like over the Alps + Italian Apennines before committing to a pipeline design.

1. Get Copernicus/WEkEO/CDSE access working (see `docs/spec.md` section 4.1 for links). If access isn't set up yet, this is the literal first step.
2. Pick 3-4 contrasting sample areas: glaciated high Alps, forested Alpine foothills, Apennines, and one location near an MGRS tile boundary. One recent ~60-90 day window is enough to start - widen later only if something's ambiguous.
3. Download real GFSC products for those samples directly (no separate catalogue-only pass first - a handful of tiles/dates is nowhere near the 500-products-per-run limit, and downloading gives you the catalogue metadata for free).
4. Inspect what you actually got: resolution/projection, quality-tier (0-3) distribution, how often cloud/no-data shows up, what a real time series at one point looks like.
5. Write findings to `recon/findings.md` as short running bullet notes - not a formal report.

## Converge: first real snow tile - DONE

Take one real downloaded GFSC raster from Track B, reproject/tile it, and render it as an overlay on the Track A map. This is the first real milestone. It answers most of the remaining open questions from both tracks at once (does the projection actually line up, does the resolution look reasonable at the zoom levels people will actually use, etc).

**Outcome.** `recon/make_overlay.py` reprojects one GFSC product (Ortles-Cevedale, 6 Feb 2026) from native UTM to EPSG:3857 and writes a paletted PNG plus a JSON sidecar into `app/public/snow/`; the app loads it as a MapLibre `image` source. Also added the spec section 5.2 snow on/off toggle and Copernicus attribution. Full notes in `recon/findings.md`.

- **Projection lines up** - verified numerically (11 landmarks, 300 random points, 0 unexplained mismatches) as well as visually: snow-free pixels trace the Adige valley exactly.
- **60 m is fine at z8-11, visibly blocky at z13+** - good enough for "is this face snow-covered", too coarse for an individual couloir. That's the concrete trigger for spec section 15 item 10.
- **An EPSG:3857 `image` source needs no tiling pipeline** - worth keeping in mind for how much machinery the real pipeline actually requires.
- Two new inputs to the formerly open section 15 visual-encoding decision came out of looking at it: `nearest` vs `linear` resampling is an honesty tradeoff, and grey cloud is confusable with rock on this basemap. A third - snow at full opacity hiding the shaded relief - turned out to be a layer-order problem and is already fixed (the basemap's hillshade is moved above the snow).

## After convergence

- **DONE - Freeze snow-data semantics from reconnaissance.** Sections 5.2-5.4, 7.1, and 9.2 of `docs/spec.md` now fix the visual encoding, quality/category handling, AS-OF selection, 14-day staleness ceiling, prolonged-gap behavior, and no-interpolation historical-chart rule. The former section 15 items 1-5 have been removed from the open list.
- **IN PROGRESS - Build the real GFSC data pipeline.** `pipeline/asof.py` applies the frozen per-pixel selection, category, quality, and staleness rules; `pipeline/raster_io.py` discovers complete GF/GF-QA/AT triplets and validates their source grids; `pipeline/mosaic.py` merges overlapping MGRS/UTM-zone composites on a common grid with a deterministic evidence-first rule; `pipeline/tiles.py` colorizes a merged composite per the frozen spec 5.2/5.4 visual encoding and writes it as standard `{z}/{x}/{y}.png` Web Mercator tiles. Next: wire up the daily fetch/schedule/publish job - a GitHub Actions cron that discovers today's products, runs asof -> mosaic -> tiles end to end for the full Alps+Apennines AOI, and writes the result straight into `app/public/` for the existing Netlify deploy to serve (**decided 2026-08-26**, see `docs/spec.md` section 15 item 8 and `docs/worklog.md` - no object storage or on-demand tile server for MVP; that's deferred along with historical AS-OF map browsing, spec section 5.3). Delete `recon/` when those duties are replaced (keeping `findings.md`); its one-image overlay remains scaffolding until then.
- **DONE - Frontend hosting.** `app/` deploys to Netlify (https://spikely.netlify.app), connected to this GitHub repo and auto-deploying on every push to `main`. See `docs/agent-guide.md` for build config.
- **DONE - Data-pipeline hosting/storage architecture for MVP (2026-08-26).** Daily GitHub Actions job -> static tiles in `app/public/` -> served by the existing Netlify deploy. No object storage or dynamic tile-rendering service for MVP; see `docs/worklog.md` for the full brainstorm and the revisit trigger for arbitrary historical map dates.
- Pick the rest of the stack: hosted routing API (for the A-to-B planner), geocoder.
- Build out the rest of `docs/spec.md` in vertical slices: search, OSM object panel + historical chart, A-to-B routing + snow/elevation profile.

## Explicitly not doing yet

Full Europe coverage, user accounts, saved routes, GPX/KML upload, native Android app, offline support. See `docs/spec.md` sections 13-14 for the full list.
