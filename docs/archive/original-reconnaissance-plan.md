# Snow Map MVP - Remaining Planning and Execution Plan

**Status:** Draft v1.0  
**Date:** 2026-08-24  
**Starting point:** MVP product specification agreed; no data has yet been downloaded or implementation started.

## 1. Purpose of this plan

This document defines the work to perform after freezing the MVP product specification and before/during implementation.

The central principle is to make architectural decisions from evidence rather than assumptions. In particular, the real behavior of Copernicus Fractional Snow Cover (FSC) data in mountainous terrain should be understood before choosing the storage, tiling, API, caching, and frontend architecture.

The work is organized as:

1. FSC data reconnaissance.
2. Snow-data semantic decisions.
3. Geographic stack reconnaissance and selection.
4. Data/backend architecture design.
5. UX/wireframe design.
6. Scale and cost estimation.
7. Licensing and attribution review.
8. Technical blueprint and stack selection.
9. Implementation plan in vertical milestones.

No coding should begin merely to "get started" before the key uncertainties in steps 1-4 are resolved.

---

# Phase 1 - Copernicus FSC data reconnaissance

## 2. Objective

The goal is to understand what the FSC product actually looks like and how it behaves over the Alps and Italian Apennines.

This phase should answer questions that directly affect product behavior and architecture:

- How recent are observations in practice?
- How variable is freshness across neighboring Sentinel-2/MGRS tiles?
- How frequently does a given mountain location receive a usable observation?
- How large and frequent are gaps caused by cloud cover?
- How useful are FSCOG and FSCTOC in open alpine terrain versus forested areas?
- How often do quality flags matter in terrain a mountaineer actually cares about?
- What does "latest valid observation" need to mean?
- What does the historical time series at one point look like?
- How much raw data exists for the intended geographic scope?
- What preprocessing is needed before data can be served efficiently to a browser?

This is not yet a production ingestion project. It is a bounded research exercise.

## 3. Official FSC facts to verify against real data

The current Copernicus documentation establishes several starting facts that should be treated as hypotheses/constraints and then tested empirically:

- FSC has native 20 m x 20 m pixels.
- Individual products correspond to Sentinel-2/MGRS tiles of approximately 110 km x 110 km.
- Products are near-real-time but follow Sentinel-2 acquisition/revisit opportunities rather than providing one synchronized daily observation of every pixel.
- Temporal gaps can occur because of cloud cover and unavailable/unsuitable source imagery.
- FSCTOC contains top-of-canopy fractional snow cover.
- FSCOG contains on-ground fractional snow cover corrected using tree-cover density and is the default product recommended for mapping snow cover.
- FSC layers use 0-100 for percentage, while special values distinguish cloud/cloud shadow, inland water, and no-data.
- FSCTOC-QA and FSCOG-QA provide four quality levels.
- QAFLAGS provide expert information including hillshade-related conditions, dense tree cover, cloud-recovered estimates, and tree-cover-density availability.

Primary references:

- https://land.copernicus.eu/en/products/snow/fractional-snow-cover
- https://land.copernicus.eu/en/technical-library/product-user-manual-high-resolution-snow-products-europe/@@download/file
- https://github.com/eea/clms-hrwsi-api-client-python

The reconnaissance should explicitly record any discrepancy between documentation and what is actually available through the current distribution mechanism.

## 4. Geographic sample design

Do not inspect only one favorite mountain. Use a deliberately varied sample so the application is not designed around an easy case.

A reasonable first sample is 8-10 areas containing the following terrain types:

| Sample type | Why it matters |
| --- | --- |
| Western Alps, high glaciated/open terrain | Tests snow detection where canopy is irrelevant and persistent snow/ice may exist. |
| Central Alps, steep complex relief | Tests hillshade/topographic effects. |
| Eastern Alps/Dolomites | Tests very steep rocky terrain and fragmented snow. |
| Forested Alpine foothills | Tests FSCOG vs FSCTOC and tree-cover QA. |
| A location near an MGRS tile boundary | Tests asynchronous neighboring acquisitions and mosaicking behavior. |
| Cloud-prone Alpine area | Tests prolonged missing-observation periods. |
| Northern Apennines | Tests lower elevation, transient snow, forest cover, rapid melt. |
| Central Apennines | Tests significant winter snow outside the Alps and different terrain/vegetation. |
| Low/no-snow control area | Verifies that snow-free behavior is represented cleanly. |
| Optional known snow-event case | Makes it easier to inspect accumulation/melt through time. |

