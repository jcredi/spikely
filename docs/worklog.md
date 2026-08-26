# Working session log

A dated, narrative record of what was done, decided, and rejected each session -
newest first. `git log` has the diffs; this has the reasoning that produced them,
especially the roads *not* taken (a rejected approach usually costs real time to
rediscover if it isn't written down).

This is not a duplicate of other docs: `docs/spec.md` is frozen product intent,
`docs/plan.md` is what's next, `recon/findings.md` is what the data actually is.
This file is what *we* did and why, across sessions.

---

## 2026-08-26 - R2-based latest-only preview pipeline: built and live-verified

**Did:** Revised the storage half of the same-day "ship latest only" decision
below, then implemented and live-tested it. Compared three ways to serve the
daily-rendered tiles: (A) the originally-decided static republish through the
existing Netlify deploy, (B) Netlify Blobs, (C) Cloudflare R2. Chose R2, then
built `pipeline/config.py` (the 62-tile MGRS set covering a 60 km corridor
around the Alpine arc and Italian Apennine spine, resolved once against
Copernicus's own `MGRS_tiles.gpkg`), `fetch.py` (lists the HR-WSI S3 catalogue
and selects/downloads only the single newest complete GF/GF-QA/AT product per
tile, never historical ones), `snapshots.py` (compact per-tile `.npz`
composites plus memory-bounded rendering one z8 metatile at a time so the full
AOI never needs to fit in RAM at once), `preview.py` (chains discovery through
render to a local `latest.json` and optional R2 publish), and `publish.py`
(uploads the immutable run first, replaces `latest.json` last, so the app
never observes a partially-published run). Added `.github/workflows/publish-
latest-preview.yml` (manual `workflow_dispatch` only) and `docs/r2-setup.md`.
Updated `app/src/map/snowOverlay.ts`/`config.ts`/`main.ts` to load that XYZ
manifest, falling back to the checked-in one-tile sample overlay if it's
unreachable. Added 16 tests (41 total, all passing); `npm run build` is clean.

Then set up a real Cloudflare R2 bucket (bucket-scoped Object Read & Write API
token, Public Development URL enabled) and ran a live 3-tile smoke test
(`32TNS 32TNT 33TUN`) end to end: real Copernicus catalogue discovery and
download (2026-08-25 products), render (292 tiles across z8-11), atomic R2
upload, and a public fetch of both the resulting `latest.json` and one actual
tile PNG (`200`, valid 256x256 RGBA) - all successful. Credentials were kept
out of the coding session entirely: they live only in a gitignored
`pipeline/.env.r2.local` (matches the existing `.env.*.local` rule; template
committed as `pipeline/.env.r2.local.example`), sourced into a subshell and
never read or printed.

**Decided:**
- Cloudflare R2 over a static Netlify republish: R2 serves tiles as public CDN
  objects with no egress fee; republishing the full static site through
  Netlify on every run risks exceeding the Free plan's credit allowance well
  before meaningful traffic, per Netlify's current per-GB/per-request credit
  pricing. This revises this same MVP decision from earlier today (see the
  entry directly below) before any of it was built - the storage question
  turned out to need settling before the scheduler, not after.
- R2 over Netlify Blobs: Blobs are private to the owning site and need a
  Function/Edge Function to serve each read, turning every tile request into
  an extra hop and consuming Netlify request/bandwidth credits; R2 objects are
  fetched directly by the CDN. Blobs remain the better fit for the day this
  pipeline needs private, site-scoped state instead of public read-heavy
  raster tiles - not the case here.
- Immutable versioned run prefixes (`runs/<runId>/tiles/...`) plus a single
  short-TTL `latest.json` pointer, updated only after every object in the run
  has uploaded. This is what makes the publish atomic from the app's point of
  view and gives cheap rollback (point `latest.json` at a prior run) without
  needing R2 versioning or lifecycle rules yet.
- Keep the GitHub Actions workflow manual-dispatch only, no cron, until a
  human has visually verified real R2-served tiles in the running app - the
  smoke test proves the pipe works, not that the rendered result looks right.
- Preview scope stays "one newest product per MGRS tile," explicitly not the
  frozen section 9.2 multi-day AS-OF fallback - the manifest's `notice` field
  says so. Good enough to validate the whole path end-to-end; not yet the
  eventual daily production job.

**Rejected:**
- Building the scheduler/cron job before the storage architecture was
  settled, as originally planned earlier today - would have wired daily
  automation on top of a storage choice (static Netlify republish) that
  turned out to be the wrong one once actually compared against alternatives.
- Verifying R2 only via unit tests with a mocked S3 client - those already
  passed before any bucket existed and prove the upload *sequence* is
  correct, not that a real bucket/token/CORS-less public URL actually serves
  the result to a browser-shaped request. Ran a real 3-tile smoke test against
  the user's actual bucket instead.
- Pasting R2 credentials into the coding session to run the smoke test -
  used a gitignored local env file sourced into a subshell instead, so the
  values never appear in any transcript or tool output.

**Open / carried forward:** CORS policy not yet applied to the bucket (was
blocked on an empty bucket per Cloudflare's own CORS-editor prerequisite; the
smoke test just populated it, so this is now unblocked). No custom domain yet
- fine short-term, `r2.dev` is rate-limited but usable for this stage. No
visual verification yet of real R2-served tiles in the running app - the
actual point of this whole preview milestone, still pending. No cron schedule
- intentional. `recon/` not yet deleted. The single-newest-product-per-tile
limitation still needs a decision before this preview becomes the real daily
job (see `docs/plan.md` "Next session" list for the concrete order).

---

## 2026-08-26 - MVP data-pipeline/storage architecture: ship "latest only"

**Did:** Brainstormed the data-pipeline hosting/storage architecture (spec
section 15 item 8), triggered by realizing spec section 5.3 ("historical
AS-OF map date") is a required MVP feature, not just the section 7.1 point
chart - and that it implies a forever-growing daily raster archive back to
20 January 2025 (spec section 4.1), not just "today's snow state." Compared
two shapes: (A) daily GitHub Actions job renders one static "latest
conditions" tile set and republishes it through the existing Netlify deploy,
with arbitrary historical map dates deferred; (B) the same daily job instead
appends one compact per-day raster to object storage, plus a small always-on
or scale-to-zero Python/rasterio service that runs the frozen section 9.2
AS-OF selection on demand for any requested date/tile, cached aggressively
since a historical (date, tile) result never changes once computed.

**Decided:**
- Ship Option A for the MVP. It reuses 100% of the pipeline code already
  built (`asof.py`, `mosaic.py`, `tiles.py`) with zero throwaway work, adds
  no new infrastructure or cost beyond the existing free GitHub Actions +
  Netlify setup, and matches the project's running preference for the
  smallest thing that closes the loop over building ahead of validated need.
- Defer arbitrary historical AS-OF **map** browsing (spec section 5.3) out
  of MVP scope. The OSM-object **historical chart** (spec section 7.1) is
  unaffected and stays required - it's small time-series data, not raster
  tiles, and was never the expensive part.
- Set the concrete operating-cost target discussed while comparing options:
  free where possible, up to EUR 20/month acceptable if it substantially
  simplifies things. Recorded in spec section 12.
- Revisit trigger for Option B: once real usage shows people actually want
  to look at past dates on the map, not before. When revisited, the leading
  candidate is Cloudflare R2 (its zero egress fees matter for unpredictable
  tile-read traffic, unlike S3) plus a scale-to-zero container service
  (Cloud Run or Fly.io) reusing `asof.py`'s backward-search logic directly.

**Rejected:**
- Building Option B now. The storage volume itself is cheap either way
  (rough estimate: ~10-20 GB backfill since Jan 2025, growing ~5-10 GB/year,
  a few dollars a month on any provider) - the real cost of Option B is
  operational complexity (a live Python/GDAL rendering service, a cache
  strategy, an object-storage bucket), not money. Not worth taking on before
  the "crazy basic" app has validated anyone wants historical browsing.
- Recomputing historical tiles live from Copernicus/CDSE on each user
  request instead of maintaining any archive of our own. Rejected regardless
  of which storage option we pick later: CDSE's per-run product limits (see
  `docs/plan.md` Track B step 3) and unknown live-request latency/reliability
  make it unfit for synchronous user-facing map requests.

**Open / carried forward:** Full spec/plan updates for this decision (spec
sections 5.3, 12, 13, 15; plan.md pipeline and stack bullets). When Option B
is revisited, first define the exact MGRS tile set covering the Alps +
Italian Apennines footprint (needed for both the one-time backfill and the
ongoing daily job either way).

---

## 2026-08-26 - Real pipeline: browser-ready XYZ tile renderer

**Did:** Added `pipeline/tiles.py`, which colorizes a merged AS-OF composite
per the frozen visual encoding in spec sections 5.2 and 5.4 (snow-cover ramp,
freshness-attenuated alpha, fixed violet cloud, transparent water/stale/
no-data) and slices the result into standard `{z}/{x}/{y}.png` Web Mercator
tiles, skipping fully-transparent ones. Added eight focused tests, bringing
the pipeline suite to 25 tests. Ran it end to end on a real `32TPS` (Ortles-
Cevedale) 11 Feb 2026 composite reprojected through `mosaic.py`'s target-grid
path: 329 tiles written across z8/10/12, and a z8 tile visually inspected
against a dark background matches the tile footprint and snow ramp already
verified by `recon/make_overlay.py`.

**Decided:**
- One module, `render_rgba` (pure colorization) plus tile-warp/write
  functions, not a bigger renderer package - this is the entire remaining gap
  between `mosaic.py`'s composite and "browser-ready tiles" per `docs/plan.md`.
- `render_rgba` needs no per-pixel state branching beyond a cloud override:
  building a 256-entry LUT where indices 101-255 (all non-percentage GF/state
  codes) default to transparent black means water/stale/no-data fall out for
  free, since their `fsc` is already `NO_VALUE` and their `freshness` is
  already zero in `AsOfComposite`. Only cloud needs an explicit override,
  because spec 5.4 gives it a fixed alpha independent of freshness.
- Standard XYZ addressing (`{z}/{x}/{y}.png`, 256px tiles, the OSM slippy-map
  convention) via `rasterio.warp.reproject` per tile, not a single big
  pre-warped raster sliced in Python - reuses the same nearest-neighbour
  warping already validated in `mosaic.py`, and keeps memory bounded per tile
  regardless of composite extent.
- Skip fully-transparent tiles rather than writing them - a mosaic's footprint
  is a rotated MGRS-tile rectangle or a small overlap region, never the whole
  world, so most of any bounding box's tile range would otherwise be empty
  files.
- 0 as a shared nodata sentinel across all four RGBA bands in the tile warp:
  no legitimate encoded pixel is ever all-zero (colors start at 130/160/190,
  alpha at 26), so treating exact zero as "no data" on both source and
  destination is unambiguous and lets one sentinel cover every band.

**Rejected:**
- Reusing `recon/make_overlay.py`'s LUT by import - that module is scaffolding
  with a "GF-only, no freshness multiplier" placeholder ramp explicitly marked
  not authoritative; `tiles.py` rebuilds the same stops directly from the now-
  frozen spec 5.2 hex/alpha values as the source of truth instead.
- `dst_nodata=0` without also setting `src_nodata=0` on the `reproject` calls:
  the first version passed this test suite's synthetic-grid check but silently
  turned every transparent `(0,0,0,0)` pixel into `(1,1,1,1)` on a real GDAL
  warp. This is a known GDAL behaviour - a resampled value that happens to
  equal `dst_nodata` gets bumped by 1 so it isn't mistaken for the nodata flag
  - and it only shows up once source and destination grids actually go through
  GDAL's warp machinery, not in pure-Python arithmetic. Caught by an end-to-end
  run against real data, not by the unit tests alone; worth remembering that
  gap next time a rasterio warp path only gets synthetic-array coverage.
- A paletted PNG per tile (as `make_overlay.py` uses for its one image): the
  freshness multiplier means a single tile can already contain up to ~305
  distinct (color, alpha) pairs (101 percentages x up to 3 freshness bands,
  plus cloud and transparent), over a 256-color palette's capacity without
  quantization. Plain RGBA per tile avoids that complexity; tile files stay
  small regardless.

**Open / carried forward:** Wire up the daily fetch/schedule/publish job that
chains `raster_io.py` -> `asof.py` -> `mosaic.py` -> `tiles.py` end to end and
uploads the result, once the storage/hosting choice (spec section 15 item 8)
is made.

---

## 2026-08-25 - Real pipeline: MGRS overlap and UTM-seam mosaic

**Did:** Added `pipeline/mosaic.py`, which composes each MGRS tile on its native
grid, reprojects semantic fields to a common target grid with nearest-neighbour
resampling, and selects one source for every overlap pixel. Added three focused
tests, bringing the pipeline suite to 17 tests. Tested the real 32TQS/33TUM
Dolomites overlap across the UTM zone 32/33 seam using 6 and 11 February 2026
products: the 90 m Web Mercator overlap grid was 98.80% valid, 0.54% cloud,
0.23% water, and 0.42% no-data. The remaining no-data is source data, not a
seam-generated gap.

**Decided:**
- Compose each tile before reprojecting it. This retains native 60 m evidence
  and lets the frozen AS-OF rule operate where the data is actually aligned.
- In an overlap, water is terminal; otherwise choose the newest valid `AT`,
  then better quality, then lexicographically earlier MGRS tile ID. With no
  valid value, precedence is cloud, stale, then no-data. This rule is now
  frozen in spec section 9.3.
- Reproject every semantic field with nearest-neighbour only. This preserves
  distinct cloud/water/no-data categories and does not manufacture fractional
  snow values across a seam.

**Rejected:**
- Assigning every overlap to a fixed tile: simple, but can discard a newer,
  better-quality observation already available in the neighbouring tile.
- Averaging/blending overlapping values: it would hide disagreement and invent
  percentage values at both snow and categorical boundaries.
- Letting source-file traversal order choose an exact tie: outcomes must remain
  stable across machines and pipeline runs.

**Open / carried forward:** Render the merged semantic result into browser-ready
Web Mercator XYZ tiles, then add daily fetch, object storage, and publication.

---

## 2026-08-25 - Deployed to Netlify

**Did:** Connected `app/` to Netlify via its dashboard's GitHub import (base
directory `app`, build command `npm run build`, publish directory `dist`).
Set `VITE_MAPTILER_API_KEY` as a Netlify env var across all deploy contexts.
Site is live at https://spikely.netlify.app; every push to `main` now
auto-deploys with no manual step. This is the project's first deploy.

