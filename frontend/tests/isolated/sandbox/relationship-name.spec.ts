import { expect, test } from "@playwright/test";

import type { Design } from "../../../src/components/systems/sandbox/domain/model";
import {
  chooseTarget,
  clashReason,
  connectSubmission,
  connectTargetGroups,
  draftName,
  EMPTY_CONNECT_DRAFT,
  nextChoosable,
  prefill,
  relationshipNamesInUse,
  typeAheadMatch,
  typeName,
} from "../../../src/components/systems/sandbox/domain/relationship-name";

// Connect from a module (docs/specs/sandbox-ux-redesign.md, FAST-4, N6).

function field(id: string, name: string, closed = false) {
  return {
    id,
    name,
    type: "Text",
    required: false,
    value: "",
    options: "",
    closed,
  };
}

function sandboxModule(
  id: string,
  name: string,
  department: string,
  fields: ReturnType<typeof field>[] = [],
  closed = false,
) {
  return { id, name, department, closed, fields, x: 0, y: 0 };
}

function relationship(
  id: string,
  name: string,
  source: string,
  target: string,
) {
  return {
    id,
    name,
    source,
    target,
    cardinality: "One-to-many",
    fieldMappings: [],
  };
}

// Sales: Orders, Customers, Shipments. Finance: Invoices, Payments, and the
// closed Archive. Orders links out to Shipments and to the closed Archive;
// Invoices links in to Orders, the other direction.
const design: Design = {
  departments: [
    { id: "sales", name: "Sales", closed: false },
    { id: "finance", name: "Finance", closed: false },
    { id: "empty", name: "Empty", closed: false },
  ],
  modules: [
    sandboxModule("orders", "Orders", "sales", [
      field("number", "Order number"),
      field("customer", "Customer"),
      field("notes", "Old notes", true),
    ]),
    sandboxModule("customers", "Customers", "sales"),
    sandboxModule("shipments", "Shipments", "sales"),
    sandboxModule("invoices", "Invoices", "finance"),
    sandboxModule("payments", "Payments", "finance"),
    sandboxModule("archive", "Archive", "finance", [], true),
  ],
  relationships: [
    relationship("r1", "Shipment", "orders", "shipments"),
    relationship("r2", "Archive link", "orders", "archive"),
    relationship("r3", "Order", "invoices", "orders"),
  ],
  rules: [],
};

const targets = connectTargetGroups(design, "orders");
const names = relationshipNamesInUse(design, "orders");

// UX-C10
test("connecting Orders to Customers prefills the name and keeps Orders as the source", () => {
  const draft = chooseTarget(EMPTY_CONNECT_DRAFT, targets, "customers");
  expect(draftName(draft, "Orders", targets, names)).toBe(
    "Orders to Customers",
  );
  expect(connectSubmission(draft, "Orders", targets, names)).toEqual({
    ok: true,
    request: { targetId: "customers", name: "Orders to Customers" },
  });
});

// UX-C10
test("the name follows the chosen target until the administrator types in it", () => {
  let draft = chooseTarget(EMPTY_CONNECT_DRAFT, targets, "customers");
  draft = chooseTarget(draft, targets, "payments");
  expect(draftName(draft, "Orders", targets, names)).toBe("Orders to Payments");
  draft = typeName(draft, "Buyer");
  draft = chooseTarget(draft, targets, "customers");
  expect(draftName(draft, "Orders", targets, names)).toBe("Buyer");
  // A name typed down to empty stays the administrator's, not the prefill.
  draft = typeName(draft, "");
  expect(draftName(draft, "Orders", targets, names)).toBe("");
  // Before a target is chosen there is no name to prefill.
  expect(draftName(EMPTY_CONNECT_DRAFT, "Orders", targets, names)).toBe("");
});

// N6
test("the names in use are the source's open fields and its outgoing relationships to open modules", () => {
  expect(names).toEqual({
    fields: ["Order number", "Customer"],
    relationships: ["Shipment"],
  });
});