Exact locations can be selected immediately before the exercise. The important point is coverage of failure modes, not geographic prestige.

For each sample, note whether it is:

- open terrain;
- forested;
- steep/shaded;
- glaciated;
- near a tile boundary;
- typically cloudy;
- seasonal/transient snow terrain.

## 5. Time windows to inspect

Use more than one temporal window.

### 5.1 Recent operational window

Inspect approximately the most recent 30-60 days available at the time of reconnaissance.

Purpose:

- understand current NRT delivery;
- measure ingestion latency;
- see tile-to-tile freshness differences;
- see actual gaps.

### 5.2 Snow-season window

Choose at least one winter/spring period with substantial snow, for example several consecutive months after 20 January 2025.

Purpose:

- inspect meaningful FSC dynamics;
- observe accumulation and melt;
- test historical continuity.

### 5.3 Melt-transition window

Inspect a period during rapid melt.

Purpose:

- see whether 20 m FSC produces useful gradients along elevation and aspect;
- test route-profile usefulness;
- understand how acquisition gaps affect rapidly changing conditions.

### 5.4 Cross-year comparison

Where data availability permits, compare the same seasonal period across two years after the accepted MVP historical cutoff.

Purpose:

- validate the proposed "this period last year" object-panel experience;
- identify any product-version or availability discontinuities.

## 6. First task: interrogate the catalogue without bulk downloading

Before retrieving raster contents, determine what products exist.

Use the official HR-WSI query mechanism/client to inspect the catalogue for the selected areas and time windows.

For every returned FSC product, capture at least:

- product identifier;
- product type/version;
- MGRS tile;
- acquisition/measurement datetime;
- publication/availability datetime if exposed;
- relevant processing/version metadata;
- file list;
- file sizes where available;
- projection/EPSG;
- geographic bounds.

### Deliverable 6A - Catalogue inventory

Produce a machine-readable table such as CSV/Parquet with one row per FSC product.

This table should make it possible to calculate update cadence and estimate total data volume without opening every raster.

## 7. Freshness and revisit analysis

For each sample location or tile, calculate:

- number of acquisitions/products per week/month;
- median time between acquisitions;
- 25th/75th/90th percentile gap;
- longest observed gap;
- fraction of calendar days with a product;
- if publication timestamps exist, acquisition-to-availability latency;
- seasonal differences where visible.

Then compare adjacent tiles.

Questions to answer:

1. Is the "latest" map normally a patchwork of different acquisition dates?
2. What is a typical age distribution across the Alps on any given AS-OF date?
3. Are differences mostly 0-2 days, or routinely much larger?
4. Are there edge cases with week-plus gaps?
5. How much worse are gaps in winter/cloudy periods?

### Deliverable 7A - Freshness report

Include:

- a small table of freshness statistics by sample area;
- a histogram/distribution of observation ages on selected AS-OF dates;
- at least one map or schematic showing acquisition-date differences across neighboring tiles;
- recommendations for candidate freshness bands, for example provisional categories such as fresh / aging / stale / unavailable.

Do **not** freeze those categories until real distributions are seen.

## 8. Download a deliberately small raster sample

Only after catalogue inspection, download enough FSC products to inspect actual pixel behavior.

For selected dates/tiles retrieve, at minimum where present:

- FSCOG;
- FSCTOC;
- FSCOG-QA;
- FSCTOC-QA;
- QAFLAGS;
- cloud layer if useful for interpretation;
- metadata needed to understand acquisition and processing.

There is no need at this stage to download the full Alps/Apennines history.

## 9. Raster structure and storage inspection

For each downloaded sample, record:

- GeoTIFF dimensions;
- CRS;
- pixel resolution;
- compression;
- uncompressed versus on-disk size;
- no-data/special-value encoding;
- internal tiling/block structure;
- whether Cloud Optimized GeoTIFF characteristics are present or could be produced efficiently;
- whether overviews are present;
- whether layers align pixel-for-pixel;
- whether tile extents overlap or merely meet;
- whether the valid S2 swath leaves large unused portions of nominal tile extent.

### Deliverable 9A - Raw-format assessment

Answer:

- Can the original GeoTIFFs be used directly for any serving workflow?
- Should they be converted to COGs?
- Would pre-rendered XYZ/WMTS raster tiles be simpler?
- Is a multidimensional array store or database justified, or unnecessary?

Do not make the final architecture choice yet; identify viable options and obvious dead ends.

## 10. Pixel-value and quality-code analysis

