# Spikely MVP Product Specification

**Status:** Draft v1.2 - snow-data semantics frozen after reconnaissance
**Date:** 2026-08-25  
**Product stage:** Planning only

**Amendment (v1.2):** Froze the MVP snow-data semantics after empirical GFSC reconnaissance: `AT`-based freshness, all-tier quality handling, exact visual/category encoding, a 14-day AS-OF ceiling, and no app-created chart interpolation or carry-forward. See sections 5.2-5.4, 7.1, and 9.2.

**Amendment (v1.1):** Switched primary snow data source from raw FSCOG/FSCTOC (20 m) to GFSC, the Copernicus gap-filled composite (60 m). Rationale: GFSC trades spatial resolution and some observation-level precision for near-complete daily spatial/temporal coverage, which meaningfully simplifies the data pipeline and AS-OF logic for the MVP. This is a deliberate, reversible choice - raw FSCOG/FSCTOC remain available as a future upgrade path if 60 m proves too coarse for specific terrain (narrow ridges, passes) or the GFSC quality tier proves too coarse a freshness signal. See section 4.1, section 7.2, and section 15.

## 1. Product summary

The product is a free, mobile-friendly web application for hikers and mountaineers that combines an outdoor/topographic map with a quasi-real-time, near-complete Copernicus snow-cover layer (GFSC).

Its main purpose is to answer practical questions such as:

- How much of this mountain area is currently snow-covered?
- How recent is the satellite observation I am looking at?
- How has snow cover at this peak, hut, pass, or other mapped place changed over time?
- If I hike from point A to point B, where along the route am I likely to encounter snow?

The MVP is a planning and situational-awareness tool. It is not a snow-depth product, an avalanche forecasting product, or a turn-by-turn navigation system.

## 2. Initial target users

Primary users:

- hikers;
- mountaineers;
- alpinists;
- other outdoor users planning mountain travel.

The first release should prioritize clarity and usefulness for people deciding whether and where they are likely to encounter snow on a mountain route.

## 3. Initial geographic scope

The MVP should cover:

- the Alps;
- the Italian Apennines.

The architecture should not unnecessarily prevent later expansion to the rest of Europe, but Europe-wide support is not an MVP requirement.

## 4. Core data sources

### 4.1 Snow data

Primary snow product:

**Copernicus Land Monitoring Service - Gap-filled Fractional Snow Cover (GFSC), 60 m**

GFSC is a daily gap-filled composite built by Copernicus from FSC (Sentinel-2 optical), WDS/SWS (Sentinel-1 radar), and DEM inputs. It reports a single fractional snow-cover percentage per pixel (0-100%), already on-ground-corrected - there is no separate top-of-canopy variant to toggle. Compared to raw FSC, GFSC trades spatial resolution (60 m vs. 20 m native) and some per-observation precision for broader daily coverage. Real samples still contained large residual gaps, so GFSC simplifies but does not remove cloud/revisit gap handling from the MVP.

Each pixel carries a quality tier (0 = high, 1 = medium, 2 = low, 3 = minimal), an `AT` timestamp for the source acquisition actually used, plus explicit codes for cloud/cloud-shadow, inland water, and no-data. `AT`, measured relative to the selected AS-OF date, is the freshness signal. Quality is a separate confidence/gap-filling signal and must not be used as a proxy for age (see sections 5.2, 5.4, and 9.2).

For MVP purposes, historical support only needs to cover data from **20 January 2025 onward**.

Reference sources:

- Product page: https://land.copernicus.eu/en/products/snow/high-resolution-gap-filled-fractional-snow-cover
- Product User Manual: https://land.copernicus.eu/en/technical-library/product-user-manual-high-resolution-snow-products-europe/@@download/file
- HR-WSI Python/S3 client: https://github.com/eea/clms-hrwsi-api-client-python

### 4.2 Map and geographic objects

OpenStreetMap is the primary source for geographic and outdoor features.

The map should support mountaineering-relevant objects such as:

