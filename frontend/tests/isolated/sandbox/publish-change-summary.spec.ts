import { expect, test } from "@playwright/test";

import {
  PublishChangeGroups,
  groupPublicationChanges,
  publicationChangeSummary,
  publicationFieldKey,
  type PublishReviewDesign,
} from "../../../src/components/systems/sandbox/components/publish-change-groups";
import {
  createdModules,
  publishedModuleLinks,
} from "../../../src/components/systems/sandbox/components/review-publish-dialog";
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

// UF-11.2, DR-11.1: the summary counts only what the owner drew. Department
// setup leaves the line; it shows as "Comes with" under its department.
test("UF-C11.1 a review summary counts what the owner drew, not department setup", () => {
  const sales = {
    kind: "department",
    action: "create",
    sandboxId: "sales",
    label: "Sales",
  } as const;
  const linksCustomer = {
    kind: "relationship",
    action: "create",
    sandboxId: "bills",
    label: "Bills customer",
  } as const;
  expect(
    publicationChangeSummary([
      sales,
      ...setupChanges("sales", "Sales", "create"),
      ...changes(1, "module", "create"),
      ...changes(2, "field", "create"),
      linksCustomer,
    ]),
  ).toBe("1 new department · 1 new module · 2 new fields · 1 new relationship");
  // A trigger stays on the line, so a trigger-only publish is not empty.
  expect(
    publicationChangeSummary([
      sales,
      ...setupChanges("sales", "Sales", "create"),
      ...changes(1, "trigger", "update"),
    ]),
  ).toBe("1 department change · 1 trigger change");
  // A setup change alone gives no line; its row still shows below.
  expect(
    publicationChangeSummary([
      {
        kind: "board",
        action: "update",
        sandboxId: "warehouse#board",
        label: "Warehouse",
      },
    ]),
  ).toBe("");
});

// UF-11.3, DR-11.2: one line directly under a new department's name says
// what the publish creates for it; the full setup list stays under it.
test("UF-C11.1 a new department says what comes with it, above its full setup list", () => {
  const sales = {
    kind: "department",
    action: "create",
    sandboxId: "sales",
    label: "Sales",
  } as const;
  const orders = {
    id: "orders",
    departmentId: "sales",
    name: "Orders",
    closed: false,
    fields: [{ id: "number" }, { id: "total" }],
  };
  const html = review(
    [
      sales,
      ...setupChanges("sales", "Sales", "create"),
      {
        kind: "module",
        action: "create",
        sandboxId: "orders",
        label: "Orders",
      },
      {
        kind: "field",
        action: "create",
        sandboxId: publicationFieldKey("orders", "number"),
        label: "Number",
      },
      {
        kind: "field",
        action: "create",
        sandboxId: publicationFieldKey("orders", "total"),
        label: "Total",
      },
    ],
    reviewDesign([{ id: "sales", name: "Sales", closed: false }], [orders]),
  );
  expect(text(html)).toContain(
    "1 new department · 1 new module · 2 new fields Departments Sales Comes with: 3 access groups · home dashboard · Announcements board · chat category and channel Group Sales managers",
  );
  expect(setupRows(html, "Sales")).toEqual(salesSetupRows);

  // It lists only the kinds this publish creates: here the channel is off.
  const noChannel = review(
    [
      sales,
      ...setupChanges("sales", "Sales", "create").filter(
        (change) => change.kind !== "channel",
      ),
    ],
    reviewDesign([{ id: "sales", name: "Sales", closed: false }], [orders]),
  );
  expect(text(noChannel)).toContain(
    "Sales Comes with: 3 access groups · home dashboard · Announcements board · chat category Group",
  );

  // A department that is not new says nothing comes with it.
  const renamed = review(
    [
      {
        kind: "department",
        action: "update",
        sandboxId: "sales",
        label: "Sales",
      },
      ...setupChanges("sales", "Sales", "update"),
    ],
    salesOpen,
  );
  expect(renamed).not.toContain("Comes with");
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
test("UF-C11.1 a new department lists its setup with Comes with and the sidebar note", () => {
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
    "Sales Comes with: 3 access groups · home dashboard · Announcements board · chat category and channel Not in the sidebar until it has a module. Group Sales managers",
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

// UF-11.1, DR-11.4 to DR-11.6: Published links each open module the publish
// creates to its records, by the live id that the bindings read after the
// publish names. A module with no live binding gets no link.
test("UF-C11.2 Published links each new open module by its live binding", () => {
  const design = reviewDesign(
    [
      { id: "ops", name: "Operations", closed: false },
      { id: "sales", name: "Sales", closed: false },
    ],
    [
      {
        id: "orders",
        departmentId: "sales",
        name: "Orders",
        closed: false,
        fields: [],
      },
      {
        id: "archive",
        departmentId: "sales",
        name: "Archive",
        closed: true,
        fields: [],
      },
      {
        id: "assets",
        departmentId: "ops",
        name: "Assets",
        closed: false,
        fields: [],
      },
      {
        id: "unbound",
        departmentId: "ops",
        name: "Unbound",
        closed: false,
        fields: [],
      },
    ],
  );
  const created = createdModules(
    [
      {
        kind: "module",
        action: "create",
        sandboxId: "orders",
        label: "Orders",
      },
      // Created closed: nobody opens its records.
      {
        kind: "module",
        action: "create",
        sandboxId: "archive",
        label: "Archive",
      },
      // Changed, not new.
      {
        kind: "module",
        action: "update",
        sandboxId: "assets",
        label: "Assets",
      },
      {
        kind: "module",
        action: "create",
        sandboxId: "unbound",
        label: "Unbound",
      },
      { kind: "field", action: "create", sandboxId: "orders", label: "Orders" },
    ],
    design,
  );
  expect(created).toEqual([
    {
      id: "orders",
      name: "Orders",
      departmentName: "Sales",
      departmentIndex: 1,
    },
    {
      id: "unbound",
      name: "Unbound",
      departmentName: "Operations",
      departmentIndex: 0,
    },
  ]);
  const ordersLive = "00000000-0000-4000-8000-0000000000a1";
  expect(
    publishedModuleLinks(created, [
      {
        kind: "module",
        sandbox_id: "orders",
        parent_sandbox_id: null,
        live_id: ordersLive,
        is_deleted: false,
      },
      // Another kind with the same sandbox id is not the module.
      {
        kind: "department",
        sandbox_id: "unbound",
        parent_sandbox_id: null,
        live_id: "00000000-0000-4000-8000-0000000000a2",
        is_deleted: false,
      },
    ]),
  ).toEqual([
    {
      id: "orders",
      name: "Orders",
      departmentName: "Sales",
      departmentIndex: 1,
      href: `/openview?section=views&module=${ordersLive}`,
    },
  ]);
  // A deleted live module gets no link.
  expect(
    publishedModuleLinks(created, [
      {
        kind: "module",
        sandbox_id: "orders",
        parent_sandbox_id: null,
        live_id: ordersLive,
        is_deleted: true,
      },
    ]),
  ).toEqual([]);
});
