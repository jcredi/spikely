# Spikely MVP Product Specification

**Status:** Draft v1.1 - product scope frozen for data reconnaissance  
**Date:** 2026-08-25  
**Product stage:** Planning only

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

GFSC is a daily, spatially- and temporally-complete composite built by Copernicus from FSC (Sentinel-2 optical), WDS/SWS (Sentinel-1 radar), and DEM inputs. It reports a single fractional snow-cover percentage per pixel (0-100%), already on-ground-corrected - there is no separate top-of-canopy variant to toggle. Compared to raw FSC, GFSC trades spatial resolution (60 m vs. 20 m native) and some per-observation precision for near-complete daily coverage, which removes most of the cloud/revisit gap-handling complexity from the MVP.

Each pixel carries a quality tier (0 = high, 1 = medium, 2 = low, 3 = minimal) plus explicit codes for cloud/cloud-shadow and no-data. This quality tier is the primary freshness/confidence signal for GFSC - it is a coarser signal than an explicit "observation age in days," since GFSC's own gap-filling can draw on source data up to about a week old. The interface should treat the quality tier as the user-facing freshness indicator (see section 5.2, section 9.2).

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

The current leading visual model is:

- **color = snow-cover percentage**;
- **opacity = observation freshness**.

This is provisional. During design/data reconnaissance, alternatives should be compared, including reversing or otherwise separating these visual channels.

The user must be able to toggle the snow overlay on/off.

The map renderer may display progressively coarser representations at lower zoom levels for performance. However, map rendering resolution and analytical resolution must remain conceptually separate.

### 5.3 Latest and historical AS-OF dates

The user must be able to view:

- the latest available snow conditions;
- snow conditions **as of a selected historical date**.

A selected date is an **AS-OF date**, not a requirement that every pixel have an observation acquired exactly on that date.

For a selected AS-OF date `D`, each pixel should use the latest valid observation available on or before `D`, subject to quality and staleness rules that will be defined after data reconnaissance.

Example:

If the user selects 15 March and a pixel has valid observations on 11 March and 17 March, the app should use the 11 March observation.

Observation age/freshness should be calculated relative to the selected AS-OF date, not necessarily relative to today's date.

### 5.4 Clouds, missing values, water, and quality

The application must not confuse unavailable observations with 0% snow.

GFSC distinguishes ordinary 0-100% values from an explicit cloud/cloud-shadow code and no-data, and carries a four-level quality tier (high/medium/low/minimal) reflecting how much spatial/temporal gap-filling went into a given pixel. Even a gap-filled, spatially-complete product can still have genuine no-data (e.g. persistent cloud with no usable source data at all).

The exact visual and analytical treatment of these states will be defined after empirical inspection of real GFSC products.

At minimum, the final behavior must distinguish:

- valid snow-free pixels;
- valid partially/fully snow-covered pixels;
- unavailable or invalid observations;
- cloud/cloud-shadow situations where no valid value is available;
- water/no-data;
- low/minimal-quality (heavily gap-filled) observations.

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

The behavior of missing observations, interpolation, carry-forward values, and quality filtering will be defined after FSC reconnaissance.

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

The precise definition of a "valid" observation is intentionally not frozen yet.

It will depend on empirical findings regarding:

- GFSC quality tier (high/medium/low/minimal);
- cloud/cloud-shadow and no-data codes;
- age of the GFSC product date relative to the AS-OF date;
- residual gaps even after gap-filling (e.g. persistent cloud with no usable source data).

The MVP specification requires an explicit, reproducible rule to be defined before implementation.

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

The following are intentionally left open until data and technology reconnaissance is complete:

1. Exact snow/freshness visual encoding.
2. Exact treatment of GFSC quality tiers (high/medium/low/minimal) and residual no-data/cloud codes.
3. Staleness thresholds and when old data should be hidden or strongly de-emphasized.
4. Treatment of prolonged cloud gaps.
5. Whether any temporal interpolation/carry-forward should occur in historical charts beyond explicit AS-OF behavior.
6. Exact route sampling method and sampling spacing.
7. Exact definition of route "snow-covered percentage."
8. Which OSM object classes are interactive by default at each zoom level.
9. Basemap/vector/terrain provider.
10. Geocoding/search provider.
11. Hiking routing provider.
12. Elevation/DEM source.
13. Frontend, backend, storage, tiling, and deployment architecture.
14. Operating-cost target after scale estimates.
15. Whether raw FSCOG/FSCTOC (20 m) should be added later as an optional higher-resolution layer for terrain where 60 m GFSC proves too coarse.

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
