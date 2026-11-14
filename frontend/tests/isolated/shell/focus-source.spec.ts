import { expect, test } from "@playwright/test";

import { focusSourceForKey } from "../../../src/lib/focus-source";

// Fields show their focus mark for keyboard focus only (Human Owner,
// 2026-11-13): a pointer press marks the focus source "pointer", and only a
// key that moves focus marks it "keyboard" again. Typing in a field never
// does, so a clicked field stays without a mark while the person types.

test("a key that moves focus makes the focus source keyboard", () => {
  expect(focusSourceForKey("Tab", true)).toBe("keyboard");
  expect(focusSourceForKey("Tab", false)).toBe("keyboard");
  expect(focusSourceForKey("Escape", true)).toBe("keyboard");
  for (const key of [
    "ArrowDown",
    "ArrowUp",
    "ArrowLeft",
    "ArrowRight",
    "Home",
    "End",
    "Enter",
    " ",
  ])
    expect(focusSourceForKey(key, false), key).toBe("keyboard");
});

test("typing and editing keys in a field keep the focus source", () => {
  for (const key of [
    "a",
    "Z",
    "7",
    " ",
    "Enter",
    "Backspace",
    "Delete",
    "ArrowDown",
    "ArrowLeft",
    "Home",
    "End",
    "Shift",
    "Meta",
  ])
    expect(focusSourceForKey(key, true), key).toBeNull();
  expect(focusSourceForKey("Shift", false)).toBeNull();
});
