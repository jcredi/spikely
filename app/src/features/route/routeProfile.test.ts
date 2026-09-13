/**
 * Tests for the A-to-B route planner's pure geometry (spec section 8). The
 * invariant that matters most - spec 8.3's "analytical results must not
 * change simply because the user changes map zoom level" - shows up here as
 * every function taking only coordinates and metres, never a pixel/zoom/
 * viewport value; these tests exercise the metre-based sampling contract
 * that the rest of the profile/chart/map-linking code is built on.
 *
 * Run with `npm test`.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  cumulativeDistances,
  DEFAULT_SPACING_METERS,
  haversineMeters,
  MAX_SAMPLES,
  pointAtDistance,
  resampleAlongRoute,
  routeLengthMeters,
  type LonLat,
} from "./routeProfile.ts";

describe("haversineMeters", () => {
  it("matches the known distance for one degree of longitude at the equator", () => {
    // At the equator, one degree of longitude is one degree of great-circle
    // arc, same as one degree of latitude anywhere: on a sphere of radius
    // 6,371,000 m that is 2*pi*R/360 = 111,194.9 m. Real-world (WGS84
    // ellipsoid) is about 111,320 m at the equator; the ~125 m spherical
    // approximation error is far below GFSC's 60 m pixel (spec 4.1/7.2),
    // which is the resolution ceiling any result built from these distances
    // can honestly claim.
    const distance = haversineMeters({ longitude: 0, latitude: 0 }, { longitude: 1, latitude: 0 });
    assert.ok(Math.abs(distance - 111194.9) < 200, `expected ~111194.9 m, got ${distance}`);
  });

  it("returns 0 for two identical points", () => {
    const p = { longitude: 12.34, latitude: 45.67 };
    assert.equal(haversineMeters(p, p), 0);
  });
});

describe("cumulativeDistances", () => {
  it("is empty for an empty route", () => {
    assert.deepEqual(cumulativeDistances([]), []);
  });

  it("is [0] for a single-point route", () => {
    assert.deepEqual(cumulativeDistances([[0, 0]]), [0]);
  });

  it("starts at 0 and is monotonically non-decreasing", () => {
    const coords: LonLat[] = [
      [7.0, 45.0],
      [7.01, 45.0],
      [7.01, 45.01],
      [7.0, 45.02],
    ];
    const distances = cumulativeDistances(coords);
    assert.equal(distances.length, coords.length);
    assert.equal(distances[0], 0);
    for (let i = 1; i < distances.length; i += 1) {
      assert.ok(distances[i] >= distances[i - 1], `distances[${i}] should be >= distances[${i - 1}]`);
    }
  });

  it("does not advance across coincident consecutive vertices", () => {
    const coords: LonLat[] = [
      [7.0, 45.0],
      [7.0, 45.0],
      [7.0, 45.0],
    ];
    assert.deepEqual(cumulativeDistances(coords), [0, 0, 0]);
  });
});

describe("routeLengthMeters", () => {
  it("is 0 for an empty or single-point route", () => {
    assert.equal(routeLengthMeters([]), 0);
    assert.equal(routeLengthMeters([[7, 45]]), 0);
  });

  it("is 0 for a route where every coordinate is identical (zero length)", () => {
    const coords: LonLat[] = [
      [7.0, 45.0],
      [7.0, 45.0],
      [7.0, 45.0],
    ];
    assert.equal(routeLengthMeters(coords), 0);
  });
});

describe("resampleAlongRoute", () => {
  it("handles an empty route without throwing", () => {
    const result = resampleAlongRoute([], DEFAULT_SPACING_METERS);
    assert.deepEqual(result.samples, []);
  });

  it("handles a single-point route as one zero-distance sample", () => {
    const result = resampleAlongRoute([[7, 45]], DEFAULT_SPACING_METERS);
    assert.equal(result.samples.length, 1);
    assert.equal(result.samples[0].distanceMeters, 0);
    assert.equal(result.samples[0].longitude, 7);
    assert.equal(result.samples[0].latitude, 45);
  });

  it("handles a zero-length route (all coordinates identical) without dividing by zero or looping forever", () => {
    const coords: LonLat[] = [
      [7.0, 45.0],
      [7.0, 45.0],
      [7.0, 45.0],
    ];
    const result = resampleAlongRoute(coords, 60);
    assert.equal(result.samples.length, 1);
    assert.equal(result.samples[0].distanceMeters, 0);
    assert.equal(result.samples[0].longitude, 7.0);
    assert.equal(result.samples[0].latitude, 45.0);
  });

  it("resamples a straight two-point line with the exact endpoints and expected count", () => {
    // ~1112 m north-south leg (0.01 degree of latitude), spaced every 100 m:
    // that is 12 intervals plus the guaranteed final endpoint sample.
    const start: LonLat = [7.0, 45.0];
    const end: LonLat = [7.0, 45.01];
    const total = haversineMeters({ longitude: start[0], latitude: start[1] }, { longitude: end[0], latitude: end[1] });

    const { samples, spacingMeters } = resampleAlongRoute([start, end], 100);

    assert.equal(spacingMeters, 100);
    assert.equal(samples[0].longitude, start[0]);
    assert.equal(samples[0].latitude, start[1]);
    assert.equal(samples[0].distanceMeters, 0);

    const lastSample = samples[samples.length - 1];
    assert.equal(lastSample.longitude, end[0]);
    assert.equal(lastSample.latitude, end[1]);
    assert.ok(Math.abs(lastSample.distanceMeters - total) < 1e-6);

    const expectedCount = Math.floor(total / 100) + 1 + 1; // interior samples + guaranteed final endpoint
    assert.equal(samples.length, expectedCount);
  });

  it("a sample's distance matches its position along the route", () => {
    const start: LonLat = [7.0, 45.0];
    const end: LonLat = [7.02, 45.0];
    const { samples } = resampleAlongRoute([start, end], 250);

    for (const sample of samples) {
      const expectedPoint = pointAtDistance([start, end], sample.distanceMeters);
      assert.ok(expectedPoint !== null);
      assert.ok(Math.abs(expectedPoint!.longitude - sample.longitude) < 1e-9);
      assert.ok(Math.abs(expectedPoint!.latitude - sample.latitude) < 1e-9);
    }
  });

  it("widens spacing rather than truncating the route when MAX_SAMPLES would otherwise be exceeded", () => {
    // A long route (about 220 km) at the default 60 m spacing would need
    // roughly 3,700 samples - well under MAX_SAMPLES on its own - so force
    // the cap with a deliberately tiny requested spacing instead.
    const start: LonLat = [7.0, 45.0];
    const end: LonLat = [9.0, 45.0]; // roughly 157 km at this latitude
    const total = routeLengthMeters([start, end]);

    const { samples, spacingMeters } = resampleAlongRoute([start, end], 1); // 1 m spacing requested

    assert.ok(spacingMeters > 1, "spacing should have been widened");
    assert.ok(samples.length <= MAX_SAMPLES, `expected at most ${MAX_SAMPLES} samples, got ${samples.length}`);

    // The route is never truncated: the last sample is still the true end.
    const lastSample = samples[samples.length - 1];
    assert.ok(Math.abs(lastSample.distanceMeters - total) < 1e-6);
    assert.equal(lastSample.longitude, end[0]);
    assert.equal(lastSample.latitude, end[1]);
  });
});

describe("pointAtDistance", () => {
  const coords: LonLat[] = [
    [7.0, 45.0],
    [7.0, 45.01],
  ];

  it("returns null only for an empty route", () => {
    assert.equal(pointAtDistance([], 10), null);
  });

  it("clamps to the route start for a negative distance", () => {
    const point = pointAtDistance(coords, -1000);
    assert.equal(point?.longitude, coords[0][0]);
    assert.equal(point?.latitude, coords[0][1]);
  });

  it("clamps to the route end for a distance beyond the route length", () => {
    const total = routeLengthMeters(coords);
    const point = pointAtDistance(coords, total + 5000);
    assert.equal(point?.longitude, coords[1][0]);
    assert.equal(point?.latitude, coords[1][1]);
  });

  it("interpolates the midpoint at half the route length", () => {
    const total = routeLengthMeters(coords);
    const point = pointAtDistance(coords, total / 2);
    assert.ok(point !== null);
    assert.ok(Math.abs(point!.latitude - 45.005) < 1e-6);
    assert.equal(point!.longitude, 7.0);
  });

  it("returns the single point of a one-coordinate route for any distance", () => {
    const point = pointAtDistance([[7, 45]], 12345);
    assert.equal(point?.longitude, 7);
    assert.equal(point?.latitude, 45);
  });
});

/**
 * `resampleAlongRoute` walks the cumulative-distance table forward with a
 * moving segment cursor instead of re-deriving it for every sample, which is
 * what keeps it linear rather than quadratic (a 8,000-vertex route sampled at
 * 60 m would otherwise be ~26 million haversines). The optimisation is only
 * worth having if it is exactly equivalent to the naive lookup, so that
 * equivalence is asserted rather than assumed - on a deliberately awkward
 * polyline with uneven leg lengths, a doubled vertex and a backtrack, since a
 * straight line would not exercise the cursor's segment advance at all.
 */