- peaks;
- huts/refuges;
- passes/saddles;
- shelters;
- trails and paths;
- roads and access points;
- parking;
- settlements and named places;
- other useful OSM objects exposed by the chosen map/search stack.

The exact basemap, tile provider, vector source, terrain source, geocoder, and elevation source are technical choices to be made later.

## 5. Core user experience

### 5.1 Main map

On opening the app, the user sees an outdoor/topographic map centered on the supported mountain region or on a sensible default view.

The base map should eventually include, directly or through combined data sources:

- hiking paths/trails;
- peaks and named mountain features;
- mountain huts and shelters;
- passes;
- contour lines;
- hillshade/terrain relief;
- rocky terrain/glaciers where available;
- access roads, parking, settlements, and labels.

A snow-cover layer is displayed over the topographic map.

### 5.2 Snow-cover visualization

Each GFSC pixel represents approximately 60 m x 60 m at native resolution.

The map must visually communicate at least two quantities:

1. fractional snow cover percentage;
2. freshness/age of the observation used for that pixel.

For a valid GFSC percentage `s` from 0 through 100, the MVP rendering is fixed as follows:

- **color = snow-cover percentage:** piecewise-linear interpolation in sRGB from `#82A0BE` at 0%, through `#C8DEF0` at 50%, to `#FFFFFF` at 100%, rounding each channel to the nearest 8-bit integer;
- **base alpha = snow-cover legibility:** the same interpolation over alpha values `26`, `150`, and `224` out of 255 at 0%, 50%, and 100%; this preserves a subtle tint for measured 0% snow while letting larger snow fractions read strongly;
- **freshness = an alpha multiplier:** `1.00` for an observation age of 0-3 calendar days, `0.75` for 4-7 days, `0.45` for 8-14 days, and `0` from day 15 onward. Final alpha is the rounded product of base alpha and this multiplier.

Age is defined in section 9.2. Quality tier does not change color or opacity; its separate treatment is in section 5.4. Cloud, water, and no-data use categorical handling rather than this ramp.

Raster reprojection and map rendering must use nearest-neighbour resampling. GFSC mixes percentage values with categorical codes, so linear resampling would invent sub-60 m detail and plausible-looking percentages at category boundaries. The basemap's existing hillshade must remain above the snow layer; terrain relief must not be recovered by weakening the snow encoding.

The user must be able to toggle the snow overlay on/off.

The map renderer may display progressively coarser representations at lower zoom levels for performance. However, map rendering resolution and analytical resolution must remain conceptually separate.

### 5.3 Latest and historical AS-OF dates

The user must be able to view:

- the latest available snow conditions;
- snow conditions **as of a selected historical date**.

A selected date is an **AS-OF date**, not a requirement that every pixel have an observation acquired exactly on that date.

For a selected AS-OF date `D`, each pixel uses the latest valid observation available on or before `D` under the deterministic selection and staleness rule in section 9.2.

Example:

If the user selects 15 March and a pixel has valid observations on 11 March and 17 March, the app should use the 11 March observation.

Observation age/freshness should be calculated relative to the selected AS-OF date, not necessarily relative to today's date.

### 5.4 Clouds, missing values, water, and quality

The application must not confuse unavailable observations with 0% snow.

GFSC distinguishes ordinary 0-100% values from an explicit cloud/cloud-shadow code and no-data, and carries a four-level quality tier (high/medium/low/minimal) reflecting how much spatial/temporal gap-filling went into a given pixel. Even a gap-filled, spatially-complete product can still have genuine no-data (e.g. persistent cloud with no usable source data at all).

The MVP treatment is:

