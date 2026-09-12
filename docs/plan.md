# Current plan

**This file is the future tense only.** What is next, what is open, what we are
deliberately not doing. When something ships it *leaves* this file - the record
of what was done and why lives in [`worklog.md`](worklog.md), newest entry
first. Do not add a "done" section here; it only grows a third copy of history
that then drifts.

**Status (2026-09-12).** MVP snow layer is functionally complete and live on
`https://nevaio.netlify.app`: the real GFSC pipeline composes the frozen spec
section 9.2 AS-OF rule over a 30-day window across 58 MGRS tiles, publishes to
Cloudflare R2 on a daily 04:35 UTC schedule, and has run unattended since
2026-08-28. Place search (section 6.1) is done, on MapTiler Geocoding. A
security review and its remediation closed on 2026-09-09; posture is in
[`security.md`](security.md). The mobile-first UI was verified on a real
handset on 2026-09-11.

**Spec section 7 - the OSM object panel - completed 2026-09-12** and is live:
the object index is published to R2 (54 shards, 211,881 objects), selection
covers all 58 tiles, the daily pipeline samples per-object GFSC, and the panel
draws real snow history over a trailing 30-day window. **Next work is A-to-B
routing (item 2)**; item 1 is now watching rather than building.

## Next, in order

1. **OSM object panel - spec section 7 is complete, and now needs watching
   rather than building.** Selection, the panel, the chart, the published
   index, the daily sampling and the historical backfill all shipped
   2026-09-12; the chart draws real per-object GFSC history on the deployed
   site. What is left is operational, not construction:
   - **Watch the next few daily runs.** The first run created every tile's
     permanent slot map; subsequent runs exercise the *extend* path, which has
     never run. The invariant to watch is that slot counts only ever grow and
     that `series/<TILE>/<YYYY-MM>.bin` length stays `slots x days x 2`.
   - **The backfill exists but is probably not needed.** The daily job samples
     its whole 31-day window every run, so the first run alone populated 13
     Aug - 11 Sept, and a trailing 30-day window is continuously covered
     without any backfill at all. `backfill-object-series.yml` is there for
     history *deeper* than 30 days, which since amendment v1.13 nothing
     requires. Run it only if that depth is wanted for its own sake; it merges
     rather than overwrites, so running it is safe but not free.
   - One open contract question from the first consumer: whether
     `bytes`/`sha256` stay in the shard index (the frontend does verify them).
   - Anything needing to know where Nevaio shows snow must ask
     `nevaio_pipeline.footprint`, not re-derive it.

2. **A-to-B routing + snow/elevation profile (spec section 8).** Needs a hosted
   routing provider chosen (spec section 15 item 6). **Decided 2026-09-11: the
   choice is made from a costed shortlist rather than cold** - a written
   options/pros-cons/recommendation pass covering the routing provider and the
   elevation/DEM source (section 15 item 7) comes first, then the owner picks.
   **Decided 2026-09-12: Mapbox Directions (`mapbox/walking`) for routing, and
   a precomputed Copernicus GLO-30 extract in R2 for elevation.** ORS was the
   pick for part of that day and was reversed the same day: its staff forbid
   delivering a key to a browser and it offers no domain restriction, which
   this app cannot work around without the backend it deliberately lacks.
   Before building: **create a separate, URL-restricted Mapbox token** - the
   default token cannot carry URL restrictions, and using it would discard the
   one control that makes a public token safe - and add `api.mapbox.com` to
   `connect-src` in `app/public/_headers` in the same change. Mapbox Directions
   returns no elevation, so the DEM is still needed; `du` the bucket first to
   confirm a GLO-30 extract fits beside the object index and the series.
   Fallback for elevation stays MapTiler Terrain-RGB.
   **The options pass behind this was delivered 2026-09-12:
   [`research/routing-and-dem-options.md`](research/routing-and-dem-options.md).
   The owner's pick is now the open step** - section 15 items 6 and 7 stay
   open, not closed by a recommendation. It recommends OpenRouteService
   `foot-hiking` (fallback: Mapbox Directions) and a precomputed Copernicus
   GLO-30 extract into the existing R2 bucket (fallback: MapTiler Terrain-RGB),
   each conditional on one check the doc names - ORS's real free quota from
   HeiGIT's own dashboard, and whether a GLO-30 extract fits the R2 headroom. Firm requirement, stronger
   than sections 8.4-8.5 currently read: observation freshness and quality must
   be shown clearly and prominently on the route profile, not "where
   practical". Spec section 15 item 11.
