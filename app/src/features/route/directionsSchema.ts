/**
 * Runtime validation for the Mapbox Directions API v5 response
 * (`mapbox/walking` profile), decided as the MVP routing provider by spec
 * section 8 and `docs/plan.md` item 2 (2026-09-12).
 *
 * This is the network-facing trust boundary for routing, in the same spirit
 * as `../objects/objectIndexSchema.ts` and `../snow/manifestSchema.ts`: the
 * types the app would like to receive check nothing at runtime, so this is
 * the actual gate between an HTTP response and the map/profile. The request
 * this validates is made with `geometries=geojson&overview=full&steps=false`,
 * so only that specific shape is accepted - not the encoded-polyline or
 * turn-by-turn shapes Mapbox can also return under other query parameters.
 *
 * Two distinct kinds of "this didn't work", and this module is careful not to
 * conflate them:
 *
 *  - **Malformed response** (`DirectionsError`, thrown): the body is not
 *    shaped like a Directions response at all - missing fields, wrong types,
 *    an unbounded or non-finite geometry. This means the provider sent us
 *    something we do not understand, and the caller should treat it as a
 *    fetch-layer failure.
 *  - **No route found** (`NoRouteError`, thrown, `NoRouteError.isNoRoute()`
 *    to distinguish it): Mapbox signals routability failures *in-band*, with
 *    HTTP 200 and a `code` other than `"Ok"` - `"NoRoute"` (no walking path
 *    connects the two points), `"NoSegment"` (a waypoint could not be matched
 *    to the road/path network), `"ProfileNotFound"`, and others. This is a
 *    real, user-facing answer - "the provider could not find a walking route
 *    between these points" - not a validation failure, so it is its own
 *    error subclass rather than a message string the caller has to pattern
 *    match, and the caller is expected to catch it separately and show it as
 *    a routing outcome rather than an error banner.
 *
 * Both are thrown rather than returned as a sentinel value so a caller that
 * only handles one of the two still fails loudly on the other, instead of
 * silently falling through - but they are deliberately different classes so
 * `catch (e) { if (e instanceof NoRouteError) ... }` never has to also rule
 * out a malformed body.
 *
 * Only the *first* route is validated and returned: spec section 8.1 limits
 * the MVP to one origin, one destination, one mode, with no alternatives UI,
 * so accepting more routes than that would be inventing scope this app does
 * not have a UI for.
 *
 * Elevation: Mapbox Directions does not return real elevation for the
 * `walking` profile (`docs/plan.md` item 2 - this is exactly why a separate
 * DEM extract is still needed). GeoJSON positions are nonetheless allowed a
 * third array entry per the GeoJSON spec, and some providers or proxies do
 * populate it. This validator ignores a third entry rather than rejecting
 * the position - but it never carries it through to `ValidatedRoute`, which
 * normalises every coordinate to a two-element `[lon, lat]` tuple. That way
 * nothing downstream can mistake a stray third number for real elevation
 * data, which it is not.
 *
 * This module imports nothing (no map config, no `import.meta.env`, no
 * `fetch`, no DOM, no MapLibre), so `npm test` runs it directly under Node.
 */

/** The Mapbox Directions v5 response shape this app requests and accepts. */
export type DirectionsResponse = {
  code: string;
  routes: unknown[];
  waypoints: unknown[];
};

/** One validated route, normalised for downstream map/profile use. */
export type ValidatedRoute = {
  distanceMeters: number;
  durationSeconds: number;
  /** Always two-element [lon, lat] tuples - any third (elevation) entry from
   *  the wire is dropped; see the module docstring on why. */
  coordinates: [number, number][];
};

// A realistic long alpine day route: 40 km at, say, one vertex every 5 m of
// path (already generous for `overview=full` simplification) is 8,000
// points. 200,000 gives roughly 25x that headroom for a multi-day traverse
// or a wandering path, while still being small enough that holding and
// rendering it can never be the thing that exhausts memory or the DOM - a
// hostile or broken response cannot hand the app a multi-million-point line.
export const MAX_ROUTE_COORDINATES = 200_000;

/** Malformed response: the body is not shaped like a Directions response. */
export class DirectionsError extends Error {}

