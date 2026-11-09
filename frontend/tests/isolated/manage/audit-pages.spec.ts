import { expect, test } from "@playwright/test";

import {
  auditPageCursors,
  emptyAuditPages,
  turnAuditPage,
} from "../../../src/components/systems/manage/domain/audit-pages";

// The audit list pages by cursor (contract 2.3): page 1 has no cursor, and
// page n + 1 sends the `next_cursor` of page n. The stack belongs to one
// reader in one organization and one request; any change to these starts
// again at page 1, so a cursor never crosses an account or an organization
// (code review check 22).

const reader = { userId: "user-a", organizationId: "org-a" };
const request = "filters-a";

function twoPagesOn() {
  const second = turnAuditPage(emptyAuditPages, reader, request, {
    to: "next",
    cursor: "after-10",
  });
  return turnAuditPage(second, reader, request, {
    to: "next",
    cursor: "after-20",
  });
}

test("Next keeps each page's cursor; Previous and a page number go back", () => {
  const third = twoPagesOn();
  expect(auditPageCursors(third, reader, request)).toEqual([
    "after-10",
    "after-20",
  ]);
  const back = turnAuditPage(third, reader, request, { to: "previous" });
  expect(auditPageCursors(back, reader, request)).toEqual(["after-10"]);
  const first = turnAuditPage(third, reader, request, { to: "page", index: 0 });
  expect(auditPageCursors(first, reader, request)).toEqual([]);
});

test("another organization, another reader or another request starts at page 1", () => {
  const third = twoPagesOn();
  expect([
    auditPageCursors(third, { ...reader, organizationId: "org-b" }, request),
    auditPageCursors(third, { ...reader, userId: "user-b" }, request),
    auditPageCursors(third, reader, "filters-b"),
  ]).toEqual([[], [], []]);
});

test("a turn after an organization change does not keep the old cursors", () => {
  const third = twoPagesOn();
  const other = { ...reader, organizationId: "org-b" };
  const next = turnAuditPage(third, other, request, {
    to: "next",
    cursor: "b-after-10",
  });
  expect(auditPageCursors(next, other, request)).toEqual(["b-after-10"]);
  expect(auditPageCursors(next, reader, request)).toEqual([]);
});

test("pages read before an organization is admitted do not carry over to it", () => {
  const pending = { ...reader, organizationId: null };
  const second = turnAuditPage(emptyAuditPages, pending, request, {
    to: "next",
    cursor: "after-10",
  });
  expect(auditPageCursors(second, pending, request)).toEqual(["after-10"]);
  expect(auditPageCursors(second, reader, request)).toEqual([]);
});
