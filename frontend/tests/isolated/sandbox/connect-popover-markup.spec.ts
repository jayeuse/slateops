import { expect, test } from "@playwright/test";
import { createElement, type ReactNode } from "react";

import { ConnectPopoverBody } from "../../../src/components/systems/sandbox/components/connect-popover";
import type { ConnectTargetGroup } from "../../../src/components/systems/sandbox/domain/relationship-name";
import { staticMarkup } from "./static-markup";

// The Connect popover's own words and rows, rendered
// (docs/specs/sandbox-ux-redesign.md, FAST-4; comp build-connect-1440).

const twoDepartments: ConnectTargetGroup[] = [
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
      { id: "invoices", name: "Invoices", state: "choosable" },
      { id: "payments", name: "Payments", state: "choosable" },
    ],
  },
];

function Title({ children }: { className?: string; children: ReactNode }) {
  return createElement("h2", null, children);
}

function body(
  targets: ConnectTargetGroup[],
  holdReason: string | null = null,
  initialTargetId: string | null = null,
) {
  return staticMarkup(ConnectPopoverBody, {
    initialTargetId,
    source: { id: "orders", name: "Orders", departmentId: "sales" },
    targets,
    existingNames: { fields: [], relationships: [] },
    holdReason,
    onRequestClose: () => undefined,
    onConnect: () => Promise.resolve({ ok: true as const, value: null }),
    onTargetPreview: () => undefined,
    listRef: { current: null },
    Title,
    phone: false,
  });
}

// UX-C10
test("the popover names the source module it connects from", () => {
  expect(body(twoDepartments)).toContain("Connect Orders to");
});

// FAST-4
test("this module and already linked rows are dim and not choosable", () => {
  const html = body(twoDepartments);
  expect(html).toMatch(
    /role="option"[^>]*aria-disabled="true"[^>]*>Orders<span[^>]*>this module</,
  );
  expect(html).toMatch(
    /role="option"[^>]*aria-disabled="true"[^>]*>Shipments<span[^>]*>already linked</,
  );
  expect(html).not.toMatch(
    /role="option"[^>]*aria-disabled="true"[^>]*>Customers/,
  );
  expect(html).not.toMatch(
    /role="option"[^>]*aria-disabled="true"[^>]*>Invoices/,
  );
  expect(html).not.toMatch(
    /role="option"[^>]*aria-disabled="true"[^>]*>Payments/,
  );
});

// FAST-4
test("targets group under their department, and a single department lists them flat", () => {
  const grouped = body(twoDepartments);
  expect(grouped).toContain('role="listbox"');
  expect(grouped).toContain('aria-label="Target module"');
  expect(grouped).toMatch(/role="group"[^>]*aria-label="Sales"/);
  expect(grouped).toMatch(/role="group"[^>]*aria-label="Finance"/);
  const flat = body([twoDepartments[0]]);
  expect(flat).not.toContain('role="group"');
  expect(flat).toContain(">Customers<");
});

// FAST-4, rule 6
test("Connect says why it waits: no target yet, or a Sandbox action holds the draft", () => {
  expect(body(twoDepartments)).toContain("Choose a module to connect to.");
  const held = body(
    twoDepartments,
    "Wait for the current Sandbox action to finish.",
  );
  expect(held).toContain("Wait for the current Sandbox action to finish.");
  expect(held).not.toContain("Choose a module to connect to.");
});

// FAST-4: a line drawn from Orders' port to Customers opens Connect with
// Customers chosen and the name prefilled.
test("a target chosen by a port drag opens chosen, with the name prefilled", () => {
  const html = body(twoDepartments, null, "customers");
  expect(html).toMatch(/role="option"[^>]*aria-selected="true"[^>]*>Customers/);
  expect(html).toContain('value="Orders to Customers"');
  // A target that cannot be chosen opens nothing chosen.
  const linked = body(twoDepartments, null, "shipments");
  expect(linked).not.toMatch(/aria-selected="true"/);
  expect(linked).toContain('value=""');
});

// FAST-4 (Product Designer review): with every row dim, Connect names why.
test("with no module left to connect to, Connect says so", () => {
  const none: ConnectTargetGroup[] = [
    {
      departmentId: "sales",
      departmentName: "Sales",
      departmentIndex: 0,
      modules: [
        { id: "orders", name: "Orders", state: "self" },
        { id: "shipments", name: "Shipments", state: "linked" },
      ],
    },
  ];
  expect(body(none)).toContain("Orders has no module left to connect to.");
  expect(body(none)).not.toContain("Choose a module to connect to.");
});
