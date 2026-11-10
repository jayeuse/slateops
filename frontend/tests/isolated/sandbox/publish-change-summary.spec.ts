import { expect, test } from "@playwright/test";

import {
  PublishChangeGroups,
  groupPublicationChanges,
  publicationChangeSummary,
  publicationFieldKey,
  type PublishReviewDesign,
} from "../../../src/components/systems/sandbox/components/publish-change-groups";
import type { SandboxPublicationChange } from "../../../src/components/systems/sandbox/state/api";
import { staticMarkup } from "./static-markup";

const changes = (
  count: number,
  kind: "department" | "module" | "field" | "trigger",
  action: "create" | "update" | "close" | "reopen",
) =>
  Array.from(
    { length: count },
    (_, index) =>
      ({ kind, action, sandboxId: `${kind}-${index}`, label: kind }) as const,
  );

// The review says what changes in plain words (F11): a count per kind, and
// the shared action only when it says more than "changes".
test("a review summary counts the changes of each kind", () => {
  expect(publicationChangeSummary(changes(7, "trigger", "update"))).toBe(
    "7 trigger changes",
  );
  expect(
    publicationChangeSummary([
      ...changes(3, "module", "update"),
      ...changes(7, "trigger", "update"),
    ]),
  ).toBe("3 module changes · 7 trigger changes");
  expect(
    publicationChangeSummary([
      ...changes(1, "department", "create"),
      ...changes(1, "module", "update"),
    ]),
  ).toBe("1 department change · 1 module change");
  // Every change shares one action, so the rows drop their chips and the
  // summary says it once.
  expect(
    publicationChangeSummary([
      ...changes(1, "department", "create"),
      ...changes(2, "module", "create"),
    ]),
  ).toBe("1 new department · 2 new modules");
  expect(publicationChangeSummary(changes(2, "field", "close"))).toBe(
    "2 closed fields",
  );
});

test("the review nests field changes under their module and puts unplaced changes under Other", () => {
  const department = {
    kind: "department",
    action: "create",
    sandboxId: "team-1",
    label: "Team 1",
  } as const;
  const title = {
    kind: "field",
    action: "create",
    sandboxId: publicationFieldKey("requests", "title"),
    label: "Title",
  } as const;
  const requests = {
    kind: "module",
    action: "create",
    sandboxId: "requests",
    label: "Service requests",
  } as const;
  const assetTag = {
    kind: "field",
    action: "update",
    sandboxId: publicationFieldKey("equipment", "asset-tag"),
    label: "Asset tag",
  } as const;
  const removedFromDraft = {
    kind: "field",
    action: "update",
    sandboxId: publicationFieldKey("requests", "removed"),
    label: "Removed field",
  } as const;
  const retired = {
    kind: "field",
    action: "close",
    sandboxId: "retired-field",
    label: "Old notes",
  } as const;
  const relationship = {
    kind: "relationship",
    action: "create",
    sandboxId: "uses",
    label: "Uses equipment",
  } as const;
  const trigger = {
    kind: "trigger",
    action: "update",
    sandboxId: "urgent",
    label: "Urgent alert",
  } as const;
  expect(
    groupPublicationChanges(
      [
        department,
        title,
        requests,
        assetTag,
        removedFromDraft,
        retired,
        relationship,
        trigger,
      ],
      {
        departments: [],
        modules: [
          {
            id: "requests",
            departmentId: "team-1",
            name: "Service requests",
            closed: false,
            fields: [{ id: "title" }],
          },
          {
            id: "equipment",
            departmentId: "team-1",
            name: "Equipment",
            closed: false,
            fields: [{ id: "asset-tag" }],
          },
        ],
      },
    ),
  ).toEqual({
    departments: [
      { id: "team-1", name: "Team 1", change: department, setup: [] },
    ],
    modules: [
      {
        id: "requests",
        name: "Service requests",
        change: requests,
        fields: [title],
      },
      { id: "equipment", name: "Equipment", fields: [assetTag] },
    ],
    relationships: [relationship],
    triggers: [trigger],
    other: [removedFromDraft, retired],
  });
});

type Change = SandboxPublicationChange;
type Action = Change["action"];

