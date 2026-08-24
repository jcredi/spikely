# Snow Map - project guide

## What this is
A free, mobile-friendly web app showing quasi-real-time Copernicus snow-cover data (GFSC) over an outdoor/topo map of the Alps + Italian Apennines, for hikers and mountaineers. Full requirements: @docs/spec.md. Current plan and status: @docs/plan.md.

## Two independent tracks
- **`app/`** - frontend map shell (MapLibre GL JS + OSM-based topo basemap). No dependency on snow data yet.
- **`recon/`** - Copernicus GFSC data reconnaissance (Python). Answers how fresh/complete GFSC actually is over our region, what the raster looks like, and what pipeline shape makes sense.

These converge at the "first real snow tile on the map" milestone - see docs/plan.md. Work on them in **separate sessions** (separate terminal windows, cd'd into the relevant folder, or separate worktrees). Don't mix both tracks' context into one conversation.

## Ground rules
- Early planning/prototyping stage. Favor small, visible, working steps over broad refactors, heavy abstraction, or building for hypothetical scale.
- No user accounts, no backend database for the MVP - see docs/spec.md section 11.
- Snow data source is GFSC (60 m, gap-filled, single value per pixel) - not raw FSCOG/FSCTOC. Don't reintroduce an on-ground/top-of-canopy toggle; see docs/spec.md section 7.2 for why.
- Copernicus data requires attribution; so does OpenStreetMap (ODbL). Don't drop attribution from any map view.
- docs/spec.md is the frozen product spec. Don't treat something as an open question if it's already answered there - check first.

## `app/` conventions
- Vite + TypeScript, no UI framework yet (deferred until panels/charts are actually built - see docs/spec.md section 15.13). Package manager: npm.
- Basemap: MapTiler "Outdoor" vector style via MapLibre GL JS. Requires `VITE_MAPTILER_API_KEY` in `app/.env` (see `app/.env.example`); get a free key at maptiler.com. OpenTopoMap (raster, no key) is the documented fallback if that becomes a blocker.
- Layout: `src/main.ts` (map instantiation), `src/map/config.ts` (style URL, initial view), `src/style.css` (full-bleed responsive layout, mobile safe-area insets).
- Dev server: `npm run dev` (from `app/`). Build: `npm run build` (outputs static `dist/`, deployable as-is).

## `recon/` conventions
- Python, using a venv at `recon/.venv`. Dependencies go in `recon/requirements.txt`.
- Findings go in `recon/findings.md` as you go - short bullet notes, not a formal write-up.
- Never commit downloaded raster samples (see .gitignore) - they're large and not ours to redistribute outside the app itself.

## Workflow
- Use plan mode for anything touching more than one file, or where the approach isn't obvious. Skip it for small, clearly-scoped fixes.
- Favor steps with a visible or checkable result: for `app/`, "does it render correctly in a browser"; for `recon/`, "does the script run and produce inspectable output."
