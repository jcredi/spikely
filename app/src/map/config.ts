const apiKey = import.meta.env.VITE_MAPTILER_API_KEY;

if (!apiKey) {
  throw new Error(
    "VITE_MAPTILER_API_KEY is not set - copy app/.env.example to app/.env and add a MapTiler API key.",
  );
}

export const styleUrl = `https://api.maptiler.com/maps/outdoor/style.json?key=${apiKey}`;

// Western Alps, with the Italian Apennines reachable by panning south.
export const initialView = {
  center: [8.5, 45.3] as [number, number],
  zoom: 6.3,
};

// Production points this at R2 with VITE_SNOW_MANIFEST_URL. A locally rendered
// preview uses /snow/latest.json; when neither exists the app falls back to the
// checked-in one-tile reconnaissance overlay.
export const snowManifestUrl =
  import.meta.env.VITE_SNOW_MANIFEST_URL || "/snow/latest.json";
export const fallbackSnowOverlayUrl = "/snow/gfsc_32TPS_20260206.json";
