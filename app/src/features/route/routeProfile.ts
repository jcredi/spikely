/**
 * Pure geometry for the A-to-B hiking route planner (spec section 8): turns a
 * route's coordinate list into distance-referenced sample points that the
 * elevation/snow profile and the linked map/profile interaction (spec 8.4,
 * 8.5) are built from. No DOM, no fetch, no MapLibre, no config - the same
 * posture `features/objects/seriesChartLayout.ts` takes.
 *
 * **The rule this module exists to enforce** (spec 8.3): "Analytical results
 * must not change simply because the user changes map zoom level." Every
 * sampling decision here is therefore in GROUND METRES along the route,
 * computed from coordinates alone. There is no screen-pixel, zoom, or
 * viewport input anywhere in this file - that is the invariant, and it is
 * why this is tested rather than eyeballed: a zoom-dependent sample spacing
 * would make the same route report different distance-with-snow numbers
 * depending on how far in the user happened to be looking, which would be a
 * silent correctness bug, not a rendering nit.
 *
 * Sampling this route (which points along it get analysed against FSC and
 * elevation data) is exactly what spec section 15 item 1 leaves open. This
 * module makes the sampling *mechanism* concrete now - even spacing in ground
 * metres, endpoints preserved exactly, a bounded sample count - but the
 * `DEFAULT_SPACING_METERS` value itself is a defensible default, not a frozen
 * decision; see the constant's own comment.
 *
 * Pure and dependency-free: `npm test` runs this directly under Node.
 */

/** A GeoJSON-order position: `[longitude, latitude]`. */
export type LonLat = readonly [number, number];

export type LatLng = { longitude: number; latitude: number };

export type RouteSample = {
  longitude: number;
  latitude: number;
  /** Metres from the route start, along the polyline (not straight-line). */
  distanceMeters: number;
};

export type ResampleResult = {
  samples: RouteSample[];
  /**
   * The spacing actually used, in metres. Equal to the requested spacing
   * unless MAX_SAMPLES would otherwise be exceeded, in which case this is
   * widened to the smallest spacing that fits - see `resampleAlongRoute`.
   */
  spacingMeters: number;
};

/**
 * Earth mean radius in metres (IUGG mean radius), used by `haversineMeters`.
 * A single spherical radius, not a full ellipsoid, is deliberate here: route
 * legs in this app are tens to hundreds of metres, and at that scale the
 * great-circle/haversine error against a proper geodesic (WGS84 ellipsoid)
 * is on the order of centimetres to low single-digit metres at worst - far
 * below GFSC's 60 m pixel (spec section 4.1, section 7.2), which is the
 * finest resolution any result derived from these distances can honestly
 * claim. A full geodesic library would be precision this app cannot use.
 */
const EARTH_RADIUS_METERS = 6371000;

/**
 * Default sample spacing along the route, in metres. Set to 60 m because
 * that is GFSC's native pixel size (docs/agent-guide.md, spec section 4.1/
 * 7.2): sampling finer than the data's own resolution would invent detail
 * the source raster does not have (the same reasoning spec section 5.4
 * applies to nearest-neighbour raster resampling). This is a reasonable
 * starting point for spec section 15 item 1 ("appropriately sampled FSC and
 * elevation data"), not a frozen product decision - a future elevation
 * source or UI need could justify a different value, but it should not
 * default to something denser than the snow data itself.
 */
export const DEFAULT_SPACING_METERS = 60;

/**
 * Hard cap on the number of samples `resampleAlongRoute` will ever return.
 * A 200 km route at the default 60 m spacing is about 3,300 samples, which
 * is fine for a chart; this cap exists so that nothing unbounded (an
 * unusually long or densely-vertexed route) ever reaches a chart or the map
 * interaction. When the cap would be exceeded, spacing is widened rather
 * than the route being truncated - see `resampleAlongRoute`.
 */
export const MAX_SAMPLES = 5000;