**Decided:**
- Ship now, even with a crazy-basic app, to close the deploy loop end-to-end
  and unblock inspecting the app on a real phone - more valuable at this
  stage than waiting for more features.
- Netlify over Vercel/Cloudflare Pages: for a static Vite build with no
  backend, all three are effectively equivalent (free, git-connected,
  auto-HTTPS). Netlify won on zero-preference tie-break, and it was already
  anticipated in `.gitignore` (`.netlify/`).
- Dashboard-based git integration over CLI-based deploys, since the goal is
  hands-off auto-deploy on every push, not one-off manual pushes.
- Left `VITE_MAPTILER_API_KEY` **unmarked** as a Netlify "secret value" and
  scoped to **all** deploy contexts with one shared value.

**Rejected:**
- Marking `VITE_MAPTILER_API_KEY` as a Netlify "secret value" - Vite inlines
  `VITE_*` vars into the client bundle by design, so Netlify's secret-scanning
  would fail the build on a value meant to reach the browser. The real access
  boundary for this key is MapTiler's own domain restriction, not Netlify.
- Scoping the env var to specific deploy contexts (e.g. separate keys for
  production vs. deploy previews) - unnecessary while the MapTiler key has no
  domain restriction yet; would only matter once one is added and it doesn't
  cover preview URLs.
