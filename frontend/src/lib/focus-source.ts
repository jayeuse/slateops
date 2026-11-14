/**
 * What moved focus last: a pointer press or the keyboard. It lives on
 * `<html data-focus-source>`, and `globals.css` hides the focus mark of
 * fields while it reads "pointer" (Human Owner, 2026-11-13). Keyboard focus
 * keeps the mark. Before any input the attribute is absent, so marks show.
 */
export type FocusSource = "pointer" | "keyboard";

/** Keys that move focus or act on a control that is not a field. */
const NAVIGATION_KEYS = new Set([
  "ArrowDown",
  "ArrowUp",
  "ArrowLeft",
  "ArrowRight",
  "Home",
  "End",
  "PageUp",
  "PageDown",
  "Enter",
  " ",
]);

/**
 * The focus source a key press sets, or null when it keeps the current one.
 * `editing` is true when the key goes to a field (typing there never shows
 * the mark of a clicked field).
 */
export function focusSourceForKey(
  key: string,
  editing: boolean,
): FocusSource | null {
  if (key === "Tab" || key === "Escape") return "keyboard";
  if (!editing && NAVIGATION_KEYS.has(key)) return "keyboard";
  return null;
}

function isField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    target.isContentEditable
  );
}

/** Listens for pointer presses and key presses; returns the cleanup. */
export function trackFocusSource(root: HTMLElement): () => void {
  const set = (source: FocusSource) => {
    if (root.dataset.focusSource !== source) root.dataset.focusSource = source;
  };
  const onPointer = () => set("pointer");
  const onKey = (event: KeyboardEvent) => {
    const source = focusSourceForKey(event.key, isField(event.target));
    if (source) set(source);
  };
  document.addEventListener("pointerdown", onPointer, true);
  document.addEventListener("keydown", onKey, true);
  return () => {
    document.removeEventListener("pointerdown", onPointer, true);
    document.removeEventListener("keydown", onKey, true);
  };
}
