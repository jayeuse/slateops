import { expect, test } from "@playwright/test";

import { focusSoon } from "../../../src/components/systems/openview/domain/focus-soon";

// The record sheet moves focus after a state change: Edit focuses the first
// field of the form, also when Edit is pressed on another tab (UF-C2.1). The
// form can take more than one frame to render on a busy device, so the focus
// waits for its target for a few frames instead of giving up after one.

function frames() {
  const queue: (() => void)[] = [];
  return {
    schedule: (run: () => void) => queue.push(run),
    /** Runs one frame; false when nothing was scheduled. */
    next: () => {
      const run = queue.shift();
      run?.();
      return run !== undefined;
    },
  };
}

test("UF-C2.1 focus waits for a target that renders a few frames later", () => {
  const clock = frames();
  let rendered = false;
  let focused = 0;
  const target = { focus: () => (focused += 1) };
  focusSoon(() => (rendered ? target : null), clock.schedule);
  expect(clock.next()).toBe(true); // frame 1: not rendered yet
  expect(clock.next()).toBe(true); // frame 2: not rendered yet
  rendered = true;
  expect(clock.next()).toBe(true); // frame 3: rendered
  expect(focused).toBe(1);
  expect(clock.next()).toBe(false); // focused once, nothing left
});

test("UF-C2.1 focus on a target that is there at the first frame happens once", () => {
  const clock = frames();
  let focused = 0;
  focusSoon(() => ({ focus: () => (focused += 1) }), clock.schedule);
  expect(clock.next()).toBe(true);
  expect(focused).toBe(1);
  expect(clock.next()).toBe(false);
});

test("UF-C2.1 focus gives up when the target never renders", () => {
  const clock = frames();
  focusSoon(() => null, clock.schedule);
  let ran = 0;
  while (clock.next()) ran += 1;
  expect(ran).toBeGreaterThan(1);
  expect(ran).toBeLessThanOrEqual(30);
});