- A committed `netlify.toml` - dashboard-configured build settings were
  simpler for a first deploy; revisit if build config needs to be versioned.

**Open / carried forward:** Set the MapTiler key's allowed-domains restriction
to `spikely.netlify.app` (and any future custom domain) now that the live
domain is known. `app/package-lock.json` is still untracked in git; committing
it would make Netlify's installs reproducible.

---

## 2026-08-25 - Real pipeline: validated GFSC raster-I/O adapter

**Did:** Added `pipeline/raster_io.py`, which discovers the three required
rasters in every GFSC product, parses tile/date/version from the official name,
and reads only one MGRS tile at a time into the AS-OF core. It rejects an
incomplete triplet, duplicate tile/date versions, multi-band data, absent CRS,
unexpected GF/GF-QA/AT dtypes or nodata sentinels, and any CRS/transform/shape
mismatch. Added five temporary-GeoTIFF tests, bringing the pipeline suite to 14
tests.

Validated the adapter on the real 6 and 11 February 2026 `32TPS` products: it
confirmed the shared EPSG:32632 1830×1830 grid, then fed the two daily arrays
to the compositor and reproduced 97.22% valid AS-OF coverage for 11 February.
It also discovered all 91 complete `32TPS` products in the full 15 January to
15 April sample window without exceptions.