// N6
test("a clashing prefill adds 2, then 3, comparing without case", () => {
  const cases = [
    { fields: [], relationships: [], expected: "Orders to Customers" },
    {
      fields: ["orders to customers"],
      relationships: [],
      expected: "Orders to Customers 2",
    },
    {
      fields: ["Orders to Customers"],
      relationships: ["ORDERS TO CUSTOMERS 2"],
      expected: "Orders to Customers 3",
    },
  ];
  for (const { fields, relationships, expected } of cases)
    expect(prefill("Orders", "Customers", { fields, relationships })).toBe(
      expected,
    );
});

// N6
test("a typed name that clashes is refused with the reason, naming a field or a relationship", () => {
  const inUse = { fields: ["Customers"], relationships: ["Billing"] };
  expect(clashReason("customers ", inUse, "Orders")).toBe(
    "Orders already has a field named Customers.",
  );
  expect(clashReason("BILLING", inUse, "Orders")).toBe(
    "Orders already has a relationship named Billing.",
  );
  expect(clashReason("Buyer", inUse, "Orders")).toBeNull();
  const draft = typeName(
    chooseTarget(EMPTY_CONNECT_DRAFT, targets, "customers"),
    "customer",
  );
  expect(connectSubmission(draft, "Orders", targets, names)).toEqual({
    ok: false,
    reason: "Orders already has a field named Customer.",
  });
});

// N2
test("connect refuses a missing target, an empty name, and a name over 80 characters", () => {
  expect(
    connectSubmission(EMPTY_CONNECT_DRAFT, "Orders", targets, names),
  ).toEqual({
    ok: false,
    reason: "Choose a module to connect to.",
  });
  const chosen = chooseTarget(EMPTY_CONNECT_DRAFT, targets, "customers");
  expect(
    connectSubmission(typeName(chosen, "  "), "Orders", targets, names),
  ).toEqual({
    ok: false,
    reason: "Relationship name is required.",
  });
  expect(
    connectSubmission(
      typeName(chosen, "a".repeat(81)),
      "Orders",
      targets,
      names,
    ),
  ).toEqual({
    ok: false,
    reason: "Relationship name must be 80 characters or fewer.",
  });
  // The name is sent trimmed, as Build saves names.
  expect(
    connectSubmission(typeName(chosen, " Buyer "), "Orders", targets, names),
  ).toEqual({
    ok: true,
    request: { targetId: "customers", name: "Buyer" },
  });
});

// FAST-4
test("targets are grouped by department, with this module and same-direction links not choosable", () => {
  expect(targets).toEqual([
    {
      departmentId: "sales",
      departmentName: "Sales",
      departmentIndex: 0,
      modules: [
        { id: "orders", name: "Orders", state: "self" },
        { id: "customers", name: "Customers", state: "choosable" },
        { id: "shipments", name: "Shipments", state: "linked" },
      ],
    },
    {
      departmentId: "finance",
      departmentName: "Finance",
      departmentIndex: 1,
      modules: [
        // Invoices links only in to Orders, so Orders can still link out to it.
        { id: "invoices", name: "Invoices", state: "choosable" },
        { id: "payments", name: "Payments", state: "choosable" },
      ],
    },
  ]);
  // A row that is not choosable cannot become the target.
  expect(
    chooseTarget(EMPTY_CONNECT_DRAFT, targets, "shipments").targetId,
  ).toBeNull();
  expect(chooseTarget(EMPTY_CONNECT_DRAFT, targets, "invoices").targetId).toBe(
    "invoices",
  );
});

// UX-C9
test("arrows move between choosable targets only, and stop at the ends", () => {
  expect(nextChoosable(targets, null, 1)).toBe("customers");
  expect(nextChoosable(targets, "customers", 1)).toBe("invoices");
  expect(nextChoosable(targets, "invoices", 1)).toBe("payments");
  expect(nextChoosable(targets, "payments", 1)).toBe("payments");
  expect(nextChoosable(targets, "payments", -1)).toBe("invoices");
  expect(nextChoosable(targets, "customers", -1)).toBe("customers");
});

// UX-C9
test("typing jumps to the first choosable target that starts with the typed letters", () => {
  expect(typeAheadMatch(targets, "Cus", null)).toBe("customers");
  expect(typeAheadMatch(targets, "pay", "customers")).toBe("payments");
  // Orders and Shipments are not choosable, so their letters find nothing.
  expect(typeAheadMatch(targets, "or", null)).toBeNull();
  expect(typeAheadMatch(targets, "ship", null)).toBeNull();
});
