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

// The single reprojected GFSC product we currently ship - see
// recon/make_overlay.py. The sidecar JSON carries the corner coordinates, so
// swapping products is a one-line change here.
export const snowOverlayUrl = "/snow/gfsc_32TPS_20260206.json";