**Decided:**
- Treat a product triplet as an all-or-nothing input. A failed/incomplete
download must stop the job instead of silently shrinking the AS-OF search set.
- Refuse multiple versions for a tile/date until a separate explicit version
selection policy exists. Choosing based on filesystem order would undermine the
deterministic selection guarantee.
- Validate daily grids before composition, including across product dates. The
AS-OF core is only meaningful when a pixel means the same ground location in
every source array.

**Rejected:**
- Glob only `*_GF.tif` and assume its sibling layers exist - this turns a
partial product into a later, harder-to-diagnose semantic error.
- Silently resample a mismatched daily source in the loader. Reprojection
belongs to the later render stage, not before native-grid AS-OF selection.

**Open / carried forward:** Define how overlapping MGRS tiles, particularly the
zone 32/33 seam, contribute to one rendered view. Then add Web Mercator XYZ
rendering and daily fetch/publish infrastructure.

---

## 2026-08-25 - Real pipeline started: AS-OF semantic core

**Did:** Committed and pushed the completed post-reconnaissance semantics/UI
checkpoint as `5a53bc5`. Added `pipeline/asof.py`, the first production-pipeline
slice: a vectorized, raster-I/O-independent compositor over aligned GF, GF-QA,
and AT arrays. Added nine unit tests covering minimal-quality forest data,
selection tie-breaks, the 14-day gap boundary, day-15 hiding, categorical
states, terminal water, malformed inputs, and exact freshness factors.

