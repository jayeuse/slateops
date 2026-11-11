import { expect, test } from "@playwright/test";

import {
  addElement,
  emptyCreateDraft,
} from "../../../src/components/systems/sandbox/domain/create-checks";
import {
  setupAccessibleName,
  setupClearedCount,
  setupOffered,
  withSetupItem,
} from "../../../src/components/systems/sandbox/domain/department-setup";
import type { Design } from "../../../src/components/systems/sandbox/domain/model";
import {
  mergeTemplateDepartment,
  templateDepartmentGroups,
} from "../../../src/components/systems/sandbox/domain/template-merge";
import { duplicateDesignTarget } from "../../../src/components/systems/sandbox/helpers/designer-duplication";

// Setup choices (docs/specs/sandbox-ux-redesign.md, "Setup choices"; FIT-1,
// FIT-3; plan section 11.3): which departments offer them, how the closed
// control counts what is cleared, and how a toggle edits the draft value.

function salesAndFinance(): Design {
  return {
    departments: [
      { id: "sales", name: "Sales", closed: false },
      {
        id: "finance",
        name: "Finance",
        closed: false,
        setup: {
          groups: true,
          dashboard: true,
          category: true,
          channel: false,
        },
      },
    ],
    modules: [],
    relationships: [],
    rules: [],
  };
}

// UX-C29 (R1.4, plan 11.3 "Count"): the four values count, Groups as one; a
// missing value means all on.
test("the closed control counts cleared items, with Groups as one item", () => {
  const all = { groups: true, dashboard: true, category: true, channel: true };
  const rows: Array<[string, Parameters<typeof setupClearedCount>[0], number]> =
    [
      ["no setup value", undefined, 0],
      ["all on", all, 0],
      ["channel cleared", { ...all, channel: false }, 1],
      ["groups cleared (three groups)", { ...all, groups: false }, 1],
      [
        "everything cleared",
        { groups: false, dashboard: false, category: false, channel: false },
        4,
      ],
    ];
  for (const [label, setup, expected] of rows)
    expect(setupClearedCount(setup), label).toBe(expected);
});

// FIND-3 words: the accessible name names the department and what is cleared.
test("the control's accessible name names the department and the cleared count", () => {
  const all = { groups: true, dashboard: true, category: true, channel: true };
  expect(setupAccessibleName("Field service", undefined)).toBe(
    "Setup for Field service",
  );
  expect(setupAccessibleName("Field service", { ...all, channel: false })).toBe(
    "Setup for Field service: 1 item cleared",
  );
  expect(
    setupAccessibleName("Field service", {
      ...all,
      channel: false,
      dashboard: false,
    }),
  ).toBe("Setup for Field service: 2 items cleared");
});

// FIT-1: only a department with no live binding offers Setup; plan 11.3
// (and BE-SD5) apply it only to a department that is also open.
test("Setup is offered for an open department with no live binding only", () => {
  expect(setupOffered({ closed: false }, false)).toBe(true);
  expect(setupOffered({ closed: false }, true)).toBe(false);
  expect(setupOffered({ closed: true }, false)).toBe(false);
});

// FIT-3: one toggle edits one department's draft value and nothing else;
// the value it writes names all four items.
test("a toggle writes the department's whole setup value and leaves others alone", () => {
  const design = salesAndFinance();

  const cleared = withSetupItem(design, "sales", "category", false);
  expect(cleared.departments[0]?.setup).toEqual({
    groups: true,
    dashboard: true,
    category: false,
    channel: true,
  });
  expect(cleared.departments[1]).toEqual(design.departments[1]);

  const restored = withSetupItem(design, "finance", "channel", true);
  expect(restored.departments[1]?.setup).toEqual({
    groups: true,
    dashboard: true,
    category: true,
    channel: true,
  });
  expect(restored.departments[0]).toEqual(design.departments[0]);
});

