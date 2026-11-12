import { expect, test } from "@playwright/test";

import {
  AddAccessStepError,
  alreadyHas,
  canAddAccess,
  exactFit,
  groupAccessLine,
  levelsFor,
  madeGroupName,
  planAddAccess,
  runAddAccess,
  type AddAccessCalls,
} from "../../../src/components/systems/access/helpers/add-access";
import type {
  AccessGroup,
  AccessGroupAccessEntry,
  AccessUserAccess,
} from "../../../src/components/systems/access/state/api-contracts";
import { group as groupFixture, timestamp } from "./fixtures";

// Item 10 of docs/specs/ux-friction-pass.md: the group lines in Invite and
// the rules of "Add access" in a person's Access tab.

const sales = "00000000-0000-4000-8000-0000000000d1";
const finance = "00000000-0000-4000-8000-0000000000d2";
const people = "00000000-0000-4000-8000-0000000000d3";
const ops = "00000000-0000-4000-8000-0000000000d4";
const quotes = "00000000-0000-4000-8000-0000000000e1";
const leads = "00000000-0000-4000-8000-0000000000e2";
const person = "00000000-0000-4000-8000-000000000102";
const other = "00000000-0000-4000-8000-000000000103";
const names: Record<string, string> = {
  [sales]: "Sales",
  [finance]: "Finance",
  [people]: "People",
  [ops]: "Operations",
};

type Row = [department: string, module: string | null, level: string];

function row([department, module, level]: Row) {
  return {
    department_id: department,
    module_id: module,
    level: level as AccessGroupAccessEntry["level"],
    department_name: names[department],
    module_name:
      module === quotes ? "Quotes" : module === leads ? "Leads" : null,
  };
}

function group(
  index: number,
  name: string,
  rows: Row[],
  members: string[] = [],
): AccessGroup {
  return {
    ...groupFixture,
    id: `00000000-0000-4000-8000-0000000000${String(index).padStart(2, "0")}`,
    name,
    member_ids: members,
    access: rows.map(row),
  } as AccessGroup;
}

test("UF-C10.1 a group line says what the group gives, with differing modules, more departments, no access and the guest limit", () => {
  const cases: [string, Row[], "member" | "guest", string][] = [
    ["one department", [[sales, null, "write"]], "member", "Sales · Write"],
    [
      "two departments, by name",
      [
        [sales, null, "write"],
        [finance, null, "read"],
      ],
      "member",
      "Finance · Read, Sales · Write",
    ],
    [
      "four departments",
      [
        [sales, null, "write"],
        [finance, null, "read"],
        [people, null, "read"],
        [ops, null, "manage"],
      ],
      "member",
      "Finance · Read, Operations · Manage +2 more",
    ],
    [
      "two modules differ",
      [
        [sales, null, "write"],
        [sales, quotes, "read"],
        [sales, leads, "manage"],
      ],
      "member",
      "Sales · Write (2 modules differ)",
    ],
    [
      "one module differs",
      [
        [sales, null, "write"],
        [sales, quotes, "read"],
      ],
      "member",
      "Sales · Write (1 module differs)",
    ],
    [
      "a module row at the department level does not differ",
      [
        [sales, null, "write"],
        [sales, quotes, "write"],
      ],
      "member",
      "Sales · Write",
    ],
    [
      "only module rows",
      [[sales, quotes, "read"]],
      "member",
      "Sales · 1 module",
    ],
    ["no access rows", [], "member", "Gives no access yet"],
    [
      "guest: a level above Read",
      [[sales, null, "write"]],
      "guest",
      "Sales · Read (guest limit)",
    ],
    [
      "guest: Read stays Read",
      [[finance, null, "read"]],
      "guest",
      "Finance · Read",
    ],
    [
      "guest: capped modules no longer differ",
      [
        [sales, null, "write"],
        [sales, quotes, "manage"],
      ],
      "guest",
      "Sales · Read (guest limit)",
    ],
  ];
  for (const [label, rows, role, expected] of cases)
    expect(groupAccessLine(rows.map(row), role), label).toBe(expected);
});

test("UF-C10.2 a group gives exactly this only with one whole-department row at that level, and the earliest name wins", () => {
  const groups = [
    group(1, "Sales Desk", [[finance, null, "read"]]),
    group(2, "Finance Review", [[finance, null, "read"]]),
    group(3, "Finance and Sales", [
      [finance, null, "read"],
      [sales, null, "read"],
    ]),
    group(4, "Accounts", [[finance, quotes, "read"]]),
    group(5, "Aardvark", [[finance, null, "write"]]),
    {
      ...group(6, "Aaa archived", [[finance, null, "read"]]),
      is_deleted: true,
    },
  ];
  expect(exactFit(groups, finance, "read")?.name).toBe("Finance Review");
  expect(exactFit(groups, finance, "manage")).toBeNull();
  expect(
    planAddAccess({
      groups,
      departmentId: finance,
      departmentName: "Finance",
      level: "read",
    }),
  ).toEqual({ kind: "join", group: groups[1] });
});