Quantify the proportions of pixels represented by:

- FSC 0%;
- FSC 1-99%;
- FSC 100%;
- cloud/cloud shadow;
- water;
- no-data;
- each QA quality level;
- relevant combinations of QAFLAGS.

Do this separately for contrasting terrain samples.

Questions:

- Are low-quality pixels rare enough to display with a warning, or common enough that strict masking would create holes?
- Do hillshade flags appear frequently in steep Alpine terrain?
- How common is the "estimated despite cloud" flag?
- How problematic is FSCOG quality under dense forest?
- Does strict quality filtering remove too much useful information?

### Deliverable 10A - Candidate validity policies

Define 2-3 candidate policies, for example conceptually:

- **Permissive:** accept most numerical FSC values, surface QA separately.
- **Balanced:** accept high/medium and selected low-quality cases, reject clearly problematic observations.
- **Strict:** only accept high/medium-quality observations with conservative QAFLAG masking.

Then quantify how much spatial and temporal coverage each policy would preserve.

The final MVP rule should be chosen from evidence, not intuition.

## 11. FSCOG versus FSCTOC comparison

Compare both layers in:

- open alpine terrain;
- sparse vegetation;
- dense forest;
- forest edges;
- snow-free control areas.

Measure:

- percentage of pixels where they differ;
- distribution of absolute differences;
- relationship between differences and FSCOG-QA / tree-cover-related flags;
- visual plausibility in representative map views.

Questions:

- Is FSCOG clearly the better default in forested hiking terrain?
- Are there situations where FSCOG creates visually surprising artifacts?
- How should the UI explain the toggle without overwhelming users?

### Deliverable 11A - Layer recommendation

Confirm or revise:

- default = FSCOG;
- optional toggle = FSCTOC;
- user-facing explanation;
- any warnings tied to dense forest/low-quality correction.

## 12. Point-history analysis for OSM objects

Simulate what the app would show for a peak, hut, or pass.

For a sample point, build a chronological series containing, for every relevant acquisition:

- acquisition date/time;
- FSCOG;
- FSCTOC;
- QA levels;
- relevant QAFLAGS;
- valid/invalid/cloud state.

Then test the proposed historical views:

- last 30 days;
- last 90 days;
- seasonal period;
- cross-year comparison.

Questions:

- Is the raw series understandable, or too sparse/noisy?
- Should the chart show observations as points rather than implying a continuous daily measurement?
- Should cloudy days simply be absent, explicitly marked, or represented as gaps?
- Is any interpolation justified?
- Is "last known valid FSC" useful as a separate derived line, or misleading?

Strong default principle: do not interpolate or carry forward invisibly. If an AS-OF value uses the last valid observation, expose its acquisition date and age.

### Deliverable 12A - Historical-series semantic proposal

Specify exactly what constitutes a plotted point, a gap, an AS-OF value, and a quality warning.

## 13. AS-OF mosaic experiment

Build a small offline prototype dataset - not an app - for one or more test regions and several AS-OF dates.

For each pixel and AS-OF date:

1. consider observations on or before the selected date;
2. apply each candidate validity policy;
3. select the latest valid observation;
4. store FSC value and observation age;
5. distinguish no usable observation from 0% snow.

The purpose is to understand the resulting product, not to commit to a production implementation.

Inspect how the map looks when:

- one tile is much older than its neighbor;
- clouds remove recent observations;
- observations become several days old during rapid melt;
- a user scrolls backward through dates.

### Deliverable 13A - AS-OF rules

Freeze the definitions of:

- `as_of_date`;
- `observation_date`;
- `observation_age`;
- `latest_valid_observation`;
- stale/unavailable;
- behavior at tile/product boundaries.

## 14. Freshness visualization experiment

Do not assume the initial color/opacity mapping is correct.

Create simple static mockups using real sample data for at least these alternatives:

### Option A

- color = FSC;
- opacity = freshness.

### Option B

- color/intensity = freshness;
- another visual channel or palette family = FSC.

### Option C

- color = FSC;
- freshness shown through saturation, hatching, desaturation, edge treatment, or a separate freshness overlay/control.

Evaluate against practical questions:

- Can the user immediately see where snow is?
- Can the user detect stale areas without mistaking stale snow for less snow?
- Does transparency allow the topo map to remain readable?
- Does a nearly transparent stale pixel become indistinguishable from "no snow"?
- Does the visualization remain understandable on a phone and in sunlight?

### Deliverable 14A - Visualization recommendation