3. **Repository structure refactor, stage 4**
   ([`../REFACTOR.md`](../REFACTOR.md)). Stages 1 (dissolve `recon/`) and 2
   (package the pipeline) are done - 2026-09-09; stage 3 (regroup the frontend
   into `app/src/features/`) is done - 2026-09-12. Stage 4 (contracts) waits
   for the OSM object panel, which is the work that would actually consume a
   shared encoding - so it is gated on item 1, not on anything structural.
   When it starts, note that `REFACTOR.md`'s target tree was written
   2026-09-09 and has already drifted once: it names frontend files that no
   longer exist and renames that later work made wrong. Verify against the
   repository, as that document's own instructions say.

## Open

- **Spec section 15** is the canonical list of undecided product questions.
  Live ones: route sampling method and "snow-covered percentage" definition
  (1, 2), basemap/terrain provider (4), optional 20 m FSCOG layer (10).
  **Items 6 and 7 were decided 2026-09-12** from
  [`research/routing-and-dem-options.md`](research/routing-and-dem-options.md):
  routing is **Mapbox Directions** (`mapbox/walking`), elevation is a
  **precomputed Copernicus GLO-30 extract into the existing R2 bucket**.
  Routing was OpenRouteService for part of that day; it is not, because ORS
  forbids client-side keys and this app has no backend - see the correction in
  that document before reopening the question.
- **Create the URL-restricted Mapbox token** (owner console work, deferred
  2026-09-12 until routing is actually built). It must be a **new** token, not
  the account's default: Mapbox's URL restrictions do not apply to default
  tokens, so the default would ship unrestricted in a public bundle - the very
  problem that disqualified OpenRouteService. Restrict it to the Netlify
  origin, set it as a Netlify env var across all contexts, and deliberately do
  **not** mark it secret, for the same reason `VITE_MAPTILER_API_KEY` is not:
  Vite inlines `VITE_*` into the client bundle by design, so secret-scanning
  would fail the build on a value meant to reach the browser. `api.mapbox.com`
  joins `connect-src` in `app/public/_headers` in the same change.
- **Custom domain in front of the `r2.dev` endpoint** (security F10, optional
  pre-launch). Owner console work; needs an Admin-scoped Cloudflare token.
  `app/public/_headers` pins the bucket host in its CSP and must change in the
  same commit - see [`r2-setup.md`](r2-setup.md) step 4.
- **Snow tile 404s make the browser console noisy.** The pipeline publishes
  only tiles that contain data, but MapLibre requests the full grid inside the
  manifest's `bounds`, so every empty cell 404s - five in one production
  viewport on 2026-09-09. Functionally harmless and long-standing; the cost is
  that a real error can hide in the noise. Options when it is worth doing:
  publish a 1x1 transparent PNG for empty cells (simple, more objects in R2),
  or narrow the published `bounds`/per-zoom coverage so the grid matches what
  actually exists (cheaper at runtime, more pipeline work). Not urgent.
- **R2 free-tier headroom.** **Measured 2026-09-12: 40.79 MB across 7.07k
  objects** - far under the 10 GB allowance, but that is a *September* figure
  and must not be read as the steady state: the archive is mostly snow-free
  tiles right now. The projection that matters is mid-winter, where a 31-date
  archive is roughly 4.0 GB and ~109,000 objects. Against that, the object
  index (28.6 MB), the per-object series (~26 MB at the two-month depth
  amendment v1.13 leaves) and a Copernicus GLO-30 extract are the other
  claimants. The first two are rounding errors; **the DEM extract is the one
  worth sizing before it is built**, and its size is still an estimate. They
  have to fit in the remaining
  ~6 GB, or the date window shortens - `config.ASOF_CATALOGUE_DATES` is the
  one dial. Re-measure in midwinter, when the number means something - the
  September reading above cannot tell us whether the DEM fits.
- **The recovery path is unrehearsed** - revoke the publication key, restore
  trusted code, rebuild dependencies, republish known-good data.

## Explicitly not doing yet

Full Europe coverage, user accounts, saved routes, GPX/KML upload, native
Android app, offline support. See [`spec.md`](spec.md) sections 13-14 for the
full list.
