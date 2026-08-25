import type { IControl, Map } from "maplibre-gl";
import type { SnowOverlay } from "../map/snowOverlay";

function formatProductDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(date.valueOf())
    ? iso
    : date.toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      });
}

/**
 * Snow layer on/off, plus what you're looking at and a way to get to it.
 *
 * The "Zoom to data" button exists because we currently ship exactly one
 * sample GFSC tile while the map opens on the whole Alps - it goes away once
 * there's real coverage.
 */
export class SnowControl implements IControl {
  private container!: HTMLElement;

  constructor(private readonly overlay: SnowOverlay) {}

  onAdd(map: Map): HTMLElement {
    const { meta } = this.overlay;

    this.container = document.createElement("div");
    this.container.className = "maplibregl-ctrl maplibregl-ctrl-group snow-ctrl";

    const toggle = document.createElement("label");
    toggle.className = "snow-ctrl__toggle";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = this.overlay.isVisible();
    checkbox.addEventListener("change", () => this.overlay.setVisible(checkbox.checked));

    const label = document.createElement("span");
    label.textContent = "Snow cover";

    toggle.append(checkbox, label);

    const metaLine = document.createElement("p");
    metaLine.className = "snow-ctrl__meta";
    metaLine.textContent = `${formatProductDate(meta.date)} · tile ${meta.tile}`;
    // The product date is the daily composite date, not the satellite pass -
    // see docs/spec.md section 7.
    metaLine.title = meta.product;

    const zoom = document.createElement("button");
    zoom.type = "button";
    zoom.className = "snow-ctrl__zoom";
    zoom.textContent = "Zoom to data";
    zoom.addEventListener("click", () => {
      map.fitBounds(this.overlay.bounds, { padding: 24 });
    });

    this.container.append(toggle, metaLine, zoom);
    return this.container;
  }

  onRemove(): void {
    this.container.remove();
  }
}