Select a leading model and one fallback, with explicit trade-offs. Final visual tuning can happen during UX design.

## 15. Route-sampling reconnaissance

Although the routing API itself belongs to a later phase, FSC sampling along a route can be investigated using any representative polyline.

Test different sampling strategies against the native 20 m raster:

- fixed spacing, e.g. every 10/20/30/50 m;
- sampling raster cells intersected by the route;
- optional narrow corridor around the route;
- aggregation over short distance bins for display.

Questions:

- What spacing captures meaningful 20 m changes without oversampling?
- How sensitive are results to GPS/path geometry offsets?
- Would a small corridor make route statistics more robust or merely blur them?
- How should missing/stale pixels along a route affect summary statistics?
- What exactly should "X% of route is snow-covered" mean for fractional pixels?

Candidate definitions to compare include:

1. mean FSC along route;
2. fraction of route samples with FSC above threshold `T`;
3. distance-weighted expected snow-covered fraction using the FSC percentages themselves;
4. threshold-based snow presence plus mean FSC as a secondary metric.

### Deliverable 15A - Route snow metric proposal

Recommend:

- sampling method;
- default spacing;
- whether a corridor is used;
- main route snow headline statistic;
- how freshness/quality affects the statistic;
- what gets shown in the interactive profile.

## 16. Data-volume and retention reconnaissance

Using catalogue counts and sample file sizes, estimate for the full MVP geographic scope:

- number of relevant MGRS tiles;
- number of FSC acquisitions/products per day/week/month/year;
- raw bytes per FSC layer/product;
- raw annual storage from 20 Jan 2025 onward;
- storage if retaining only necessary layers;
- storage after COG/compression/retiling candidates;
- likely number/size of map tiles if pre-rendered;
- historical growth rate.

Also estimate the difference between storing:

- all source products;
- only FSCOG/FSCTOC + QA information;
- derived daily/AS-OF mosaics;
- pre-rendered map tiles;
- route/object query-optimized structures.

### Deliverable 16A - Capacity model

Produce a simple spreadsheet/table with low/base/high estimates for storage and processing.

This will feed directly into architecture and cost decisions.

## 17. FSC reconnaissance exit criteria

Do not move to architecture selection until we can answer all of the following with evidence:

1. What is the typical and worst-case observation age in our target regions?
2. How should a historical AS-OF map choose observations?
3. Which observations count as valid?
4. How should clouds/no-data be represented?
5. How should quality be used in display and analysis?
6. Is FSCOG still the correct default?
7. Does the object-level history series support the intended UX?
8. What route-sampling semantics appear defensible?
9. How much data do we need to store/process?
10. What serving approaches remain plausible after seeing real file structure and volume?

The expected output of Phase 1 is a short **FSC Reconnaissance Report** plus machine-readable inventories/statistics, not application code.

---

# Phase 2 - Freeze snow-data semantics

## 18. Objective

Turn empirical findings into explicit product rules.

Decisions to freeze:

- valid observation rule;
- AS-OF selection rule;
- observation age calculation;
- staleness thresholds;
- handling of cloud, water, no-data, and low-quality values;
- FSCOG/FSCTOC defaults and explanations;
- historical-chart gaps and observation markers;
- map freshness visualization;
- route snow statistic and sampling method.

### Deliverable

A short **Snow Data Semantics Specification** containing formulas/pseudocode and examples.

This document should be precise enough that two independent implementations would produce the same answers.

---

# Phase 3 - Geographic stack reconnaissance and selection

## 19. Components to evaluate

Evaluate candidate services/libraries for:

1. frontend map rendering;
2. outdoor/topographic basemap;
3. interactive OSM vector features/POIs;
4. contour lines;
5. hillshade/terrain;
6. geocoding/search;
7. hosted hiking routing;
8. elevation/DEM.

For each component compare:

- feature fit;
- mobile support;
- licensing/attribution;
- free-tier limits;
- paid pricing at plausible usage;
- API reliability;
- rate limits;
- cacheability;
- vendor lock-in;
- ease of implementation for a first-time webapp developer;
- migration/self-hosting path if the app grows.

## 20. Routing-specific evaluation

The hosted router must support a hiking/walking profile over OSM data.

Compare at least a small set of credible providers such as OpenRouteService, GraphHopper, and potentially a hosted Valhalla-based option.

Test representative routes containing:

- normal hiking trails;
- steep mountain paths;
- paths with `sac_scale` where present;
- huts/peaks/passes as endpoints;
- route segments with access restrictions;
- areas with sparse OSM coverage.