- GF values 0-100 with a quality tier 0-3 and usable `AT` are valid. High, medium, low, and minimal tiers are all retained for map rendering and analysis; tier alone never hides or attenuates a value. The tier must be preserved and displayed by name in point/history details and included in route-quality summaries. This is necessary because a real forested sample was tier 3 on every valid day.
- QA flags are retained as metadata but do not exclude a valid percentage in the MVP.
- Cloud/cloud-shadow (`205`) is not a snow value. If AS-OF fallback finds no usable earlier value, render it as violet `#A855F7` at alpha `0.45` and label it **Cloud**. Neutral grey is forbidden because it was confusable with rock/scree on the selected basemap.
- Inland water (`210`) is a terminal mask, not 0% snow: do not search earlier products for a snow value, render the snow layer transparent, and report **Water** in details and analysis.
- No-data (`255`), a missing product, an unusable `AT`, or inconsistent GF/GF-QA category codes is unavailable, not 0% snow: render the snow layer transparent and report **No data**. A valid 0% pixel remains distinguishable by the ramp's blue tint.
- A structurally valid percentage whose newest usable `AT` is more than 14 days old is hidden and reported as **Stale - last observation N days old**, not collapsed into cloud, no-data, or 0% snow.

Cloud and no-data remain separate states throughout storage, APIs, charts, and UI even though both can trigger AS-OF fallback. They were observed as distinct multi-day runs in real data and must not be collapsed into one generic missing code.

## 6. Place search and selectable OSM objects

### 6.1 Search

The user can search for a place by:

- name;
- coordinates.

Search should support ordinary locations and mountain-relevant named OSM objects, subject to the capabilities of the selected geocoder/search stack.

Examples include peaks, huts, passes, villages, parking areas, and other named features.

### 6.2 Selectable objects

Mountaineering-relevant OSM objects shown on the map should be interactive map entities, not merely labels baked into a raster image.

When the user selects an eligible OSM object, an information panel opens below or adjacent to the map depending on screen size.

The detailed snow-history panel applies to OSM objects only.

Clicking an arbitrary raster pixel does **not** need to open a historical snow panel in the MVP.

## 7. OSM object information and snow history panel

For a selected OSM object, the panel should display relevant object metadata where available, for example:

- name;
- object type;
- elevation;
- coordinates;
- relevant OSM attributes.

It should also display current/as-of snow information derived at the object's location, including at minimum:

- GFSC percentage;
- GFSC product date (the daily composite date, not necessarily the underlying satellite acquisition date);
- age of that product date relative to the map AS-OF date;
- quality tier for that pixel (high/medium/low/minimal), as the primary indicator of how much gap-filling was involved.

### 7.1 Historical chart

The panel should include an interactive snow-cover history chart for the selected object.

The user should be able to choose periods such as:

- last 30 days;
- last 90 days;
- last year;
- custom period;
- comparable period in a previous year, where data availability permits.

Exact presets can be refined later.

The chart must handle missing/cloudy observations honestly rather than silently converting them to snow-free conditions.

Historical charts plot one discrete mark for a product date only when that product's own pixel has GF 0-100, GF-QA 0-3, and a usable `AT` no more than 14 days before that product date. The mark uses that product's explicit GF value. Charts do not interpolate, smooth, or carry the last value into a cloud/no-data/missing date, and they do not populate chart gaps from the map's AS-OF fallback. A gap remains a gap and is labelled **Cloud**, **No data**, or **Stale** where applicable. Every mark's details expose product date, source `AT`, observation age, and quality tier. This rule does not undo gap-filling already performed inside an explicit GFSC product; it only forbids the app from inventing additional values.

### 7.2 FSCOG / FSCTOC toggle - removed for MVP

GFSC does not provide a separate top-of-canopy layer, so this toggle no longer applies. GFSC is effectively on-ground-corrected already.

If 60 m resolution or GFSC's smoothing proves too coarse for specific terrain during implementation, raw FSCOG/FSCTOC remain available as a future higher-resolution layer (see section 15). Any such addition should still avoid implying that either value is snow depth.

## 8. A-to-B hiking route planner

### 8.1 Scope

The MVP includes simple walking/hiking routing from point A to point B.

The route should be produced through a hosted OSM-based routing API. The app should not implement or self-host a routing engine for the initial MVP unless later investigation reveals a compelling reason.

Candidate providers will be evaluated later.

The route planner is intentionally limited to:

- one origin;
- one destination;
- walking/hiking mode.