/** The setup items a publish derives for one department, in R2 order. */
function setupChanges(id: string, name: string, action: Action): Change[] {
  return [
    {
      kind: "group",
      action,
      sandboxId: `${id}#managers`,
      label: `${name} managers · manage`,
    },
    {
      kind: "group",
      action,
      sandboxId: `${id}#members`,
      label: `${name} members · write`,
    },
    {
      kind: "group",
      action,
      sandboxId: `${id}#viewers`,
      label: `${name} viewers · read`,
    },
    {
      kind: "dashboard",
      action,
      sandboxId: `${id}#dashboard`,
      label: `${name} dashboard`,
    },
    { kind: "board", action, sandboxId: `${id}#board`, label: name },
    { kind: "category", action, sandboxId: `${id}#category`, label: name },
    { kind: "channel", action, sandboxId: `${id}#channel`, label: name },
  ];
}

const salesSetupRows = [
  "Group Sales managers · manage",
  "Group Sales members · write",
  "Group Sales viewers · read",
  "Dashboard Sales dashboard",
  "Board Sales",
  "Category Sales",
  "Channel Sales",
];

function reviewDesign(
  departments: PublishReviewDesign["departments"],
  modules: PublishReviewDesign["modules"] = [],
): PublishReviewDesign {
  return { departments, modules };
}

const salesOpen = reviewDesign([{ id: "sales", name: "Sales", closed: false }]);

function text(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", '"')
    .replaceAll("&#x27;", "'")
    .replace(/\s+/g, " ")
    .trim();
}

/** Each row of the "Setup for <name>" list, as its visible text. */
function setupRows(html: string, name: string): string[] {
  const start = html.indexOf(`aria-label="Setup for ${name}"`);
  if (start < 0) return [];
  const list = html.slice(start, html.indexOf("</ul>", start));
  return list
    .split("<li")
    .slice(1)
    .map((row) => text(`<li${row}`));
}

function review(changes: Change[], design: PublishReviewDesign): string {
  return staticMarkup(PublishChangeGroups, { changes, design });
}

// S1 and SD-C1 (contributor): the summary counts each setup kind, so it
// matches the preview `counts`.
test("a review summary counts each kind of department setup", () => {
  const sales = {
    kind: "department",
    action: "create",
    sandboxId: "sales",
    label: "Sales",
  } as const;
  expect(
    publicationChangeSummary([
      sales,
      ...setupChanges("sales", "Sales", "create"),
      ...changes(2, "module", "create"),
    ]),
  ).toBe(
    "1 new department · 3 new groups · 1 new dashboard · 1 new Board · 1 new category · 1 new channel · 2 new modules",
  );
  expect(
    publicationChangeSummary([
      sales,
      ...setupChanges("sales", "Sales", "create"),
      ...changes(1, "trigger", "update"),
    ]),
  ).toBe(
    "1 department change · 3 group changes · 1 dashboard change · 1 Board change · 1 category change · 1 channel change · 1 trigger change",
  );
});

// S1 and S7 (SD-C23): setup items sit under their department in R2 order,
// whatever order the server sends; a Board change of an existing department
// gets a parent without a change of its own; setup never goes to "Other".
test("the review nests setup changes under their department in a fixed order", () => {
  const sales = {
    kind: "department",
    action: "create",
    sandboxId: "sales",
    label: "Sales",
  } as const;
  const [managers, members, viewers, dashboard, board, category, channel] =
    setupChanges("sales", "Sales", "create");
  const warehouseBoard = {
    kind: "board",
    action: "update",
    sandboxId: "warehouse#board",
    label: "Warehouse",
  } as const;
  const archiveBoard = {
    kind: "board",
    action: "create",
    sandboxId: "dept#2#board",
    label: "Archive",
  } as const;
  const groups = groupPublicationChanges(
    [
      channel,
      warehouseBoard,
      board,
      sales,
      viewers,
      category,
      managers,
      dashboard,
      archiveBoard,
      members,
    ],
    reviewDesign([
      { id: "sales", name: "Sales", closed: false },
      { id: "warehouse", name: "Warehouse", closed: false },
    ]),
  );
  expect(groups.departments).toEqual([
    {
      id: "sales",
      name: "Sales",
      change: sales,
      setup: [managers, members, viewers, dashboard, board, category, channel],
    },
    { id: "warehouse", name: "Warehouse", setup: [warehouseBoard] },
    // Not in the draft: the Board's label names it, and the role follows
    // the last "#".
    { id: "dept#2", name: "Archive", setup: [archiveBoard] },
  ]);
  expect(groups.other).toEqual([]);
});