/**
 * Great-circle distance between two points, in metres, via the haversine
 * formula. See `EARTH_RADIUS_METERS` for why a spherical approximation is
 * accurate enough for this app's route-leg scale.
 */
export function haversineMeters(a: LatLng, b: LatLng): number {
  const lat1 = toRadians(a.latitude);
  const lat2 = toRadians(b.latitude);
  const dLat = toRadians(b.latitude - a.latitude);
  const dLon = toRadians(b.longitude - a.longitude);

  const sinDLat = Math.sin(dLat / 2);
  const sinDLon = Math.sin(dLon / 2);
  const h = sinDLat * sinDLat + Math.cos(lat1) * Math.cos(lat2) * sinDLon * sinDLon;
  const c = 2 * Math.asin(Math.min(1, Math.sqrt(h)));
  return EARTH_RADIUS_METERS * c;
}

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

function toLatLng([longitude, latitude]: LonLat): LatLng {
  return { longitude, latitude };
}

/**
 * Cumulative distance in metres from the first vertex to each vertex of
 * `coordinates`, in GeoJSON `[longitude, latitude]` order. One entry per
 * input coordinate; the first entry is always 0.
 *
 * An empty input returns an empty array; a single coordinate returns `[0]`.
 * Coincident consecutive vertices (a zero-length leg, or an entire
 * zero-length route) simply contribute 0 to the running total - there is no
 * division here, so this never produces NaN or throws.
 */
export function cumulativeDistances(coordinates: readonly LonLat[]): number[] {
  if (coordinates.length === 0) return [];
  const distances: number[] = [0];
  for (let i = 1; i < coordinates.length; i += 1) {
    const leg = haversineMeters(toLatLng(coordinates[i - 1]), toLatLng(coordinates[i]));
    distances.push(distances[i - 1] + leg);
  }
  return distances;
}

/** Total route length in metres. 0 for an empty or single-point route. */
export function routeLengthMeters(coordinates: readonly LonLat[]): number {
  const distances = cumulativeDistances(coordinates);
  return distances.length > 0 ? distances[distances.length - 1] : 0;
}

/**
 * The position at `distanceMeters` along the route (linear interpolation
 * within the segment it falls in). Out-of-range input is clamped to the
 * route's start or end rather than returning null: for the linked map/
 * profile interaction (spec 8.5), a finger that overshoots the end of the
 * profile should still show a dot sitting at the summit, not disappear.
 *
 * Returns `null` only when there is no route at all (empty `coordinates`).
 * A single-point route returns that point for any requested distance.
 */
export function pointAtDistance(coordinates: readonly LonLat[], distanceMeters: number): LatLng | null {
  if (coordinates.length === 0) return null;
  if (coordinates.length === 1) return toLatLng(coordinates[0]);
  return interpolate(coordinates, cumulativeDistances(coordinates), distanceMeters, 1).point;
}

/**
 * Position at `target` metres along a polyline whose cumulative distances are
 * already known, searching forward from vertex `from`.
 *
 * Splitting this out of `pointAtDistance` is what keeps `resampleAlongRoute`
 * linear. `pointAtDistance` rebuilds the whole cumulative table on every call,
 * which is right for a one-off lookup (a finger on the profile) and quadratic
 * if a resampling loop calls it per sample: a 8,000-vertex route sampled at
 * 60 m is ~3,300 lookups, so the naive version is ~26 million haversines and
 * takes seconds. Callers that walk forward in increasing distance pass the
 * previous result's `index` back in and the whole pass costs one table plus
 * one traversal.
 *
 * `target` is clamped into `[0, total]` here, so the returned index is always
 * a real segment end.
 */
