import { expect, test } from "@playwright/test";

import {
  lastOrganizationToOpen,
  openRefusalKind,
  openRefusalMessage,
} from "../../../src/lib/last-organization";

// docs/specs/ux-friction-pass.md item 13: the browser's last organization
// opens at sign-in only when it is one of this account's memberships.
const harbor = {
  orgId: "00000000-0000-4000-8000-0000000000a1",
  name: "Harbor Operations Group",
};
const school = {
  orgId: "00000000-0000-4000-8000-0000000000a2",
  name: "Riverside School",
};
const otherAccounts = "00000000-0000-4000-8000-0000000000f9";

const rows = [
  {
    name: "a stored membership of an account with several opens",
    stored: school.orgId,
    memberships: [harbor, school],
    opens: school.orgId,
  },
  {
    name: "a stored id in capitals still matches its membership",
    stored: school.orgId.toUpperCase(),
    memberships: [harbor, school],
    opens: school.orgId,
  },
  {
    name: "another account's organization in the same browser does not open",
    stored: otherAccounts,
    memberships: [harbor, school],
    opens: null,
  },
  {
    name: "nothing stored shows the chooser",
    stored: null,
    memberships: [harbor, school],
    opens: null,
  },
  {
    name: "a malformed stored value shows the chooser",
    stored: "harbor",
    memberships: [harbor, school],
    opens: null,
  },
  {
    name: "a single-organization account behaves as now",
    stored: harbor.orgId,
    memberships: [harbor],
    opens: null,
  },
] as const;

for (const row of rows)
  test(`UF-C13.2 ${row.name}`, () => {
    expect(lastOrganizationToOpen(row.stored, row.memberships)).toBe(row.opens);
  });

test("UF-C13.3 a refused automatic open names its reason", () => {
  expect(openRefusalKind(403, "mfa_required")).toBe("mfa");
  expect(openRefusalKind(403, "ip_not_allowed")).toBe("network");
  expect(openRefusalKind(403, "organization_required")).toBe("other");
  expect(openRefusalKind(503, null)).toBe("other");
  expect(openRefusalKind(null, null)).toBe("other");
  expect(openRefusalMessage(harbor.name, "mfa")).toBe(
    "Harbor Operations Group asks for two-step verification. Choose it to continue.",
  );
  expect(openRefusalMessage(harbor.name, "network")).toBe(
    "Harbor Operations Group does not allow sign-in from this network.",
  );
  expect(openRefusalMessage(harbor.name, "other")).toBe(
    "Harbor Operations Group could not be opened.",
  );
});