// S1: a first publish shares one action, so no row has a chip; the setup
// list is open and named, and the sidebar note sits under the new
// department that has no open module yet (SD15).
test("a new department lists its setup with the sidebar note", () => {
  const html = review(
    [
      {
        kind: "department",
        action: "create",
        sandboxId: "sales",
        label: "Sales",
      },
      ...setupChanges("sales", "Sales", "create"),
    ],
    reviewDesign(
      [{ id: "sales", name: "Sales", closed: false }],
      [
        {
          id: "old",
          departmentId: "sales",
          name: "Old",
          closed: true,
          fields: [],
        },
      ],
    ),
  );
  expect(setupRows(html, "Sales")).toEqual(salesSetupRows);
  expect(html).not.toContain('data-slot="badge"');
  expect(text(html)).toContain(
    "Sales Not in the sidebar until it has a module. Group Sales managers",
  );
});

// S2 and S3: an open module in the draft drops the sidebar note; a department
// created closed has no setup and no note.
test("the sidebar note and setup show only for an open department without modules", () => {
  const withModule = review(
    [
      {
        kind: "department",
        action: "create",
        sandboxId: "sales",
        label: "Sales",
      },
      ...setupChanges("sales", "Sales", "create"),
    ],
    reviewDesign(
      [{ id: "sales", name: "Sales", closed: false }],
      [
        {
          id: "leads",
          departmentId: "sales",
          name: "Leads",
          closed: false,
          fields: [],
        },
      ],
    ),
  );
  expect(setupRows(withModule, "Sales")).toEqual(salesSetupRows);
  expect(withModule).not.toContain("Not in the sidebar");

  const closed = review(
    [
      {
        kind: "department",
        action: "create",
        sandboxId: "sales",
        label: "Sales",
      },
    ],
    reviewDesign([{ id: "sales", name: "Sales", closed: true }]),
  );
  expect(closed).not.toContain("Setup for");
  expect(closed).not.toContain("Not in the sidebar");
  expect(text(closed)).toContain("Sales");
});

// S7 (SD-C23): a Board change of a department that has no change of its own
// shows under an "Unchanged" parent, with its own chip.
test("a Board change of an existing department shows under an unchanged parent", () => {
  const html = review(
    [
      {
        kind: "board",
        action: "update",
        sandboxId: "warehouse#board",
        label: "Warehouse",
      },
      { kind: "trigger", action: "create", sandboxId: "alert", label: "Alert" },
    ],
    reviewDesign([{ id: "warehouse", name: "Warehouse", closed: false }]),
  );
  expect(text(html)).toContain("Departments Unchanged Warehouse Changed Board");
  expect(setupRows(html, "Warehouse")).toEqual(["Changed Board Warehouse"]);
});

// S8 (SD-C9, SD-C11, SD-C12): a nested row shows its chip only when its word
// differs from its department's; the channel uses the OpenComms words.
test("setup rows of a renamed, closed, or reopened department show only differing chips", () => {
  const alert = {
    kind: "trigger",
    action: "create",
    sandboxId: "alert",
    label: "Alert",
  } as const;
  const linked = (action: Action, kinds: Change["kind"][]) =>
    review(
      [
        { kind: "department", action, sandboxId: "sales", label: "Sales" },
        ...setupChanges("sales", "Sales", action).filter((change) =>
          kinds.includes(change.kind),
        ),
        alert,
      ],
      salesOpen,
    );
  expect(
    setupRows(
      linked("update", ["group", "dashboard", "board", "category", "channel"]),
      "Sales",
    ),
  ).toEqual(salesSetupRows);
  expect(setupRows(linked("close", ["board", "channel"]), "Sales")).toEqual([
    "Board Sales",
    "Archived Channel Sales",
  ]);
  expect(setupRows(linked("reopen", ["board", "channel"]), "Sales")).toEqual([
    "Board Sales",
    "Restored Channel Sales",
  ]);
});