Ran the compositor against real `32TPS` products from 6 and 11 February 2026.
The 11 February product was about 90.5% no-data by itself; two-date AS-OF
selection produced 97.22% valid coverage with acquisition ages of 0-11 days,
0.42% water, and 2.35% remaining no-data.

**Decided:**
- Put production code in a new `pipeline/` package and keep the semantic core
  independent of GeoTIFF discovery, reprojection, XYZ writing, storage, and
  scheduling. Those concerns will wrap one tested implementation of the frozen
  rules rather than each reimplementing them.
- Represent validity separately from FSC with explicit valid/cloud/water/stale/
  no-data states. Non-valid pixels cannot accidentally enter analysis as 0%
  snow; stale pixels retain acquisition age for truthful UI reporting but not
  an FSC value.
- Reject duplicate product dates and misaligned arrays at this boundary. A
  caller must resolve product versions and grids explicitly instead of making
  results depend on input order.
- Use the standard-library `unittest` runner and the existing reconnaissance
  environment for this first slice; introduce a separate production environment
  when raster-I/O dependencies land.

**Rejected:**
- Embedding AS-OF decisions directly in a GeoTIFF/XYZ loop - that would couple
  correctness to storage and make the rules harder to test in isolation.
- Treating the sample overlay generator as the production pipeline - it lacks
  GF-QA/AT and only understands one hardcoded product/tile/UTM zone.