test("UF-C10.3 a made group is named for its department and level, never a Sandbox derived name, and a taken name moves to 2, then 3", () => {
  expect(madeGroupName("Finance", "read")).toBe("Finance read access");
  expect(madeGroupName("Finance", "write")).toBe("Finance write access");
  expect(madeGroupName("Finance", "manage")).toBe("Finance manage access");
  expect(madeGroupName("Finance", "read", 3)).toBe("Finance read access 3");
  // The Sandbox derives "<Department> managers", "members" and "viewers"
  // (backend/app/systems/sandbox/derived/actions.py); here none of them
  // gives exactly the chosen level, so a group is made.
  const derived = [
    group(1, "Finance managers", [[finance, quotes, "manage"]], [other]),
    group(2, "Finance members", [[finance, quotes, "write"]], [other]),
    group(3, "Finance viewers", [[finance, quotes, "read"]], [other]),
  ];
  for (const level of ["read", "write", "manage"] as const) {
    const plan = planAddAccess({
      groups: derived,
      departmentId: finance,
      departmentName: "Finance",
      level,
    });
    expect(plan).toEqual({
      kind: "make",
      name: `Finance ${level} access`,
    });
  }
  const taken = [
    group(1, "Finance read access", [[sales, null, "read"]]),
    group(2, "finance read access 2", [
      [finance, null, "read"],
      [sales, null, "read"],
    ]),
  ];
  expect(
    planAddAccess({
      groups: taken,
      departmentId: finance,
      departmentName: "Finance",
      level: "read",
    }),
  ).toEqual({ kind: "make", name: "Finance read access 3" });
});

test("UF-C10.4 a guest is offered Read only", () => {
  expect(levelsFor("guest")).toEqual(["read"]);
  expect(levelsFor("member")).toEqual(["read", "write", "manage"]);
});

test("P3F3-1 Add access shows only to an administrator viewing a person who is not an administrator", () => {
  const member = { role: "member", is_deleted: false } as const;
  expect(canAddAccess({ role: "admin" }, member)).toBe(true);
  expect(
    canAddAccess({ role: "admin" }, { role: "guest", is_deleted: false }),
  ).toBe(true);
  expect(
    canAddAccess({ role: "admin" }, { role: "admin", is_deleted: false }),
  ).toBe(false);
  expect(canAddAccess({ role: "admin" }, { ...member, is_deleted: true })).toBe(
    false,
  );
  // A department manager is a member with Manage; the role decides.
  expect(canAddAccess({ role: "member" }, member)).toBe(false);
  expect(canAddAccess({ role: "guest" }, member)).toBe(false);
  expect(canAddAccess(undefined, member)).toBe(false);
});

test("UF-C10.6 a retry uses the made group: it joins it once it gives exactly this, reuses its name with no access and no members, and never a same-name group with members", () => {
  const target = {
    departmentId: finance,
    departmentName: "Finance",
    level: "read" as const,
  };
  // The access step failed after the create: the made group is empty.
  const empty = group(9, "Finance read access", []);
  expect(planAddAccess({ ...target, groups: [empty] })).toEqual({
    kind: "reuse",
    group: empty,
  });
  // The member step failed: the made group gives exactly this now.
  const made = group(9, "Finance read access", [[finance, null, "read"]]);
  expect(planAddAccess({ ...target, groups: [made] })).toEqual({
    kind: "join",
    group: made,
  });
  // Same name, no access, but people in it: someone else's group.
  const peopled = group(8, "Finance read access", [], [other]);
  expect(planAddAccess({ ...target, groups: [peopled] })).toEqual({
    kind: "make",
    name: "Finance read access 2",
  });
  const second = { ...empty, name: "Finance read access 2" };
  expect(planAddAccess({ ...target, groups: [peopled, second] })).toEqual({
    kind: "reuse",
    group: second,
  });
});

test("DR-10.6 the person already has that level or more in the whole department, from the group that gives the most", () => {
  const access: AccessUserAccess = {
    user_id: person,
    role: "member",
    unrestricted: false,
    entries: [
      {
        department_id: finance,
        module_id: null,
        level: "write",
        groups: [
          { group_id: groupFixture.id, name: "Finance readers", level: "read" },
          { group_id: groupFixture.id, name: "Sales Desk", level: "write" },
        ],
      },
      { department_id: sales, module_id: quotes, level: "manage", groups: [] },
    ],
  };
  expect(alreadyHas(access, finance, "read")).toEqual({
    level: "write",
    groupName: "Sales Desk",
  });
  expect(alreadyHas(access, finance, "write")?.level).toBe("write");
  expect(alreadyHas(access, finance, "manage")).toBeNull();
  // A module row is not the whole department.
  expect(alreadyHas(access, sales, "read")).toBeNull();
});

