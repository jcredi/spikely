/**
 * The one place that answers "how much of the bottom of the screen is covered
 * by a sheet right now".
 *
 * Nevaio has two bottom sheets - the object panel (spec section 7) and the
 * route panel (spec section 8) - and one bottom-left map control that must not
 * end up underneath either of them. That collision has been shipped twice
 * already (the search bar and the snow control, then the object panel and the
 * snow control), so the coupling is kept explicit and in a single module
 * rather than hard-coded per sheet: every open sheet registers itself here,
 * this module publishes the **largest** registered height as
 * `--bottom-sheet-height` on the document element, and `style.css` offsets the
 * snow control by that variable.
 *
 * Taking the maximum rather than the latest value matters: the two sheets are
 * mutually exclusive *by policy today* (opening a route closes the object
 * panel), and if that policy ever changes this keeps working instead of
 * quietly reverting to the older, shorter sheet's height.
 *
 * Heights are observed with a `ResizeObserver`, not measured once on open: a
 * sheet keeps growing after it is revealed - the object panel's history chart
 * arrives asynchronously - and measuring the moment instead of the element is
 * exactly what let a real chart push the panel up over the snow control on a
 * 320 px viewport.
 *
 * This lives in `map/` rather than in either feature because neither feature
 * owns it; it is the contract between them.
 */

const CSS_VARIABLE = "--bottom-sheet-height";

const heights = new Map<Element, number>();

function republish(): void {
  let tallest = 0;
  for (const height of heights.values()) tallest = Math.max(tallest, height);
  document.documentElement.style.setProperty(CSS_VARIABLE, `${Math.round(tallest)}px`);
}

/**
 * Track one sheet's laid-out height for as long as it is open.
 *
 * Call `track` when the sheet becomes visible and `release` when it is hidden;
 * a released sheet contributes nothing, which is what lets the control drop
 * back down. Both are idempotent.
 */
export class BottomSheetHeight {
  private observer: ResizeObserver | null = null;

  constructor(private readonly element: HTMLElement) {}

  track(): void {
    this.observer?.disconnect();
    this.observer = new ResizeObserver(() => this.measure());
    this.observer.observe(this.element);
    this.measure();
  }

  release(): void {
    this.observer?.disconnect();
    this.observer = null;
    heights.delete(this.element);
    republish();
  }

  private measure(): void {
    if (this.element.hidden) {
      heights.delete(this.element);
    } else {
      heights.set(this.element, this.element.getBoundingClientRect().height);
    }
    republish();
  }
}