function interpolate(
  coordinates: readonly LonLat[],
  distances: readonly number[],
  target: number,
  from: number,
): { point: LatLng; index: number } {
  const total = distances[distances.length - 1];
  const clamped = Math.min(Math.max(target, 0), total);

  let i = Math.max(1, from);
  while (i < coordinates.length - 1 && distances[i] < clamped) i += 1;

  const segStart = distances[i - 1];
  const segLength = distances[i] - segStart;
  // Zero-length segment (coincident vertices): any position along it is the
  // same point, so avoid a 0/0 division and just take the segment's start.
  const t = segLength > 0 ? (clamped - segStart) / segLength : 0;
  const [lon1, lat1] = coordinates[i - 1];
  const [lon2, lat2] = coordinates[i];
  return {
    point: { longitude: lon1 + (lon2 - lon1) * t, latitude: lat1 + (lat2 - lat1) * t },
    index: i,
  };
}

/**
 * Evenly spaced samples along the route polyline, in ground metres.
 *
 * - The first sample is exactly the route start and the last sample is
 *   exactly the route end, regardless of how the requested spacing divides
 *   the total length - these are the endpoints the user actually chose
 *   (an origin/destination object, spec 8.2), and dropping or approximating
 *   one (e.g. the summit routed to) would be a real defect, not rounding.
 * - Intermediate samples are linearly interpolated along the segment they
 *   fall in, via `pointAtDistance`.
 * - If the requested spacing would need more than `MAX_SAMPLES` samples to
 *   cover the route, the spacing is widened to the smallest value that fits
 *   in `MAX_SAMPLES` - the route is never truncated, because silently
 *   dropping the back half of a route would be the worst possible failure
 *   for a safety-adjacent planning tool. The returned `spacingMeters` is how
 *   a caller learns this happened.
 * - A zero-length route (every coordinate identical, or a single point)
 *   returns one sample at distance 0 - never a division by zero and never
 *   an infinite loop.
 * - An empty `coordinates` array returns no samples.
 */
export function resampleAlongRoute(
  coordinates: readonly LonLat[],
  spacingMeters: number = DEFAULT_SPACING_METERS,
): ResampleResult {
  if (coordinates.length === 0) {
    return { samples: [], spacingMeters };
  }

  // Built once and walked forward, not rebuilt per sample - see `interpolate`.
  const distances = cumulativeDistances(coordinates);
  const total = distances[distances.length - 1];

  if (total === 0) {
    const [longitude, latitude] = coordinates[0];
    return { samples: [{ longitude, latitude, distanceMeters: 0 }], spacingMeters };
  }

  let effectiveSpacing = spacingMeters;
  const requiredSamples = Math.floor(total / effectiveSpacing) + 1;
  if (requiredSamples > MAX_SAMPLES) {
    // Smallest spacing such that ceil(total / spacing) + 1 <= MAX_SAMPLES,
    // i.e. total / spacing <= MAX_SAMPLES - 1.
    effectiveSpacing = total / (MAX_SAMPLES - 1);
  }

  // Interior sample count as index*spacing, not repeated addition: summing
  // `effectiveSpacing` into a running total thousands of times would drift
  // with floating-point error and could push one sample past MAX_SAMPLES.
  // A tiny relative epsilon keeps a step that lands (up to float rounding)
  // exactly on `total` from being counted as an extra interior sample - it
  // is already the endpoint pushed separately below.
  const epsilon = total * 1e-9;
  const interiorCount = Math.min(MAX_SAMPLES - 1, Math.ceil((total - epsilon) / effectiveSpacing));

  const samples: RouteSample[] = [];
  let cursor = 1;
  for (let i = 0; i < interiorCount; i += 1) {
    const distance = i * effectiveSpacing;
    const { point, index } = interpolate(coordinates, distances, distance, cursor);
    cursor = index;
    samples.push({ longitude: point.longitude, latitude: point.latitude, distanceMeters: distance });
  }
  const last = coordinates[coordinates.length - 1];
  samples.push({ longitude: last[0], latitude: last[1], distanceMeters: total });

  return { samples, spacingMeters: effectiveSpacing };
}