### 8.2 Route endpoints

The preferred interaction is selection of OSM objects or searched places as origin and destination.

The detailed UX for choosing endpoints will be designed later.

### 8.3 Route outputs

Once a route is calculated, the application should show basic route information such as:

- distance;
- elevation gain/loss where available or derivable;
- route geometry on the map.

The route must then be analyzed against native-resolution or appropriately sampled FSC and elevation data.

Analytical results must not change simply because the user changes map zoom level.

### 8.4 Snow coverage along the route

The route view should include:

- snow coverage profile along distance;
- elevation profile along the same distance axis;
- route-level summary snow statistics;
- a route line that can visually encode snow coverage along its length.

A useful MVP headline statistic is the proportion of the route currently/as-of-date affected by snow, with the exact definition to be decided after data reconnaissance.

Potential additional statistics, if straightforward and defensible, include:

- distance with FSC above a selected threshold;
- longest continuous snow-covered section;
- snow coverage by elevation band;
- freshness/quality summary for the observations intersecting the route.

These are optional unless promoted into scope later.

### 8.5 Linked map/profile interaction

The elevation and snow profile must be interactive.

When the user moves a mouse pointer or finger along the profile:

- the corresponding route location is identified;
- a marker/dot moves to the corresponding point on the map;
- the profile can show local elevation, FSC, and observation freshness/quality where practical.

This interaction is a core MVP requirement.

### 8.6 Routing disclaimer

Automatically generated hiking routes depend on OSM completeness and the routing provider's interpretation of paths and trail difficulty.

The app should make clear that a suggested route must be independently verified and is not a guarantee of safety, accessibility, or suitability.

The MVP is a route-planning aid, not a safety-critical navigator.

## 9. Snow data semantics

### 9.1 What GFSC means

GFSC is fractional surface snow coverage (on-ground corrected), expressed as a percentage of the pixel area.

The app must not present GFSC as:

- snow depth;
- snow water equivalent;
- snow hardness;
- avalanche risk;
- a determination that crampons, skis, snowshoes, or other equipment are required.

A value of 100% means that the pixel is assessed as completely snow-covered according to the product, not that snow is deep.

### 9.2 Latest valid observation

All dates and acquisition timestamps are compared in UTC. For an AS-OF calendar date `D`, observation age is `D - UTC-date(AT)` in whole calendar days, with a minimum of zero.

For each pixel:

1. If the newest available product on or before `D` identifies the pixel as inland water (`210`), return **Water** immediately.
2. Consider products with product date on or before `D`. A candidate is valid only when GF is 0-100, GF-QA is 0-3, `AT` is usable and no later than the end of `D`, and its observation age is at most 14 days. Quality tiers 0-3 are equally eligible.
3. Select the candidate with the greatest `AT`. Break an `AT` tie by better quality tier (lower numeric GF-QA), then by the later product date. This makes the result independent of file or query ordering.
4. Render the selected value with the age multiplier from section 5.2: normal at 0-3 days, aging at 4-7 days, and strongly de-emphasized/stale at 8-14 days.
5. If no candidate exists, return no snow value. Preserve the newest product's reason as **Cloud** for `205` or **No data** for `255`; no product or malformed/inconsistent metadata is **No data**. If valid-form percentages exist but their usable acquisitions are all older than 14 days, return **Stale** with the most recent acquisition age. Do not search or carry forward beyond 14 days.

The backward search is required because median same-day valid coverage was only 25-63% across the reconnaissance samples and one tile changed from 97% valid to 90% no-data in five days. The 14-day ceiling keeps the complete observed 14-day forest gap usable, but makes anything older genuinely unavailable instead of presenting an indefinite carry-forward as current evidence.

## 10. Responsive/mobile web behavior

The first product is an open web application but must be designed mobile-first enough to work comfortably on a phone browser.

Requirements include:

- touch-friendly map controls;
- touch-friendly date and layer controls;
- selectable OSM objects without relying on mouse hover;
- route-profile scrubbing by touch;
- information panels that work on narrow screens;
- no essential interaction that requires a desktop mouse.