- Starting with scheduling or object storage before the transformation itself
  is correct and testable.

**Open / carried forward:** Add a raster-I/O adapter that discovers GF/GF-QA/AT
triplets, validates their grids/metadata, and feeds them to the compositor. Then
resolve MGRS overlap/UTM seam policy, produce XYZ output, and add scheduled
fetch/publish infrastructure. `recon/` remains until those duties are replaced.

---

## 2026-08-25 - Removed the convergence-only zoom control

**Did:** Removed the throwaway **Zoom to data** button from the snow control,
including its click handler and now-dead CSS. The control now contains only the
snow visibility toggle and current sample-product metadata. The screenshot
harness still drives the map directly and needs no change.

**Decided:** Do not replace it with another recenter/fit-bounds action. The
button existed only to reach one reconnaissance tile from the Alps-wide initial
view; carrying that scaffold into the real-coverage UI would preserve the wrong
interaction model.

**Rejected:** Keeping the button until the pipeline lands - it has completed its
milestone purpose, and leaving known throwaway UI in place makes it easier to
mistake for a product requirement later.

**Open / carried forward:** Build the real GFSC pipeline; no pipeline work was
started in this cleanup.

---

## 2026-08-25 - Snow-data semantics frozen after convergence

**Did:** Closed the five snow-data decisions that reconnaissance had deliberately
left open. Updated `docs/spec.md` sections 4.1, 5.2-5.4, 7.1, and 9.2 with
reproducible rules, removed those items from section 15's open list, and marked
the post-convergence semantics step done in `docs/plan.md`. Aligned the GF-only
reconnaissance LUT with the frozen base ramp and violet cloud color, regenerated
its one sample overlay, and reran its georeferencing check; did not start the
real pipeline.

**Decided:**
- Preserve the proven steel-blue-to-white coverage ramp: sRGB `#82A0BE` at 0%,
  `#C8DEF0` at 50%, and `#FFFFFF` at 100%, with base alpha 26/150/224 out of
  255. Freshness multiplies that alpha by 1.00 at age 0-3 days, 0.75 at 4-7,
  0.45 at 8-14, and 0 from day 15. Nearest-neighbour resampling and hillshade
  above snow are part of the rule, not renderer preferences.
- Treat `AT` acquisition time as freshness and GF-QA as a separate confidence
  signal. All tiers 0-3 remain valid and equally eligible; quality is preserved
  and reported but never used to hide or fade a percentage. Otherwise the real
  Paneveggio forest point, tier 3 on every valid day, would be unusable.
- Keep cloud (`205`), water (`210`), and no-data (`255`) semantically distinct.
  Cloud falls back to violet rather than rock-like grey when no recent value is
  available; water is a terminal transparent mask; no-data is transparent and
  never treated as 0% snow.
- For AS-OF date `D`, choose the valid candidate with the newest `AT`; ties use
  better quality then newer product date. Search backward only while source age
  is at most 14 days. This handles the observed 14-day gap and poor same-day
  coverage, while the 8-14-day alpha makes the age visible and day 15 prevents
  an old value from becoming an indefinite claim about current snow.
- Historical charts show explicit valid product-day values only. They neither
  interpolate nor carry values into cloud/no-data/missing days, including via
  the map's AS-OF fallback; gaps stay visible and labelled.

