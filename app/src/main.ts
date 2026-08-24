import maplibregl from "maplibre-gl";
import { initialView, styleUrl } from "./map/config";
import "./style.css";

new maplibregl.Map({
  container: "map",
  style: styleUrl,
  center: initialView.center,
  zoom: initialView.zoom,
}).addControl(new maplibregl.NavigationControl(), "top-right");
