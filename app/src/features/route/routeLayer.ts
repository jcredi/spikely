/**
 * Everything the A-to-B route draws on the map (spec section 8.3): the route
 * geometry itself, the two endpoints, and the cursor dot that spec section 8.5
 * requires to follow a finger moving along the profile.
 *
 * Three separate sources rather than one, because they change on completely
 * different cadences: the endpoints change when the user picks them (and exist
 * before any route does - picking a start with no destination yet must still be
 * visible), the line changes once per routing request, and the cursor moves on
 * every pointer move. Sharing one source would mean re-serialising the whole
 * polyline on each `pointermove`.
 *
 * **No HTML markers, deliberately.** `maplibregl.Marker` with a custom element
 * would be the easy way to draw a labelled "A" and "B" pin, and it is not used
 * here: `docs/agent-guide.md` pins `maplibre-gl` at 4.7.1 with a live critical
 * advisory, and the reason that advisory is unreachable in this app is
 * precisely that it has "no popups, no HTML markers, and a literal attribution
 * string". Adding HTML markers for a convenience would invalidate that written
 * analysis. The endpoints are therefore circle layers, distinguished by colour
 * and echoed by matching swatches in the route panel.
 *
 * Layer order: these are added with a plain `addLayer` and so sit on top of
 * everything, including the snow raster - which `features/snow/overlay.ts`
 * deliberately inserts *below* the basemap's contour and water layers. That
 * also means a date change, which tears the raster down and builds a new one,
 * never disturbs the route.
 */
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";

const LINE_SOURCE_ID = "route-line";
const LINE_CASING_LAYER_ID = "route-line-casing";
const LINE_LAYER_ID = "route-line";
const ENDPOINT_SOURCE_ID = "route-endpoints";
const ENDPOINT_LAYER_ID = "route-endpoints";
const CURSOR_SOURCE_ID = "route-cursor";
const CURSOR_LAYER_ID = "route-cursor";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

/** Start and destination, echoed by `.route-panel__swatch` in `style.css`. */
export const START_COLOR = "#16a34a";
export const DESTINATION_COLOR = "#b91c1c";

export type RoutePoint = { longitude: number; latitude: number };

export class RouteLayer {
  constructor(private readonly map: MapLibreMap) {
    map.addSource(LINE_SOURCE_ID, { type: "geojson", data: EMPTY });
    map.addSource(ENDPOINT_SOURCE_ID, { type: "geojson", data: EMPTY });
    map.addSource(CURSOR_SOURCE_ID, { type: "geojson", data: EMPTY });

    // A white casing under a dark line: the route has to stay readable over
    // both a pale snow raster and dark forest shading, and a single-colour
    // line disappears into one or the other.
    map.addLayer({
      id: LINE_CASING_LAYER_ID,
      type: "line",
      source: LINE_SOURCE_ID,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#ffffff", "line-width": 7, "line-opacity": 0.9 },
    });
    map.addLayer({
      id: LINE_LAYER_ID,
      type: "line",
      source: LINE_SOURCE_ID,
      layout: { "line-cap": "round", "line-join": "round" },
      // Solid for now. Spec section 8.4's "route line that can visually encode
      // snow coverage along its length" needs a per-sample FSC value, which
      // needs the route sampling decision (spec section 15 items 1-2) and a
      // data source the frontend does not yet have - see docs/plan.md.
      paint: { "line-color": "#1f2937", "line-width": 3 },
    });

    map.addLayer({
      id: ENDPOINT_LAYER_ID,
      type: "circle",
      source: ENDPOINT_SOURCE_ID,
      paint: {
        "circle-radius": 7,
        "circle-color": ["get", "color"],
        "circle-stroke-width": 2.5,
        "circle-stroke-color": "#ffffff",
      },
    });

    map.addLayer({
      id: CURSOR_LAYER_ID,
      type: "circle",
      source: CURSOR_SOURCE_ID,
      paint: {
        "circle-radius": 6,
        "circle-color": "#ffffff",
        "circle-stroke-width": 3,
        "circle-stroke-color": "#1f2937",
      },
    });
  }

  /** GeoJSON positions, `[longitude, latitude]`, straight from the provider. */
  setRoute(coordinates: readonly [number, number][]): void {
    if (coordinates.length < 2) {
      this.clearRoute();
      return;
    }
    this.source(LINE_SOURCE_ID).setData({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          // Copied rather than cast: the source array is `readonly` here on
          // purpose, and MapLibre takes ownership of whatever it is given.
          geometry: { type: "LineString", coordinates: coordinates.map(([lon, lat]) => [lon, lat]) },
          properties: {},
        },
      ],
    });
  }

  clearRoute(): void {
    this.source(LINE_SOURCE_ID).setData(EMPTY);
  }

  /** Either endpoint may be null - a chosen start with no destination yet is a real state. */
  setEndpoints(start: RoutePoint | null, destination: RoutePoint | null): void {
    const features: GeoJSON.Feature[] = [];
    if (start) features.push(endpointFeature(start, START_COLOR, "start"));
    if (destination) features.push(endpointFeature(destination, DESTINATION_COLOR, "destination"));
    this.source(ENDPOINT_SOURCE_ID).setData({ type: "FeatureCollection", features });
  }

  /** The dot that tracks a finger on the profile (spec section 8.5); null hides it. */
  setCursor(point: RoutePoint | null): void {
    if (!point) {
      this.source(CURSOR_SOURCE_ID).setData(EMPTY);
      return;
    }
    this.source(CURSOR_SOURCE_ID).setData({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [point.longitude, point.latitude] },
          properties: {},
        },
      ],
    });
  }

  clear(): void {
    this.clearRoute();
    this.setEndpoints(null, null);
    this.setCursor(null);
  }

  private source(id: string): GeoJSONSource {
    return this.map.getSource(id) as GeoJSONSource;
  }
}

function endpointFeature(point: RoutePoint, color: string, role: string): GeoJSON.Feature {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [point.longitude, point.latitude] },
    properties: { color, role },
  };
}
