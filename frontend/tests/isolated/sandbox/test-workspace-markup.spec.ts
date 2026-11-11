import { expect, test } from "@playwright/test";

import { TestEventBlock } from "../../../src/components/systems/sandbox/components/test-event-rows";
import { TestValueRow } from "../../../src/components/systems/sandbox/components/test-setup-rows";
import { TestWorkspace } from "../../../src/components/systems/sandbox/components/test-workspace";
import type { SandboxDocumentDesign } from "../../../src/components/systems/sandbox/domain/document";
import { staticMarkup } from "./static-markup";
import { TestResultCardHarness } from "./test-result-harness";
import { field, ordersDesign } from "./test-section-design";

// The Test screen's own words and states, rendered (Product Designer PR1
// screen review F7, F10, F13; docs/specs/sandbox-ux-redesign.md E7).

function workspace(
  design: SandboxDocumentDesign,
  overrides: Partial<Parameters<typeof TestWorkspace>[0]> = {},
) {
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
    ...overrides,
  });
}

/** Whether the button named `label` wears the action ink (`text-primary`). */
function actionInk(html: string, label: string) {
  const button = html.match(
    new RegExp(`<button([^>]*)>(?:(?!</button>)[\\s\\S])*${label}`),
  );
  expect(button, `a "${label}" button`).not.toBeNull();
  return /\btext-primary(?![-\w])/.test(button![1]!);
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
  // E7 and the test-empty comp: the reading says what to do next.
  expect(html).toContain("Nothing to test yet");
  expect(html).toContain("Add a module in Build to see what it does.");
  expect(html).toContain(">Open Build<");
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

// F15 (PR1 Product Designer finding)
test("a field whose settings allow no value is named once, by its error under the field", () => {
  const stage = field(
    "stage",
    "Stage",
    { kind: "select", defaultValue: null, options: [] },
    true,
  );
  const design = ordersDesign([stage]);
  const fields = design.modules[0]!.fields;
  const html = staticMarkup(TestResultCardHarness, {
    design,
    triggers: [],
    draftRevision: 1,
    administrator: null,
    run: null,
    title: "Example item",
    fields,
    values: { amount: 1, status: "open", paid: false, stage: null },
    startValues: { amount: 1, status: "open", paid: false, stage: null },
    setFieldIds: [],
    before: null,
    needed: [{ fieldId: "stage", name: "Stage" }],
    notes: [],
    onlyTrigger: false,
    triggerChoices: null,
    checkedTriggerIds: [],
    editing: true,
    runNumber: null,
    running: false,
    runDisabledReason: null,
    idPrefix: "result",
    onEdit: () => undefined,
    onValue: () => undefined,
    onCheckTrigger: () => undefined,
    onRunAgain: () => undefined,
    onShowOnCanvas: () => undefined,
  });
  expect(
    html.split("Its settings allow no value. Enter one to run.").length - 1,
  ).toBe(1);
  expect(html).not.toContain("needs a value before this runs");
});

// F16 (PR1 Product Designer finding)
test("Try this trigger takes the action ink only while it can run", () => {
  // The ink is the contract here: a disabled control in action ink reads as
  // live in dark, while "Try it" beside it fades to the plain ink.
  const tryThisTrigger = (state: {
    disabledReason: string | null;
    busy: boolean;
  }) => {
    const html = staticMarkup(TestEventBlock, {
      block: {
        key: "added",
        title: "When an item is added",
        event: { kind: "record-created" },
        triggers: [
          {
            id: "flag",
            name: "Flag large orders",
            enabled: true,
            conditions: "always",
            sets: [],
            attention: null,
          },
        ],
      },
      ...state,
      runningKey: null,
      onTry: () => undefined,
      onTryTrigger: () => undefined,
    });
    return actionInk(html, "Try this trigger");
  };
  expect(tryThisTrigger({ disabledReason: null, busy: false })).toBe(true);
  // Another run or a clear is in flight.
  expect(tryThisTrigger({ disabledReason: null, busy: true })).toBe(false);
  // Runs are refused, with the reason DisabledReason keeps.
  expect(
    tryThisTrigger({ disabledReason: "Clear results first.", busy: false }),
  ).toBe(false);
});

// F16 (PR1 Product Designer finding, same class)
test("Change values, Clear results and Open review take the action ink only while they can act", () => {
  const card = (running: boolean) => {
    const design = ordersDesign();
    return staticMarkup(TestResultCardHarness, {
      design,
      triggers: [],
      draftRevision: 1,
      administrator: null,
      run: null,
      title: "Example item",
      fields: design.modules[0]!.fields,
      values: {},
      startValues: {},
      setFieldIds: [],
      before: null,
      needed: [],
      notes: [],
      onlyTrigger: false,
      triggerChoices: null,
      checkedTriggerIds: [],
      editing: false,
      runNumber: null,
      running,
      runDisabledReason: null,
      idPrefix: "result",
      onEdit: () => undefined,
      onValue: () => undefined,
      onCheckTrigger: () => undefined,
      onRunAgain: () => undefined,
      onShowOnCanvas: () => undefined,
    });
  };
  // Sales has no live binding, so its module shows Open review (E6).
  const newDepartment = { bindings: [] };
  const rows: Array<[string, string, string, boolean]> = [
    ["Change values", "can act", card(false), true],
    ["Change values", "while the run runs", card(true), false],
    [
      "Clear results",
      "with kept results",
      workspace(ordersDesign(), { total: 3 }),
      true,
    ],
    [
      "Clear results",
      "with nothing to clear",
      workspace(ordersDesign()),
      false,
    ],
    [
      "Open review",
      "can act",
      workspace(ordersDesign(), {
        ...newDepartment,
        review: { reason: null, disabled: false, open: () => undefined },
      }),
      true,
    ],
    [
      "Open review",
      "refused with a reason",
      workspace(ordersDesign(), {
        ...newDepartment,
        review: {
          reason: "Nothing to publish yet.",
          disabled: true,
          open: () => undefined,
        },
      }),
      false,
    ],
  ];
  for (const [label, state, html, inked] of rows)
    expect(actionInk(html, label), `${label} ${state}`).toBe(inked);
  // DisabledReason keeps the refused review's reason.
  expect(rows[5]![2]).toContain("Nothing to publish yet.");
});
