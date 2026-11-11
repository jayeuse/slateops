import { expect, test } from "@playwright/test";

import { SetupPopoverBody } from "../../../src/components/systems/sandbox/components/setup-popover";
import type { DepartmentSetup } from "../../../src/components/systems/sandbox/domain/model";
import { staticMarkup } from "./static-markup";

// "Created at publish", rendered (docs/specs/sandbox-ux-redesign.md, B9;
// setup spec SD13, SD14; comp build-setup-1440).

function body(setup: DepartmentSetup | undefined) {
  return staticMarkup(SetupPopoverBody, {
    name: "Field service",
    departmentIndex: 0,
    setup,
    held: false,
    onToggle: () => undefined,
    phone: false,
  });
}

function text(markup: string): string {
  return markup
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// B9, SD13: four choices, then the Board as text that cannot be cleared.
test("the popover lists four choices and the Board as always created", () => {
  const markup = body(undefined);
  expect(text(markup)).toBe(
    "Created at publish Groups · managers, members, viewers Dashboard Category Channel Board · always created",
  );
  expect(markup.match(/role="checkbox"/g)).toHaveLength(4);
  expect(markup.match(/aria-checked="true"/g)).toHaveLength(4);
});

// SD14 (UX-C29 comp B9): only a cleared Category adds the line, under it.
test("a cleared Category adds 'The channel goes in no category.' under it", () => {
  const all = { groups: true, dashboard: true, category: true, channel: true };
  expect(text(body({ ...all, channel: false }))).not.toContain(
    "The channel goes in no category.",
  );
  const cleared = text(body({ ...all, category: false }));
  expect(cleared).toContain(
    "Category The channel goes in no category. Channel",
  );
});