**Rejected:**
- Filtering out low/minimal GF-QA or attenuating it as though it meant age -
  this would erase forested terrain and conflates confidence with the measured
  `AT` freshness signal.
- Same-day-only or 5-7-day fallback - median valid coverage was only 25-63%, a
  tile became 90% no-data within five days, and a real gap lasted 14 days.
- Carry-forward beyond 14 days or chart interpolation - both create plausible
  snow values with no explicit supporting observation.
- Neutral grey for cloud - it was visually confusable with rock/scree on the
  MapTiler Outdoor basemap. Also retained the earlier rejection of linear
  resampling and of reducing snow opacity to recover relief.
- Extending the GF-only reconnaissance overlay to fake freshness or quality:
  it has neither `AT` nor GF-QA. It was regenerated only to sanity-check the
  frozen base ramp and categorical cloud color; the real pipeline is the right
  place to render their combined semantics. Its numerical/alignment check
  passed; an optional browser re-check could not run because no browser surface
  was available in this session, which does not block the semantic decision.

**Open / carried forward:** Build the real multi-tile GFSC pipeline from these
frozen rules; this session intentionally stopped at the semantic gate.

---

## 2026-08-25 - Multi-tool agent instructions (Claude Code + OpenAI Codex)

**Did:** Split `.claude/CLAUDE.md`'s content into a shared `docs/agent-guide.md`.
Added a root `AGENTS.md` and rewrote `.claude/CLAUDE.md` as one-line adapters
that both point to it, so Claude Code and OpenAI Codex work from identical
instructions instead of two copies that could drift.

**Decided:**
- Third neutral file (`docs/agent-guide.md`) rather than making either tool's
  file the canonical source - keeps the two adapters symmetric, so adding a
  third tool later is another one-line adapter, not a decision about which
  existing file to subordinate.
- `docs/agent-guide.md`, not repo root, for the shared file: it sits alongside
  `spec.md`/`plan.md`/`worklog.md`, the other files it already tells agents
  to read.

**Rejected:**
- `.codex/AGENTS.md`, as originally proposed - Codex (and the open agents.md
  spec more broadly: Cursor, Jules, etc.) looks for `AGENTS.md` at the repo
  root, not inside a `.codex/` folder. Placed at root instead; a file Codex
  never reads would have made this exercise pointless.

---

## 2026-08-25 - Converge: first real snow tile (Track A + B)

**Did:** Scanned all 580 downloaded GFSC products to pick the best sample date.
Built `recon/make_overlay.py`, which reprojects a GFSC `GF.tif` to EPSG:3857 and
writes a paletted PNG + JSON sidecar. Loaded it into the MapLibre map as an
`image` source (`app/src/map/snowOverlay.ts`), added a layer toggle + "Zoom to
data" control (`app/src/ui/snowControl.ts`), and Copernicus attribution. Built a
Playwright screenshot harness (`app/scripts/screenshot.mjs`) to verify the result
visually. Milestone from `docs/plan.md` "Converge: first real snow tile".

**Decided:**
- Product: `T32TPS_20260206` (Ortles-Cevedale). Not the highest-coverage date
  available overall - chosen because the date matters more than the area (see
  findings.md), and this date's ~21% snow-free valley floor doubles as a free
  alignment test against the basemap.
- One reprojected PNG + MapLibre `image` source, not an XYZ tile pipeline: an
  axis-aligned EPSG:3857 rectangle maps exactly onto the source's four-corner
  quad, so no warping pipeline is needed to answer this milestone's questions.
- `raster-resampling: nearest`, not `linear`: GF mixes 0-100 percentages with
  categorical codes (cloud/water/nodata); any averaging kernel invents values
  at the boundary between them.
- Paletted PNG instead of RGBA: GF has ~103 distinct values, so the colour LUT
  doubles as the palette (alpha via tRNS) - 772 KB vs 2.89 MB, byte-identical
  after decode.
