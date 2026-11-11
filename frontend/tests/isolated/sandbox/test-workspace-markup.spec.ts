import { expect, test } from "@playwright/test";

import { TestValueRow } from "../../../src/components/systems/sandbox/components/test-setup-rows";
import { TestWorkspace } from "../../../src/components/systems/sandbox/components/test-workspace";
import type { SandboxDocumentDesign } from "../../../src/components/systems/sandbox/domain/document";
import { staticMarkup } from "./static-markup";
import { field, ordersDesign } from "./test-section-design";

// The Test screen's own words and states, rendered (Product Designer PR1
// screen review F7, F10, F13; docs/specs/sandbox-ux-redesign.md E7).

function workspace(design: SandboxDocumentDesign) {
  return staticMarkup(TestWorkspace, {
    design,
    triggers: [],
    runs: [],
    total: 0,
    onRun: () => Promise.reject(new Error("no run in a markup test")),
    onClear: () => Promise.resolve(),
    draftRevision: 1,
    onShowOnCanvas: () => undefined,
    administrator: null,
    bindings: null,
    waitReason: null,
    review: { reason: null, disabled: true, open: () => undefined },
    onOpenBuild: () => undefined,
  });
}

test("with no module, the Modules pane says so and shows no search", () => {
  const html = workspace({
    departments: [],
    modules: [],
    relationships: [],
    layout: {},
  });
  expect(html).toContain("No modules yet");
  expect(html).not.toContain("Search modules");
});

test("the Modules search is named by its placeholder and label, with no visible label", () => {
  const html = workspace(ordersDesign());
  expect(html).toContain('aria-label="Search modules"');
  expect(html).toContain('placeholder="Search modules"');
  expect(html).not.toMatch(/<label[^>]*>[^<]*Search modules/);
});

test("Change values names a Checkbox value Checked or Unchecked, as Values used does", () => {
  const html = staticMarkup(TestValueRow, {
    field: field("paid", "Paid", { kind: "checkbox", defaultValue: false }),
    value: false,
    error: undefined,
    onChange: () => undefined,
  });
  expect(html).toContain(">Checked</option>");
  expect(html).toContain(">Unchecked</option>");
  expect(html).not.toContain(">Yes</option>");
});
