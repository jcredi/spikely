import type { CatalogueEntry } from "./dateCatalogueSchema";

/** Render an AS-OF date the way a reader in the Alps expects to see it. */
export function formatProductDate(iso: string): string {
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

type Status = "ready" | "loading" | "failed";

/**
 * The AS-OF date display, and the historical date picker when there is one
 * (spec section 5.3).
 *
 * It has always occupied this spot under the search bar as a non-interactive
 * label; it becomes a control only when the catalogue actually offers a choice.
 * With zero or one available date there is nothing to pick, so it stays a
 * label rather than becoming a picker with a single stop - a control that
 * cannot change anything is a promise the data does not keep.
 *
 * The control is a native `<input type="range">` (a slider, per the owner's
 * own suggestion), stepped over the catalogue's dates rather than continuous
 * days - every stop is a real, loadable date, so the user can never drag to a
 * gap. A calendar-grid picker was the other option on the table; a slider
 * needs far less hand-built code (a calendar needs its own popup
 * positioning, a day grid, and its own keyboard nav - all ours to write and
 * maintain with no UI framework), and the app has no date the catalogue
 * doesn't already order along one line, which a slider represents directly.
 * The trade-off: with up to 31 stops a slider stays precise enough to land on
 * any one of them; a longer history would need rethinking.
 *
 * A native range input keeps the platform's own keyboard behaviour (arrow
 * keys, Home/End, Page Up/Down) and drag/touch handling for free; only
 * `aria-valuetext` is set by hand, so a screen reader announces the actual
 * date instead of a raw step index.
 *
 * The control stays visible when a date fails to load. That is deliberate: the
 * picker is the only way back to a date that works, so hiding it on failure
 * would strand the user on a broken selection.
 */
export class SnowDateControl {
  readonly element: HTMLElement;

  private readonly label: HTMLElement;
  private readonly slider: HTMLInputElement;

  /** Catalogue entries in slider order: oldest first, latest at the top end -
   *  so dragging right moves forward in time, matching a left-to-right
   *  timeline reading. `entries` itself (as given by the catalogue, and by
   *  `setCurrent`'s lookups) stays newest-first throughout, matching every
   *  other consumer of `CatalogueEntry[]`. */
  private chronological: CatalogueEntry[] = [];
  private current: string | null = null;
  private notice = "";
  private status: Status = "ready";

  constructor(private readonly onSelect: (entry: CatalogueEntry) => void) {
    this.element = document.createElement("div");
    this.element.className = "snow-date";
    this.element.hidden = true;

    this.label = document.createElement("span");
    this.label.className = "snow-date__label";

    this.slider = document.createElement("input");
    this.slider.type = "range";
    this.slider.className = "snow-date__slider";
    this.slider.setAttribute("aria-label", "Snow observation date");

    // Update the label live while dragging/keying through, so the user sees
    // where they are before committing; commit the actual selection only on
    // `change` (drag release, or immediately for a single key press, which is
    // already "one step, one commit" - matching the old <select>'s behaviour).
    this.slider.addEventListener("input", () => this.previewSliderValue());
    this.slider.addEventListener("change", () => this.commitSliderValue());
  }

  /** The available dates, newest first. Fewer than two means no picker. */
  setCatalogue(entries: CatalogueEntry[]): void {
    this.chronological = [...entries].reverse();
    this.render();
  }

  /** The date actually on the map right now, and the manifest's own notice. */
  setCurrent(asOfDate: string | null, notice: string): void {
    this.current = asOfDate;
    this.notice = notice;
    this.status = asOfDate === null ? "failed" : "ready";
    this.render();
  }

  setLoading(): void {
    this.status = "loading";
    this.render();
  }

  private render(): void {
    const interactive = this.chronological.length > 1;
    if (!interactive && this.current === null) {
      this.element.hidden = true;
      this.element.replaceChildren();
      return;
    }
    this.element.hidden = false;
    this.element.classList.toggle("snow-date--interactive", interactive);
    this.element.classList.toggle("snow-date--loading", this.status === "loading");
    this.element.classList.toggle("snow-date--failed", this.status === "failed");
    this.element.replaceChildren(interactive ? this.buildSlider() : this.buildLabel());
  }

  private buildLabel(): HTMLElement {
    const label = document.createElement("span");
    label.className = "snow-date__label";
    label.textContent = this.current === null ? "No date" : formatProductDate(this.current);
    label.title = this.notice;
    return label;
  }

  /** Index of the current AS-OF date within `chronological`, or the latest
   *  stop when the map's date is not in the catalogue at all (a stale cache,
   *  or a publication caught mid-flight - the catalogue is still the
   *  authority on what is offered, so this never invents an extra stop for
   *  it; see the same rule the old <select> applied to its orphan option). */
  private currentIndex(): number {
    if (this.current !== null) {
      const index = this.chronological.findIndex((entry) => entry.asOfDate === this.current);
      if (index !== -1) return index;
    }
    return this.chronological.length - 1;
  }

  private labelFor(entry: CatalogueEntry): string {
    const isLatest = this.chronological[this.chronological.length - 1] === entry;
    return isLatest ? `${formatProductDate(entry.asOfDate)} (latest)` : formatProductDate(entry.asOfDate);
  }

  private buildSlider(): HTMLElement {
    const wrap = document.createElement("div");
    wrap.className = "snow-date__slider-wrap";

    const known = this.current !== null && this.chronological.some((entry) => entry.asOfDate === this.current);
    const index = this.currentIndex();
    const entry = this.chronological[index];

    this.label.textContent =
      this.current !== null && !known ? formatProductDate(this.current) : this.labelFor(entry);
    this.label.title =
      this.status === "failed"
        ? "That date could not be loaded. Drag the slider to choose another."
        : this.notice;

    this.slider.min = "0";
    this.slider.max = String(Math.max(this.chronological.length - 1, 0));
    this.slider.step = "1";
    this.slider.value = String(index);
    this.slider.disabled = this.status === "loading";
    this.slider.setAttribute("aria-valuetext", this.labelFor(entry));
    this.slider.title = this.label.title;

    wrap.append(this.label, this.slider);
    return wrap;
  }

  private entryAtSlider(): CatalogueEntry | undefined {
    const index = Number(this.slider.value);
    return this.chronological[index];
  }

  private previewSliderValue(): void {
    const entry = this.entryAtSlider();
    if (!entry) return;
    this.label.textContent = this.labelFor(entry);
    this.slider.setAttribute("aria-valuetext", this.labelFor(entry));
  }

  private commitSliderValue(): void {
    const entry = this.entryAtSlider();
    if (entry) this.onSelect(entry);
  }
}