- Verified alignment two ways: numerically (independent GeoTIFF-via-pyproj vs.
  PNG-via-sidecar sampling at 11 landmarks + 300 random points, 0 unexplained
  mismatches) and visually (Playwright screenshots at hiking zoom levels).
- Snow layer inserted above landcover/hillshade, below contours/trails/labels -
  then the basemap's existing hillshade layer moved to sit *above* the snow
  (not duplicated) so full-opacity snow doesn't erase the shaded relief.
- `initialView` in `app/src/map/config.ts` left at the Alps-wide default; a
  "Zoom to data" button reaches the one sample tile instead, since retargeting
  the whole map for one sample tile would misrepresent actual coverage.
- `recon/make_overlay.py` is explicitly scaffolding, not the data pipeline -
  marked for deletion once the real fetch/tile job exists (see docs/plan.md).
  Its output PNG is committed anyway: `recon/data/` is gitignored, so without
  the PNG in git a fresh clone has no way to reproduce or see it.

**Rejected:**
- Lowering the snow layer's max opacity to let hillshade show through - fixes
  the relief but makes snow itself harder to read (50% and 100% cover start to
  look similar). The problem was layer order, not opacity.
- Moving the snow layer *below* hillshade - fails specifically on MapTiler
  Outdoor, which draws the `parks` fill above hillshade; snow under a national
  park polygon rendered green.
- A second, duplicate hillshade layer above the snow - brings relief back but
  double-shades every non-snow pixel, making the whole basemap more contrasty
  than intended.
- Git LFS for the overlay PNG - LFS earns its cost on binaries that change
  often; this one is a single 772 KB scaffolding artifact scheduled for
  deletion, and the eventual pipeline ships tiles via object storage, not git.

**Open / carried forward:**
- Whether to commit the overlay PNG + `make_overlay.py` as a unit (decided:
  yes, see CHANGELOG).
- Three new inputs to spec.md section 15's visual-encoding decision: resampling
  choice as an honesty tradeoff, grey cloud vs. rock confusability on this
  basemap, and (now resolved) the hillshade order fix.

---

## 2026-08-25 - GFSC reconnaissance, first real downloads

**Did:** Set up `recon/.venv`, vendored the HR-WSI S3 client, and downloaded real
GFSC products for 4 sample areas (glaciated Alps, forested foothills, Apennines,
an MGRS tile-boundary point) over a 2026-01-15 to 2026-04-15 window - 580
products, ~1.6 GB total. Read the Product User Manual directly to build an
authoritative value codebook rather than guessing from pixel values. Full detail
in `recon/findings.md`; this entry is the narrative summary.

**Decided:**
- No personal Copernicus/WEkEO account needed - the HR-WSI S3 client ships a
  read-only access key; confirmed by reading the client source, not just its docs.
- pip + a plain venv instead of the client's documented conda flow - all its
  dependencies have PyPI wheels.
- Computed the actual MGRS tile-boundary point from real tile-overlap geometry
  (`MGRS_tiles.gpkg`) rather than guessing from a map; the first visual guess
  turned out to fall inside only one tile, not the boundary.

**Findings that shaped later decisions:**
- Quality tier was minimal (tier 3) on every single day at one forested test
  point - not a fluke; the PUM explains gap-filling is mainly for non-forested
  terrain. Directly informed former spec.md section 15 item 2.
- NODATA gaps up to 14 consecutive days at one pixel, longer than the PUM's
  stated 5-7 day compositing window. Directly informed former section 15 item 4.
- Confirmed `QAFLAGS` bit7 (radar/SWS source) lines up exactly with wet-snow
  pixels forced to 100% FSC - documented PUM behaviour, not a bug.

**Rejected:** A separate catalogue-only query pass before downloading - a
handful of tiles/dates is nowhere near the 500-products-per-run limit, and
downloading directly gives the catalogue metadata for free.

**Open / carried forward:** Hadn't yet reprojected or rendered anything for the
map - became the next session's "Converge: first real snow tile" milestone.
