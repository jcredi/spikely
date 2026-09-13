/**
 * Tests for the Mapbox Directions response validator.
 *
 * Run with `npm test` (Node runs the TypeScript directly - no bundler,
 * browser or map). Every rejection case is something a corrupted, broken or
 * hostile Directions response could otherwise have put on the map or
 * profile - or, for the size cap, used to exhaust memory or the DOM.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  DirectionsError,
  MAX_ROUTE_COORDINATES,
  NoRouteError,
  validateDirectionsResponse,
} from "./directionsSchema.ts";

/** A response in the shape Mapbox really returns for a walking route. */
function response(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    code: "Ok",
    waypoints: [
      { name: "", location: [7.7, 45.9] },
      { name: "", location: [7.75, 45.95] },
    ],
    routes: [
      {
        distance: 4200.5,
        duration: 3600,
        geometry: {
          type: "LineString",
          coordinates: [
            [7.7, 45.9],
            [7.72, 45.92],
            [7.75, 45.95],
          ],
        },
      },
    ],
    ...overrides,
  };
}

describe("validateDirectionsResponse", () => {
  it("accepts a well-formed walking route and returns the first route", () => {
    const result = validateDirectionsResponse(response());
    assert.equal(result.distanceMeters, 4200.5);
    assert.equal(result.durationSeconds, 3600);
    assert.deepEqual(result.coordinates, [
      [7.7, 45.9],
      [7.72, 45.92],
      [7.75, 45.95],
    ]);
  });

  it("throws NoRouteError, not DirectionsError, for an in-band NoRoute code", () => {
    const body = response({ code: "NoRoute", routes: [] });
    assert.throws(() => validateDirectionsResponse(body), NoRouteError);
    try {
      validateDirectionsResponse(body);
      assert.fail("expected NoRouteError to be thrown");
    } catch (error) {
      assert.ok(NoRouteError.isNoRoute(error));
      assert.ok(!(error instanceof DirectionsError));
      assert.equal((error as NoRouteError).code, "NoRoute");
    }
  });

  it("throws NoRouteError for other Mapbox routability codes", () => {
    assert.throws(
      () => validateDirectionsResponse(response({ code: "NoSegment", routes: [] })),
      NoRouteError,
    );
  });

  it("rejects a missing field as malformed, not as no-route", () => {
    const body = response();
    delete (body.routes as Record<string, unknown>[])[0].distance;
    assert.throws(() => validateDirectionsResponse(body), DirectionsError);
  });

  it("rejects a field with the wrong type", () => {
    const body = response();
    (body.routes as Record<string, unknown>[])[0].duration = "3600";
    assert.throws(() => validateDirectionsResponse(body), DirectionsError);
  });

  it("rejects a single-point LineString", () => {
    const body = response();
    (body.routes as Record<string, unknown>[])[0].geometry = {
      type: "LineString",
      coordinates: [[7.7, 45.9]],
    };
    assert.throws(() => validateDirectionsResponse(body), DirectionsError);
  });

  it("rejects an out-of-range latitude", () => {
    const body = response();
    (body.routes as Record<string, unknown>[])[0].geometry = {
      type: "LineString",
      coordinates: [
        [7.7, 45.9],
        [7.72, 95.0],
      ],
    };
    assert.throws(() => validateDirectionsResponse(body), DirectionsError);
  });

  it("rejects an out-of-range longitude", () => {
    const body = response();
    (body.routes as Record<string, unknown>[])[0].geometry = {
      type: "LineString",
      coordinates: [
        [7.7, 45.9],
        [200.0, 45.95],
      ],
    };
    assert.throws(() => validateDirectionsResponse(body), DirectionsError);
  });

  it("rejects NaN anywhere in a position", () => {
    const body = response();
    (body.routes as Record<string, unknown>[])[0].geometry = {
      type: "LineString",
      coordinates: [
        [7.7, 45.9],
        [Number.NaN, 45.95],
      ],
    };
    assert.throws(() => validateDirectionsResponse(body), DirectionsError);
  });

  it("rejects Infinity anywhere in a position", () => {
    const body = response();
    (body.routes as Record<string, unknown>[])[0].geometry = {
      type: "LineString",
      coordinates: [
        [7.7, 45.9],
        [7.72, Number.POSITIVE_INFINITY],
      ],
    };
    assert.throws(() => validateDirectionsResponse(body), DirectionsError);
  });

  it("accepts a 3-element position and truncates the third entry", () => {
    const body = response();
    (body.routes as Record<string, unknown>[])[0].geometry = {
      type: "LineString",
      coordinates: [
        [7.7, 45.9, 1234],
        [7.75, 45.95, 5678],
      ],
    };
    const result = validateDirectionsResponse(body);
    assert.deepEqual(result.coordinates, [
      [7.7, 45.9],
      [7.75, 45.95],
    ]);
    for (const position of result.coordinates) {
      assert.equal(position.length, 2);
    }
  });

  it("rejects a LineString above MAX_ROUTE_COORDINATES", () => {
    const coordinates: [number, number][] = [];
    for (let i = 0; i < MAX_ROUTE_COORDINATES + 1; i += 1) {
      coordinates.push([7.7, 45.9]);
    }
    const body = response();
    (body.routes as Record<string, unknown>[])[0].geometry = {
      type: "LineString",
      coordinates,
    };
    assert.throws(() => validateDirectionsResponse(body), DirectionsError);
  });
});