// UX-C34 (FIT-4, N13): a department from the entry, a template merge, or
// Duplicate starts from the default setup. Until setup slice 5 the default
// is "all on", written as no value; Duplicate never copies the source's.
test("a new department from the entry, a template, or Duplicate starts with no setup value", () => {
  const design = salesAndFinance();

  const entry = addElement(design, "department", "legal", null, {
    ...emptyCreateDraft,
    name: "Legal",
  });
  if (!entry.ok) throw new Error(entry.reason);
  const fromEntry = entry.design.departments.find(
    (item) => item.id === "legal",
  );

  const template = templateDepartmentGroups()[0]?.departments[0];
  if (!template) throw new Error("A template department is required");
  const merged = mergeTemplateDepartment(
    design,
    template.key,
    "Template copy",
    () => crypto.randomUUID(),
  );
  if (!merged.ok) throw new Error(merged.reason);
  const fromTemplate = merged.design.departments.at(-1);

  const duplicated = duplicateDesignTarget(design, {
    kind: "department",
    id: "finance",
  });
  if (!duplicated) throw new Error("Finance could not be duplicated");
  const fromDuplicate = duplicated.design.departments.find(
    (item) => item.id === duplicated.selected,
  );

  for (const [label, department] of [
    ["entry", fromEntry],
    ["template merge", fromTemplate],
    ["Duplicate of a department with channel cleared", fromDuplicate],
  ] as const) {
    // No setup key at all: the default until setup slice 5 (BE-SD5).
    expect(Object.keys(department ?? {}).sort(), label).toEqual([
      "closed",
      "id",
      "name",
    ]);
  }
  expect(fromDuplicate?.name).toBe("Finance Copy");
});

// SD-C20 (BE-SD6, FIT-4): with the Manage default "channel: no", a
// department added by the entry, a template, or Duplicate starts with
// `setup.channel` false and the others on; Duplicate takes the default, not
// the source's value. The administrator can still turn it on before publish.
test("a new department from the entry, a template, or Duplicate starts from the Manage default", () => {
  const design = salesAndFinance();
  const channelOff = {
    groups: true,
    dashboard: true,
    category: true,
    channel: false,
  };

  const entry = addElement(
    design,
    "department",
    "legal",
    null,
    { ...emptyCreateDraft, name: "Legal" },
    channelOff,
  );
  if (!entry.ok) throw new Error(entry.reason);
  const fromEntry = entry.design.departments.find(
    (item) => item.id === "legal",
  );

  const template = templateDepartmentGroups()[0]?.departments[0];
  if (!template) throw new Error("A template department is required");
  const merged = mergeTemplateDepartment(
    design,
    template.key,
    "Template copy",
    () => crypto.randomUUID(),
    channelOff,
  );
  if (!merged.ok) throw new Error(merged.reason);
  const fromTemplate = merged.design.departments.at(-1);

  // Sales has no setup value (all on); its copy still takes the default.
  const duplicated = duplicateDesignTarget(
    design,
    { kind: "department", id: "sales" },
    channelOff,
  );
  if (!duplicated) throw new Error("Sales could not be duplicated");
  const fromDuplicate = duplicated.design.departments.find(
    (item) => item.id === duplicated.selected,
  );

  for (const [label, department] of [
    ["entry", fromEntry],
    ["template merge", fromTemplate],
    ["Duplicate of a department with every item on", fromDuplicate],
  ] as const)
    expect(department?.setup, label).toEqual({
      groups: true,
      dashboard: true,
      category: true,
      channel: false,
    });

  // Turning the channel on before publish edits only the new department.
  const legal = fromEntry!;
  const turnedOn = withSetupItem(entry.design, legal.id, "channel", true);
  expect(
    turnedOn.departments.find((item) => item.id === "legal")?.setup,
  ).toEqual({ groups: true, dashboard: true, category: true, channel: true });
  expect(turnedOn.departments[0]).toEqual(design.departments[0]);
});