function recordedCalls(
  groups: AccessGroup[][],
  fail?: { at: "create" | "access" | "member"; error: unknown },
) {
  const log: string[] = [];
  const versioned = (data: AccessGroup) => ({
    data,
    etag: `"${data.id}:${data.revision}"`,
  });
  const made = group(9, "", []);
  const calls: AddAccessCalls = {
    listGroups: async (offset) => {
      log.push(`list ${offset}`);
      const index = offset === 0 ? 0 : 1;
      const items = groups[index] ?? [];
      return {
        items,
        pagination: {
          limit: 100,
          offset,
          count: items.length,
          total: groups.flat().length,
          has_more: index + 1 < groups.length,
          total_is_capped: false,
        },
      };
    },
    createGroup: async (name) => {
      log.push(`create ${name}`);
      if (fail?.at === "create") throw fail.error;
      return versioned({ ...made, name, created_at: timestamp });
    },
    getGroup: async (id) => {
      log.push(`get ${id}`);
      return versioned(groups.flat().find((item) => item.id === id)!);
    },
    setAccess: async (id, access, etag) => {
      log.push(`access ${id} ${etag} ${JSON.stringify(access)}`);
      if (fail?.at === "access") throw fail.error;
      return versioned({ ...made, id, revision: 2 });
    },
    addMember: async (id) => {
      log.push(`member ${id}`);
      if (fail?.at === "member") throw fail.error;
    },
  };
  return { log, calls };
}

test("P3F3-2 Add access reads every page of groups, then joins the exact fit, or creates, sets one access row, and adds the person, in that order", async () => {
  const target = {
    departmentId: finance,
    departmentName: "Finance",
    level: "read" as const,
  };
  const fit = group(2, "Finance Review", [[finance, null, "read"]]);
  const first = [group(1, "Accounts", [[sales, null, "read"]])];
  let run = recordedCalls([first, [fit]]);
  await expect(runAddAccess(target, run.calls)).resolves.toEqual({
    groupName: "Finance Review",
    plan: "join",
  });
  expect(run.log).toEqual(["list 0", "list 1", `member ${fit.id}`]);

  run = recordedCalls([first]);
  await expect(runAddAccess(target, run.calls)).resolves.toEqual({
    groupName: "Finance read access",
    plan: "make",
  });
  const madeId = group(9, "", []).id;
  expect(run.log).toEqual([
    "list 0",
    "create Finance read access",
    `access ${madeId} "${madeId}:${groupFixture.revision}" [{"department_id":"${finance}","module_id":null,"level":"read"}]`,
    `member ${madeId}`,
  ]);

  // A reused group is read first for its ETag.
  const empty = group(7, "Finance read access", []);
  run = recordedCalls([[empty]]);
  await runAddAccess(target, run.calls);
  expect(run.log).toEqual([
    "list 0",
    `get ${empty.id}`,
    `access ${empty.id} "${empty.id}:${groupFixture.revision}" [{"department_id":"${finance}","module_id":null,"level":"read"}]`,
    `member ${empty.id}`,
  ]);
});

test("UF-C10.6 a failure after the create names the made group; a failed create or join names none", async () => {
  const target = {
    departmentId: finance,
    departmentName: "Finance",
    level: "read" as const,
  };
  const refused = new Error("refused");
  for (const [at, made] of [
    ["create", null],
    ["access", "Finance read access"],
    ["member", "Finance read access"],
  ] as const) {
    const run = recordedCalls([[]], { at, error: refused });
    const caught = await runAddAccess(target, run.calls).catch(
      (error) => error,
    );
    expect(caught, at).toBeInstanceOf(AddAccessStepError);
    expect((caught as AddAccessStepError).step).toBe(at);
    expect((caught as AddAccessStepError).made).toBe(made);
    expect((caught as AddAccessStepError).failure).toBe(refused);
  }
  const fit = group(2, "Finance Review", [[finance, null, "read"]]);
  const run = recordedCalls([[fit]], { at: "member", error: refused });
  const caught = await runAddAccess(target, run.calls).catch((error) => error);
  expect((caught as AddAccessStepError).made).toBeNull();
});

test("P3F3-9 a run whose fresh plan differs from the shown one stops before any write and returns the fresh groups", async () => {
  const target = {
    departmentId: finance,
    departmentName: "Finance",
    level: "read" as const,
  };
  const fit = group(2, "Finance Review", [[finance, null, "read"]]);
  const shown = planAddAccess({ ...target, groups: [fit] });
  // Someone gave Finance Review more access after the line was shown.
  const changed = group(2, "Finance Review", [[finance, null, "write"]]);
  let run = recordedCalls([[changed]]);
  const outcome = await runAddAccess(target, run.calls, shown).then(
    () => "ran",
    (error: Error) => error.name,
  );
  expect(outcome).toBe("AddAccessPlanChanged");
  expect(run.log).toEqual(["list 0"]);

  // The same plan as shown runs.
  run = recordedCalls([[fit]]);
  await expect(runAddAccess(target, run.calls, shown)).resolves.toEqual({
    groupName: "Finance Review",
    plan: "join",
  });
  expect(run.log).toEqual(["list 0", `member ${fit.id}`]);
});