describe("resampleAlongRoute matches the per-sample lookup", () => {
  it("agrees with pointAtDistance on an uneven, self-doubling route", () => {
    const coordinates: [number, number][] = [
      [7.0, 45.0],
      [7.0005, 45.0],
      [7.0005, 45.0], // doubled vertex: a zero-length segment mid-route
      [7.02, 45.004],
      [7.021, 45.02],
      [7.01, 45.021], // backtracks west
      [7.05, 45.03],
    ];
    const { samples, spacingMeters } = resampleAlongRoute(coordinates, 25);
    assert.ok(samples.length > 20, `expected a multi-sample route, got ${samples.length}`);
    assert.equal(spacingMeters, 25);

    for (const sample of samples) {
      const expected = pointAtDistance(coordinates, sample.distanceMeters);
      assert.ok(expected !== null);
      // Both paths do the same interpolation arithmetic, so this is an exact
      // match rather than an approximate one; a tolerance here would hide a
      // cursor that landed on the wrong segment.
      assert.equal(sample.longitude, expected.longitude, `longitude at ${sample.distanceMeters} m`);
      assert.equal(sample.latitude, expected.latitude, `latitude at ${sample.distanceMeters} m`);
    }
  });

  it("stays fast on a route with many vertices", () => {
    // 8,000 vertices is the order of a long alpine day route at `overview=full`.
    const coordinates: [number, number][] = Array.from({ length: 8000 }, (_, i) => [
      7 + i * 0.00005,
      45 + i * 0.00002,
    ]);
    const started = Date.now();
    const { samples } = resampleAlongRoute(coordinates, DEFAULT_SPACING_METERS);
    const elapsed = Date.now() - started;
    assert.ok(samples.length > 100);
    // Generous by two orders of magnitude against the linear implementation,
    // and still far under what the quadratic one took - this is a guard
    // against reintroducing the per-sample table rebuild, not a benchmark.
    assert.ok(elapsed < 1000, `resampling took ${elapsed} ms`);
  });
});