Do not select based only on the pricing page.

### Deliverable

A **Geographic Stack Decision Table** with one recommended choice and one fallback for each component.

---

# Phase 4 - Data and backend architecture design

## 21. Design the complete data flow

Define the intended production flow conceptually:

```text
Copernicus catalogue/S3
        |
        v
scheduled discovery/ingestion
        |
        v
raw or minimally retained source data
        |
        v
validation + preprocessing
        |
        +--> map-serving representation
        |
        +--> object/time-series query representation
        |
        +--> route-analysis representation
        v
API/CDN/object storage
        |
        v
web client
```

Separately:

```text
OSM search/object source ----+
                             |
hosted hiking router --------+--> route geometry --> elevation + FSC sampling --> route stats/profile
```

## 22. Architectural questions to decide

- Which data can be fully static and CDN-served?
- Do we need a traditional application server at all?
- Can browser map rendering read precomputed tiles directly from object storage/CDN?
- How are historical AS-OF views represented efficiently?
- Should "latest" be precomputed after each ingestion cycle?
- Are historical object time series precomputed or queried on demand?
- Are route FSC statistics computed client-side, server-side, or through a small serverless API?
- How is a hosted routing API key protected?
- What scheduled mechanism discovers new Copernicus products?
- How are partial/failed ingestion runs detected and retried?
- What metadata proves which source observation generated each served pixel/value?
- What is cached, and for how long?

## 23. Candidate architecture families to compare

Do not prematurely assume a heavy GIS backend. Compare at least:

### A. Mostly static/CDN architecture

Preprocess FSC into browser-friendly raster tiles/COGs and serve through object storage/CDN. Use small serverless functions only for queries that require secrets or dynamic route analysis.

### B. Lightweight geospatial API

Keep optimized rasters/object storage plus a small Python API for AS-OF lookup, object history, and route sampling.

### C. Database-heavy architecture

Use a geospatial database or multidimensional store for historical pixel/time queries and rendering.

Only choose C if reconnaissance demonstrates a real need. A sophisticated database is not automatically better for an MVP.

### Deliverable

An **Architecture Decision Record** showing the selected topology, major components, data formats, and rationale.

---

# Phase 5 - UX and interaction design

## 24. Wireframe before implementation

Create low-fidelity wireframes for desktop and mobile web.

Required screens/states:

- initial map/latest snow;
- layer control;
- AS-OF date selection;
- FSCOG/FSCTOC toggle;
- freshness legend;
- search results;
- selected peak/hut/pass panel;
- historical chart;
- route-planning mode;
- calculated route;
- linked elevation + snow profile;
- unavailable/stale/cloudy data states;
- loading/error states.

## 25. Mobile-specific validation

Confirm that the product does not depend on hover.

Test:

- tapping closely spaced POIs;
- opening/closing the lower information sheet;
- scrubbing the route profile with a finger;
- changing date without covering the entire map;
- viewing legends on small screens;
- using the app in portrait orientation.

### Deliverable

A small set of approved wireframes and an interaction-state document.

---

# Phase 6 - Scale, performance, and operating cost

## 26. Build a quantitative usage model

Estimate at least three scenarios:

- personal/experimental use;
- small public app;
- unexpectedly successful free app.

For each estimate:

- monthly active users;
- map tile requests;
- snow tile requests;
- object-history queries;
- route calculations;
- route-analysis requests;
- CDN egress;
- backend/serverless invocations;
- storage;
- scheduled preprocessing compute.

## 27. Compare a free and small-budget design

Explicitly produce:

### Near-zero-cost option

What compromises or extra engineering are required to remain on free tiers?

### Small-budget option

What becomes much simpler/reliable at approximately tens of euros per month?

Favor paying a small amount when it removes disproportionate complexity or operational fragility.

### Deliverable

A monthly cost table and recommended initial operating model.

---

# Phase 7 - Licensing, attribution, and terms review

## 28. Review every data/service dependency

Check:

- Copernicus/CLMS data terms and required attribution;
- OpenStreetMap/ODbL attribution requirements;
- chosen basemap provider terms;
- geocoder terms, including caching/storage restrictions;
- routing API terms;
- elevation/DEM license;
- contour/hillshade source license;
- restrictions on public/free apps, redistribution, or heavy tile use.

Ensure that "free API" is not confused with "allowed to proxy/cache/redistribute indefinitely."

### Deliverable

