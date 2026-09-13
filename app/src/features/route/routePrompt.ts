/**
 * The thin strip that says a route is half-planned (spec section 8.2).
 *
 * Picking two endpoints needs the object panel - that is the surface that
 * resolves a tap to a real index record, handles an ambiguous tap, and says
 * when nothing is there. So the route sheet cannot be open during picking, or
 * the two would fight for the bottom of a phone screen, and the user would
 * still have no way to see the half-finished plan.
 *
 * Hence a strip rather than a second sheet: it sits under the search bar, out
 * of the way of both the object panel and the bottom-left snow control, states
 * which endpoint is already chosen and which is still needed, and offers the
 * one action that must always be reachable - cancel. It deliberately does not
 * register with `map/bottomSheet.ts`: it is anchored at the top and covers no
 * control.
 *
 * Plain DOM, `textContent` only - an endpoint name comes from the OSM index.
 */

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export class RoutePrompt {
  readonly element: HTMLElement;

  private readonly message: HTMLElement;
  private onCancel: (() => void) | null = null;

  constructor() {
    this.element = element("div", "route-prompt");
    this.element.hidden = true;
    this.element.setAttribute("aria-live", "polite");

    this.message = element("span", "route-prompt__message");
    const cancel = element("button", "route-prompt__cancel", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", () => this.onCancel?.());

    this.element.append(this.message, cancel);
  }

  setCancelHandler(handler: () => void): void {
    this.onCancel = handler;
  }

  /**
   * `chosen` is the endpoint already picked and `needed` is the one still
   * missing, both as user-facing words: the message has to tell someone who
   * put the phone away mid-plan what they were doing.
   */
  show(chosen: string, needed: "start" | "destination"): void {
    const wanted = needed === "start" ? "starting point" : "destination";
    this.message.textContent = `${chosen} is set. Now tap or search for the ${wanted}.`;
    this.element.hidden = false;
  }

  hide(): void {
    this.element.hidden = true;
  }
}