/**
 * A well-formed response reporting, in-band, that no walking route exists
 * between the requested points (or another routability failure - see
 * `code`). This is a real answer from the provider, not a parse failure.
 */
export class NoRouteError extends Error {
  /** The Mapbox status code, e.g. "NoRoute", "NoSegment", "ProfileNotFound". */
  readonly code: string;

  constructor(code: string) {
    super(`Mapbox Directions returned code "${code}", not "Ok"`);
    this.code = code;
  }

  static isNoRoute(error: unknown): error is NoRouteError {
    return error instanceof NoRouteError;
  }
}

function fail(message: string): never {
  throw new DirectionsError(message);
}

function requireFiniteNumber(value: unknown, field: string, min: number, max: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    fail(`${field} must be a finite number`);
  }
  if (value < min || value > max) fail(`${field} must be between ${min} and ${max}`);
  return value;
}

/** One [lon, lat] or [lon, lat, elevation] GeoJSON position. The optional
 *  third entry is checked (must be finite, if present) but discarded. */
function requirePosition(value: unknown, field: string): [number, number] {
  if (!Array.isArray(value) || value.length < 2 || value.length > 3) {
    fail(`${field} must be an array of 2 or 3 numbers`);
  }
  const lon = requireFiniteNumber(value[0], `${field}[0]`, -180, 180);
  const lat = requireFiniteNumber(value[1], `${field}[1]`, -90, 90);
  if (value.length === 3) {
    // Present but ignored - see the module docstring's elevation note.
    requireFiniteNumber(value[2], `${field}[2]`, -Infinity, Infinity);
  }
  return [lon, lat];
}

function requireLineString(value: unknown, field: string): [number, number][] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(`${field} must be a JSON object`);
  }
  const source = value as Record<string, unknown>;
  if (source.type !== "LineString") {
    fail(`${field}.type must be "LineString", got ${String(source.type)}`);
  }
  if (!Array.isArray(source.coordinates)) {
    fail(`${field}.coordinates must be an array`);
  }
  const coordinates = source.coordinates;
  if (coordinates.length < 2) {
    fail(`${field}.coordinates must have at least 2 positions`);
  }
  if (coordinates.length > MAX_ROUTE_COORDINATES) {
    fail(
      `${field}.coordinates has ${coordinates.length} positions, ` +
        `over the ${MAX_ROUTE_COORDINATES} limit`,
    );
  }
  return coordinates.map((position: unknown, index: number) =>
    requirePosition(position, `${field}.coordinates[${index}]`),
  );
}

function requireRoute(value: unknown, field: string): ValidatedRoute {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(`${field} must be a JSON object`);
  }
  const source = value as Record<string, unknown>;

  const distanceMeters = requireFiniteNumber(source.distance, `${field}.distance`, 0, Infinity);
  const durationSeconds = requireFiniteNumber(source.duration, `${field}.duration`, 0, Infinity);
  const coordinates = requireLineString(source.geometry, `${field}.geometry`);

  return { distanceMeters, durationSeconds, coordinates };
}

/**
 * Validate a Mapbox Directions v5 response for the `mapbox/walking` profile,
 * requested with `geometries=geojson&overview=full&steps=false`.
 *
 * Throws `NoRouteError` when the body is well-formed but Mapbox's own `code`
 * says no route exists (or another in-band routability failure), and
 * `DirectionsError` when the body is not shaped like a Directions response at
 * all. Only the first route is validated and returned - see the module
 * docstring.
 */
export function validateDirectionsResponse(document: unknown): ValidatedRoute {
  if (typeof document !== "object" || document === null || Array.isArray(document)) {
    fail("directions response must be a JSON object");
  }
  const source = document as Record<string, unknown>;

  if (typeof source.code !== "string" || source.code.length === 0) {
    fail("code must be a non-empty string");
  }
  if (source.code !== "Ok") {
    // Well-formed, in-band routability failure - not a parse error.
    throw new NoRouteError(source.code);
  }

  if (!Array.isArray(source.routes) || source.routes.length === 0) {
    fail("routes must be a non-empty array");
  }
  if (!Array.isArray(source.waypoints)) {
    fail("waypoints must be an array");
  }

  return requireRoute(source.routes[0], "routes[0]");
}