A one-page **Licensing and Attribution Checklist** plus the exact attribution text/components the app must expose.

---

# Phase 8 - Technical blueprint and stack selection

## 29. Select the concrete stack

Only now choose:

- frontend framework;
- map rendering library;
- charting library;
- backend/API framework if needed;
- data-processing language/tools;
- object storage;
- database if needed;
- scheduler/cron mechanism;
- CDN;
- hosting/deployment service;
- CI/CD approach;
- monitoring/logging.

Given the developer profile for this project, selection criteria should prioritize:

1. few moving pieces;
2. strong documentation and community support;
3. easy local development;
4. easy deployment;
5. low operating burden;
6. easy debugging;
7. acceptable cost;
8. a credible path toward a future Android application/API reuse.

Avoid complexity whose only benefit is hypothetical future scale.

### Deliverable

A **Technical Blueprint** with:

- architecture diagram;
- component list;
- repository structure;
- environments;
- key interfaces/APIs;
- local-development workflow;
- deployment workflow;
- data-refresh workflow;
- key operational risks.

---

# Phase 9 - Implementation planning

## 30. Build in vertical slices

Implementation should produce something visible/testable at the end of each milestone rather than completing all backend work before the UI.

Recommended sequence:

### Milestone 1 - Map shell

- responsive web shell;
- outdoor/topographic map;
- pan/zoom;
- basic controls.

**Exit:** usable topo map on desktop and phone.

### Milestone 2 - One real FSC sample

- render one representative real FSC dataset over the map;
- working legend;
- verify geospatial alignment.

**Exit:** real 20 m snow data visible in-browser in one area.

### Milestone 3 - Latest regional snow

- production-like ingestion for supported region;
- latest-valid/as-of-current representation;
- freshness visualization;
- quality/no-data behavior.

**Exit:** browse the Alps/Apennines with current snow information.

### Milestone 4 - Historical AS-OF map

- date selector;
- historical observation selection;
- age relative to selected date.

**Exit:** move backward through time and obtain reproducible historical maps.

### Milestone 5 - OSM search and selectable objects

- search by name/coordinates;
- interactive mountain POIs;
- object details.

**Exit:** reliably select a peak/hut/pass and identify its FSC value/observation.

### Milestone 6 - Object snow history

- time-series endpoint/data structure;
- historical chart;
- time range controls;
- FSCOG/FSCTOC toggle;
- quality/freshness indications.

**Exit:** selected objects have useful historical FSC analysis.

### Milestone 7 - A-to-B hiking route

- hosted routing API integration;
- start/destination selection;
- route geometry;
- distance/elevation basics.

**Exit:** calculate a credible hiking route between two supported places.

### Milestone 8 - Route snow analysis

- sample FSC along route;
- compute headline statistics;
- display elevation + snow profile;
- color/annotate route by snow.

**Exit:** user can understand where snow occurs along the planned hike.

### Milestone 9 - Linked profile/map interaction

- desktop pointer scrubbing;
- mobile touch scrubbing;
- synchronized marker on map;
- local elevation/FSC/freshness readout.

**Exit:** core route-analysis interaction is polished.

### Milestone 10 - Public MVP hardening

- loading/error states;
- caching/performance;
- mobile polish;
- attribution;
- disclaimers;
- monitoring;
- rate-limit protection;
- deployment documentation.

**Exit:** safe to publish as a free public MVP.

---

# Phase 10 - Post-MVP candidates, explicitly deferred

Do not allow these to delay the MVP unless new evidence changes priorities:

- GPX/KML upload;
- multi-waypoint routes;
- circular-route planning;
- user accounts;
- saved routes/favorites;
- route sharing;
- weather layers;
- avalanche information;
- snow-depth estimation;
- native Android application;
- live GPS navigation;
- offline maps/snow data;
- notifications/alerts;
- automated route-condition scoring.

Some of these may later become very valuable, especially in a native Android app, but they should not distort the first architecture unless they are cheap to keep possible.

---

# 31. Immediate next action

The immediate next substantive task is **Phase 1: FSC data reconnaissance**.

The recommended first session is deliberately narrow:

1. choose the 8-10 representative sample areas;
2. query the FSC catalogue for those areas without bulk downloading;
3. build the product/acquisition inventory;
4. quantify freshness/revisit behavior;
5. only then download a small set of rasters for quality/value inspection.

The first decision gate should therefore happen **before** any webapp coding and after we have a real answer to:

> How does Copernicus FSC actually behave, spatially and temporally, over the mountains we intend to serve?
