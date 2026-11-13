type Focusable = { focus: () => void };

/** How many frames a focus waits for its target to render. */
const FRAMES = 20;

/**
 * Focuses after React renders the next state. The target can take more than
 * one frame to render (a form on another tab, a busy device), so the focus
 * waits for it for a few frames and then gives up.
 */
export function focusSoon(
  find: () => Focusable | null | undefined,
  schedule: (run: () => void) => unknown = (run) => requestAnimationFrame(run),
  frames = FRAMES,
) {
  schedule(() => {
    const target = find();
    if (target) target.focus();
    else if (frames > 1) focusSoon(find, schedule, frames - 1);
  });
}
