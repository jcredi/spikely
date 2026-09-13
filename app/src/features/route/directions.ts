/**
 * The network boundary for A-to-B hiking routes (spec section 8.1): one
 * request to Mapbox Directions' `mapbox/walking` profile, validated by
 * `directionsSchema.ts` before any value reaches the map.
 *
 * Why Mapbox and not OpenRouteService, which was the pick for part of
 * 2026-09-12: ORS's own staff forbid delivering an API key to a browser and
 * ORS offers no domain restriction, so a keyless-frontend app like this one
 * cannot use it without the backend spec section 11 says the MVP does not
 * have. Mapbox public tokens *can* be URL-restricted, which is what makes a
 * token in a public bundle defensible. The full comparison is in
 * `docs/research/routing-and-dem-options.md`, including the correction that
 * reversed the original recommendation - read it before reopening this.
 *
 * `mapbox/walking` is the profile, not `mapbox/driving`; Mapbox has no
 * hiking-specific profile, which is a real limitation to state rather than
 * paper over: it is an urban-walking profile applied to alpine paths, and it
 * knows nothing about trail difficulty, exposure, or seasonal closure. Spec
 * section 8.6 requires the app to say so, and `routePanel.ts` does.
 *
 * This module holds the token and the `fetch`, exactly as
 * `../search/geocode.ts` does for place search, so everything below it stays
 * pure and Node-testable.
 */
import { mapboxAccessToken } from "../../map/config";
import {
  DirectionsError,
  NoRouteError,
  validateDirectionsResponse,
  type ValidatedRoute,
} from "./directionsSchema.ts";

export { DirectionsError, NoRouteError, type ValidatedRoute };

const ENDPOINT = "https://api.mapbox.com/directions/v5/mapbox/walking";

/**
 * Bound the response before it is parsed. `overview=full` on a long alpine
 * route is tens of kilobytes of JSON; a megabyte means something is wrong
 * with the response, not with the route. `directionsSchema.ts` bounds the
 * decoded geometry too - this bounds the bytes, which is the cheaper check.
 */
const MAX_RESPONSE_BYTES = 4 * 1024 * 1024;

export type RoutePoint = { longitude: number; latitude: number };

/** Whether routing can be offered at all - see `mapboxAccessToken` in `map/config.ts`. */
export function routingIsConfigured(): boolean {
  return mapboxAccessToken !== null;
}

/** Six decimals is ~0.1 m: far finer than any path geometry, and it keeps the URL short. */
function formatPoint(point: RoutePoint): string {
  return `${point.longitude.toFixed(6)},${point.latitude.toFixed(6)}`;
}

/**
 * Fetch one walking route from `start` to `destination`.
 *
 * Throws `NoRouteError` when Mapbox answers, in-band, that no walking route
 * connects the two points - a real answer to show the user, not a failure -
 * and `DirectionsError` for everything else, including a missing token, a
 * transport failure, and an HTTP error. See `directionsSchema.ts` for why
 * those two are deliberately different classes.
 */
export async function fetchWalkingRoute(
  start: RoutePoint,
  destination: RoutePoint,
  options: { signal?: AbortSignal } = {},
): Promise<ValidatedRoute> {
  if (mapboxAccessToken === null) {
    // Callers are expected to check `routingIsConfigured()` and never offer
    // the control at all; this is the backstop, and it says which variable is
    // missing rather than surfacing an opaque 401 from Mapbox.
    throw new DirectionsError("VITE_MAPBOX_TOKEN is not set, so routing is unavailable");
  }

  const url = new URL(`${ENDPOINT}/${formatPoint(start)};${formatPoint(destination)}`);
  // GeoJSON rather than an encoded polyline: the decoder would be one more
  // hand-written parser on the trust boundary, for a payload this app is not
  // large enough to care about the size of.
  url.searchParams.set("geometries", "geojson");
  // The full geometry, not the zoom-dependent simplification Mapbox defaults
  // to. Spec section 8.3: "Analytical results must not change simply because
  // the user changes map zoom level" - a simplified overview would make the
  // route's own length depend on how it was asked for.
  url.searchParams.set("overview", "full");
  // No turn-by-turn instructions: this is a planning aid, not a navigator
  // (spec section 8.6), and the steps array is most of the response size.
  url.searchParams.set("steps", "false");
  url.searchParams.set("access_token", mapboxAccessToken);

  let response: Response;
  try {
    response = await fetch(url, { signal: options.signal });
  } catch (error) {
    // An abort is the caller superseding its own request; let it through
    // untouched so the caller can ignore it rather than showing an error.
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new DirectionsError(`could not reach the routing provider: ${String(error)}`);
  }

  if (response.status === 401 || response.status === 403) {
    // The overwhelmingly likely cause is the token: expired, revoked, or
    // URL-restricted to an origin this build is not served from.
    throw new DirectionsError(
      `the routing provider rejected this app's token (HTTP ${response.status})`,
    );
  }
  if (response.status === 422) {
    // Mapbox uses 422 for a request it understood but cannot answer - most
    // often a coordinate it cannot snap to any walkable segment. That is the
    // same class of answer as an in-band "NoSegment", so it is reported the
    // same way rather than as a broken app.
    throw new NoRouteError("NoSegment");
  }
  if (response.status === 429) {
    throw new DirectionsError("the routing provider's rate limit was reached - try again shortly");
  }
  if (!response.ok) {
    throw new DirectionsError(`routing request failed: HTTP ${response.status}`);
  }

  const declared = Number(response.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_RESPONSE_BYTES) {
    throw new DirectionsError(`routing response declares ${declared} bytes, over the limit`);
  }
  const body = await response.arrayBuffer();
  if (body.byteLength > MAX_RESPONSE_BYTES) {
    throw new DirectionsError(`routing response is ${body.byteLength} bytes, over the limit`);
  }

  let document: unknown;
  try {
    document = JSON.parse(new TextDecoder().decode(body));
  } catch (error) {
    throw new DirectionsError(`routing response is not valid JSON: ${String(error)}`);
  }
  return validateDirectionsResponse(document);
}
