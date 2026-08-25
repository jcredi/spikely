import type { Map } from "maplibre-gl";

/** Sidecar written by recon/make_overlay.py alongside the overlay PNG. */
export type SnowOverlayMeta = {
  image: string;
  product: string;
  tile: string;
  /** Product date (the daily composite date), ISO yyyy-mm-dd. */
  date: string;
  sourceCrs: string;
  sourceResolutionMeters: number;
  size: [number, number];
  /** Top-left, top-right, bottom-right, bottom-left - MapLibre's image-source order. */
  coordinates: [[number, number], [number, number], [number, number], [number, number]];
  bounds: [number, number, number, number];
  coverage: Record<string, number>;
};

export const SOURCE_ID = "gfsc-snow";
export const LAYER_ID = "gfsc-snow";

// Keep the snow above landcover and hillshade but below everything a hiker
// navigates by. In MapTiler Outdoor the contour lines are the first layer of
// that kind; the rest are fallbacks in case the style's layer ids change.
const INSERT_BEFORE = ["contour_index", "contour", "waterway_river", "water"];

export type SnowOverlay = {
  meta: SnowOverlayMeta;
  bounds: [number, number, number, number];
  setVisible: (visible: boolean) => void;
  isVisible: () => boolean;
};

/**
 * Add one reprojected GFSC product to the map as an image overlay.
 *
 * The PNG is already in EPSG:3857, which is what MapLibre renders in, so its
 * four corners describe an axis-aligned rectangle and the image lands
 * pixel-for-pixel where it belongs - no warping on the client side.
 */
export async function addSnowOverlay(map: Map, sidecarUrl: string): Promise<SnowOverlay> {
  const response = await fetch(sidecarUrl);
  if (!response.ok) {
    throw new Error(`Failed to load snow overlay metadata: ${response.status} ${sidecarUrl}`);
  }
  const meta: SnowOverlayMeta = await response.json();
  const imageUrl = new URL(meta.image, new URL(sidecarUrl, window.location.href)).href;

  map.addSource(SOURCE_ID, {
    type: "image",
    url: imageUrl,
    coordinates: meta.coordinates,
  });

  const beforeId = INSERT_BEFORE.find((id) => map.getLayer(id));

  map.addLayer(
    {
      id: LAYER_ID,
      type: "raster",
      source: SOURCE_ID,
      paint: {
        // Opacity is already baked into the PNG's palette alpha, per GFSC value.
        // Nearest, not linear: at hiking zooms this shows the true 60 m GFSC
        // pixels rather than a smooth gradient the data doesn't actually have.
        "raster-resampling": "nearest",
        "raster-fade-duration": 0,
      },
    },
    beforeId,
  );

  // Snow at full opacity would paint flat over the basemap's shaded relief, and
  // a mountain map can't afford to lose that. Re-order so the hillshade draws
  // *over* the snow instead: the terrain reads through at no cost to snow
  // contrast. Moving the existing layer rather than adding a second one matters
  // - two hillshade passes double-shade everywhere the snow isn't.
  const hillshade = map.getStyle().layers.find((layer) => layer.type === "hillshade");
  if (hillshade && beforeId) {
    map.moveLayer(hillshade.id, beforeId);
  }

  return {
    meta,
    bounds: meta.bounds,
    setVisible: (visible) =>
      map.setLayoutProperty(LAYER_ID, "visibility", visible ? "visible" : "none"),
    isVisible: () => map.getLayoutProperty(LAYER_ID, "visibility") !== "none",
  };
}