Desktop may offer hover as an additional convenience.

## 11. State, accounts, and privacy

The MVP is completely stateless from the user's perspective.

It should require:

- no user account;
- no login;
- no saved routes;
- no saved favorite places;
- no personal profile.

Backend caching, shared precomputed data, and anonymous operational telemetry are separate technical considerations and do not constitute user-specific persisted state.

## 12. Operating model

The app is free to users.

A near-zero-cost deployment should be evaluated, but a modest operating budget is acceptable if it substantially reduces complexity, improves reliability, or avoids building/operating unnecessary infrastructure.

The first web deployment may use Netlify or an equivalent service for the frontend, but hosting choices are not yet fixed.

## 13. MVP feature scope

| Capability | MVP status |
| --- | --- |
| Outdoor/topographic map | Required |
| GFSC snow overlay | Required |
| Latest snow conditions | Required |
| Historical AS-OF map date | Required |
| Observation freshness visualization | Required |
| Quality/missing-data handling | Required |
| Search by name | Required |
| Search by coordinates | Required |
| Interactive mountaineering-relevant OSM objects | Required |
| OSM-object historical snow chart | Required |
| A-to-B hiking route planning | Required |
| Route elevation + snow profile | Required |
| Linked profile/map cursor | Required |
| Basic route snow summary | Required |
| User accounts | Out of scope |
| Saved routes/favorites | Out of scope |
| GPX/KML upload | Out of scope |
| Multi-waypoint routes | Out of scope |
| Circular route generation | Out of scope |
| Turn-by-turn/live navigation | Out of scope |
| Offline maps/snow | Out of scope |
| FSCOG/FSCTOC on-ground/canopy toggle | Out of scope (GFSC has no canopy variant) |
| Android native app | Future |
| Notifications | Future |

## 14. Explicit non-goals for v1

The MVP should not attempt to become:

- a full GIS application;
- an avalanche bulletin or hazard model;
- a snow-depth estimator;
- a weather forecast app;
- a live GPS navigation app;
- an offline field-navigation tool;
- a social/community platform;
- an account-based route library.

These exclusions are important to keep the first release manageable.

## 15. Important open decisions

Snow/freshness encoding, quality and categorical-code handling, staleness, prolonged gaps, and historical-chart carry-forward are now frozen in sections 5.2-5.4, 7.1, and 9.2. The remaining open decisions are:

1. Exact route sampling method and sampling spacing.
2. Exact definition of route "snow-covered percentage."
3. Which OSM object classes are interactive by default at each zoom level.
4. Basemap/vector/terrain provider.
5. Geocoding/search provider.
6. Hiking routing provider.
7. Elevation/DEM source.
8. Frontend, backend, storage, tiling, and deployment architecture.
9. Operating-cost target after scale estimates.
10. Whether raw FSCOG/FSCTOC (20 m) should be added later as an optional higher-resolution layer for terrain where 60 m GFSC proves too coarse.

## 16. MVP success criteria

The MVP is successful if a hiker or mountaineer can, on desktop or mobile web:

1. open the app and understand where snow is currently present in a mountain area;
2. distinguish fresh observations from stale or unavailable observations;
3. move the map to a named mountain location quickly;
4. inspect historical FSC at a mapped peak, hut, pass, or similar OSM object;
5. change the map to an earlier AS-OF date and understand what snow information was available then;
6. plan an A-to-B hiking route;
7. see where snow occurs along that route in combination with elevation;
8. interactively link the route profile to the map;
9. understand that the product represents snow cover, not snow depth or route safety.

## 17. Product principle

The app should make sophisticated geospatial data useful without requiring the user to understand satellite products, MGRS tiles, GeoTIFFs, quality bitmasks, or GIS software.

The interface should expose uncertainty and freshness honestly while keeping the default experience simple enough to answer one practical question quickly:

**"Where am I likely to encounter snow on this mountain or route, based on the most recent usable satellite observations?"**
