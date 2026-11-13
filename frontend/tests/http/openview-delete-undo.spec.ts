import { expect, test, type Locator, type Page } from "./helpers/test";
import {
  installListApi,
  listIds,
  recordId,
  statusLabel,
  type Viewer,
} from "./helpers/openview-list-api";
import {
  installKanbanApi,
  installRecordSheetApi,
  kanbanHref,
  quoteRecordSummary,
  recordIds,
  stageIds,
  wireCard,
} from "./helpers/board-kanban-api";
import { wireRecord } from "../helpers/wire";
import { openedSheet } from "./helpers/settled";

// Delete with Undo in the OpenView record sheet (candidate 9 of
// docs/specs/subtle-interactions.md, DR-SI-9.1 to DR-SI-9.5): Delete record
// deletes at once with "Record deleted." and Undo in the record header, and
// Undo restores. The Boards record card sheet keeps its delete question.
// Delete is a soft delete and Restore its reverse; the mock keeps the
// server's rules: a deleted record stays readable by its id and is listed
// only with the Deleted filter.

const contacts = `/openview?section=views&module=${listIds.module}&view=${listIds.view}`;
const first = recordId(0);
const firstPath = `/api/records/${first}`;

type RestoreAnswer =
  /** A value check refuses it (422, `_invalid`). */
  | { kind: "invalid"; detail: string }
  /** Someone restored it first (409). */
  | { kind: "restored-elsewhere" }
  /** Someone deleted it forever (404). */
  | { kind: "purged" };

/**
 * DELETE and restore of the list mock's records. The next restore can be
 * refused once with `refuseNextRestore`.
 */
async function installDeleteApi(page: Page, viewer: Viewer = "writer") {
  const api = await installListApi(page, { viewer });
  const records = api.state.records;
  const state = {
    /** "DELETE <path>" and "POST <path>", in order. */
    commands: [] as string[],
    nextRestore: null as RestoreAnswer | null,
  };
  const wire = (id: string) => {
    const stored = records.get(id);
    if (!stored) throw new Error(`No record ${id}`);
    const label = statusLabel(stored.data[listIds.status]);
    return wireRecord({
      id,
      module_id: listIds.module,
      data: stored.data,
      display_values: label ? { [listIds.status]: label } : {},
      created_at: "2026-11-01T08:00:00Z",
      updated_at: stored.updated_at,
      is_deleted: stored.is_deleted,
      deleted_at: stored.is_deleted ? "2026-11-13T11:00:00Z" : null,
    });
  };
  const setDeleted = (id: string, isDeleted: boolean) => {
    const stored = records.get(id);
    if (stored) records.set(id, { ...stored, is_deleted: isDeleted });
  };
  await page.route(
    (url) => /^\/api\/records\/[0-9a-f-]{36}(\/restore)?$/.test(url.pathname),
    async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const id = path.split("/")[3] ?? "";
      if (request.method() === "DELETE" && !path.endsWith("/restore")) {
        state.commands.push(`DELETE ${path}`);
        setDeleted(id, true);
        return route.fulfill({ status: 204, body: "" });
      }
      if (request.method() === "POST" && path.endsWith("/restore")) {
        state.commands.push(`POST ${path}`);
        const answer = state.nextRestore;
        state.nextRestore = null;
        if (answer?.kind === "invalid")
          return route.fulfill({
            status: 422,
            json: { detail: answer.detail },
          });
        if (answer?.kind === "restored-elsewhere") {
          setDeleted(id, false);
          return route.fulfill({
            status: 409,
            json: { detail: "Record is not deleted" },
          });
        }
        if (answer?.kind === "purged") {
          records.delete(id);
          return route.fulfill({
            status: 404,
            json: { detail: "Record not found" },
          });
        }
        setDeleted(id, false);
        return route.fulfill({ json: wire(id) });
      }
      return route.fallback();
    },
  );
  return {
    state,
    refuseNextRestore(answer: RestoreAnswer) {
      state.nextRestore = answer;
    },
  };
}

async function openRecord(page: Page, id = first) {
  await page.goto(`${contacts}&record=${id}`);
  return openedSheet(page.getByRole("dialog", { name: "Record details" }));
}

/** The record header's status and its Undo (G7, DR-SI-9.2). */
const headerStatus = (sheet: Locator) =>
  sheet.locator("header").getByRole("status");
const headerUndo = (sheet: Locator) =>
  sheet.locator("header").getByRole("button", { name: "Undo", exact: true });
const deletedBadge = (sheet: Locator) =>
  sheet.locator("header").getByText("Deleted", { exact: true });
const moreActions = (sheet: Locator) =>
  sheet.getByRole("button", { name: "More record actions" });

async function deleteRecord(page: Page, sheet: Locator) {
  await moreActions(sheet).click();
  await page.getByRole("menuitem", { name: "Delete record" }).click();
}

test("SI-C9.1 Delete record deletes at once with one DELETE, then says Record deleted. with Undo in the header", async ({
  page,
}) => {
  const api = await installDeleteApi(page);
  const sheet = await openRecord(page);
  await deleteRecord(page, sheet);

  // No question: the one DELETE goes at once.
  await expect.poll(() => api.state.commands).toEqual([`DELETE ${firstPath}`]);
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(headerStatus(sheet)).toHaveText("Record deleted.");
  // DR-SI-9.2: focus moves to Undo, in the sheet.
  await expect(headerUndo(sheet)).toBeFocused();
  // SI-9.3: the sheet shows the deleted record, as a Restore shows it.
  await expect(deletedBadge(sheet)).toBeVisible();
  await expect(
    sheet.getByRole("button", { name: "Restore record" }),
  ).toBeVisible();
  // One status place (G7): the page adds no notice of its own.
  await expect(page.getByText(/restore it from this dialog/)).toHaveCount(0);
});

test("SI-C9.2 Undo restores with one POST restore: Record restored. with no Undo, and the record is active after a reload", async ({
  page,
}) => {
  const api = await installDeleteApi(page);
  const sheet = await openRecord(page);
  await deleteRecord(page, sheet);
  await headerUndo(sheet).click();

  await expect(headerStatus(sheet)).toHaveText("Record restored.");
  await expect(headerUndo(sheet)).toHaveCount(0);
  await expect(deletedBadge(sheet)).toHaveCount(0);
  expect(api.state.commands).toEqual([
    `DELETE ${firstPath}`,
    `POST ${firstPath}/restore`,
  ]);
  // Undo left with its words; focus stayed in the sheet header.
  await expect(moreActions(sheet)).toBeFocused();

  await page.reload();
  const reloaded = await openedSheet(
    page.getByRole("dialog", { name: "Record details" }),
  );
  await expect(
    reloaded.getByRole("button", { name: "Edit record" }),
  ).toBeVisible();
  await expect(deletedBadge(reloaded)).toHaveCount(0);
});

test("SI-C9.3 a record deleted without Undo is listed by the Deleted filter and restores there, with no Undo left", async ({
  page,
}) => {
  const api = await installDeleteApi(page);
  const sheet = await openRecord(page);
  await deleteRecord(page, sheet);
  await expect(headerUndo(sheet)).toBeVisible();
  // DR-SI-9.4: a tab change ends the Undo and its words.
  await sheet.getByRole("tab", { name: "Files" }).click();
  await expect(headerUndo(sheet)).toHaveCount(0);
  await expect(headerStatus(sheet)).toBeEmpty();
  await sheet.getByRole("button", { name: "Close", exact: true }).click();
  await expect(sheet).toHaveCount(0);
  const anaRow = page
    .getByRole("table")
    .getByRole("row")
    .filter({ hasText: "Ana Cruz" });
  await expect(anaRow).toHaveCount(0);

  await page.getByRole("button", { name: "Filters", exact: true }).click();
  await page
    .getByRole("dialog", { name: "Filters" })
    .getByRole("combobox", { name: "Deleted records" })
    .selectOption("only");
  await page.keyboard.press("Escape");
  await anaRow.getByText("Ana Cruz", { exact: true }).click();
  const reopened = await openedSheet(
    page.getByRole("dialog", { name: "Record details" }),
  );
  // G8: the Undo ended with the sheet; Restore works as now.
  await expect(deletedBadge(reopened)).toBeVisible();
  await expect(headerUndo(reopened)).toHaveCount(0);
  await reopened.getByRole("button", { name: "Restore record" }).click();
  await expect(deletedBadge(reopened)).toHaveCount(0);
  expect(api.state.commands).toEqual([
    `DELETE ${firstPath}`,
    `POST ${firstPath}/restore`,
  ]);
});

test("SI-C9.4 an Undo that a value check refuses shows the reason; the record stays deleted with Restore", async ({
  page,
}) => {
  const api = await installDeleteApi(page);
  const sheet = await openRecord(page);
  await deleteRecord(page, sheet);
  api.refuseNextRestore({
    kind: "invalid",
    detail: `Field ${listIds.status} must be one of the configured options`,
  });
  await headerUndo(sheet).click();

  await expect(headerStatus(sheet)).toHaveText(
    "Status: Must be one of the configured options.",
  );
  await expect(headerUndo(sheet)).toHaveCount(0);
  await expect(deletedBadge(sheet)).toBeVisible();
  await expect(
    sheet.getByRole("button", { name: "Restore record" }),
  ).toBeEnabled();
  expect(api.state.commands).toEqual([
    `DELETE ${firstPath}`,
    `POST ${firstPath}/restore`,
  ]);
});

test("SI-C9.4 an Undo after someone restored the record says so and shows the record as it is now", async ({
  page,
}) => {
  const api = await installDeleteApi(page);
  const sheet = await openRecord(page);
  await deleteRecord(page, sheet);
  api.refuseNextRestore({ kind: "restored-elsewhere" });
  await headerUndo(sheet).click();

  await expect(headerStatus(sheet)).toHaveText(
    "Someone already restored this record.",
  );
  await expect(headerUndo(sheet)).toHaveCount(0);
  // The sheet read the record again: it is active.
  await expect(deletedBadge(sheet)).toHaveCount(0);
  await expect(
    sheet.getByRole("button", { name: "Edit record" }),
  ).toBeVisible();
});

test("SI-C9.4 an Undo of a record deleted forever says so, and the sheet shows Record unavailable", async ({
  page,
}) => {
  const api = await installDeleteApi(page);
  const sheet = await openRecord(page);
  await deleteRecord(page, sheet);
  api.refuseNextRestore({ kind: "purged" });
  await headerUndo(sheet).click();

  await expect(
    sheet.getByRole("heading", { name: "Record unavailable" }),
  ).toBeVisible();
  await expect(headerUndo(sheet)).toHaveCount(0);
  // G7: the sheet says why, in the header that read "Record deleted.".
  await expect(headerStatus(sheet)).toHaveText(
    "This record was deleted forever.",
  );
  // The page status does not say it again after the sheet closes.
  await sheet.getByRole("button", { name: "Close", exact: true }).click();
  await expect(sheet).toHaveCount(0);
  await expect(
    page.getByText("This record was deleted forever.", { exact: true }),
  ).toHaveCount(0);
});

test("R4-5 a delete's Undo in the sheet header is the only Undo, after a list change offered one on the page", async ({
  page,
}) => {
  const api = await installDeleteApi(page);
  await page.goto(contacts);
  const anaRow = page
    .getByRole("table")
    .getByRole("row")
    .filter({ hasText: "Ana Cruz" });
  await anaRow.getByRole("button", { name: "Status: Active, options" }).click();
  await page
    .getByRole("group", { name: "Change Status to" })
    .getByRole("menuitemradio", { name: "Former" })
    .click();
  const everyUndo = page.getByRole("button", {
    name: "Undo",
    exact: true,
    includeHidden: true,
  });
  await expect(everyUndo).toHaveCount(1);

  await anaRow.getByText("Ana Cruz", { exact: true }).click();
  const sheet = await openedSheet(
    page.getByRole("dialog", { name: "Record details" }),
  );
  await deleteRecord(page, sheet);
  await expect(headerUndo(sheet)).toBeFocused();
  await expect(everyUndo).toHaveCount(1);
  expect(api.state.commands).toEqual([`DELETE ${firstPath}`]);
});

for (const viewer of ["reader", "guest"] as const) {
  test(`SI-C9.5 a ${viewer} gets no Delete record`, async ({ page }) => {
    const api = await installDeleteApi(page, viewer);
    const sheet = await openRecord(page);
    await moreActions(sheet).click();
    await expect(
      page.getByRole("menuitem", { name: "Copy link" }),
    ).toBeVisible();
    await expect(
      page.getByRole("menuitem", { name: "Delete record" }),
    ).toHaveCount(0);
    expect(api.state.commands).toEqual([]);
  });
}

test("SI-C9.7 the Kanban record card sheet still asks Delete this record? and deletes nothing on Cancel", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const card = wireCard(null, stageIds.doing, 1024, {
    kind: "record",
    record: quoteRecordSummary,
  });
  await installKanbanApi(page, { level: "write", cards: [card] });
  await installRecordSheetApi(page);
  const deletes: string[] = [];
  await page.route(`**/api/records/${recordIds.quote}`, (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    deletes.push(route.request().url());
    return route.fulfill({ status: 204, body: "" });
  });
  await page.goto(kanbanHref(`card=${card.id}`));
  const sheet = await openedSheet(
    page.getByRole("dialog", { name: "Q-24112", exact: true }),
  );
  await moreActions(sheet).click();
  await page.getByRole("menuitem", { name: "Delete record" }).click();
  const question = page.getByRole("alertdialog", {
    name: "Delete this record?",
  });
  await expect(question).toBeVisible();
  await question.getByRole("button", { name: "Cancel" }).click();
  await expect(question).toHaveCount(0);
  expect(deletes).toEqual([]);
  // No Undo comes to the Boards sheets (SI-9.5).
  await expect(
    sheet.getByRole("button", { name: "Undo", exact: true }),
  ).toHaveCount(0);
});

test("SI-C9.8 on a phone, Delete record and its Undo work by keyboard in the sheet, with a 44 px Undo", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const api = await installDeleteApi(page);
  const sheet = await openRecord(page);
  await moreActions(sheet).focus();
  await page.keyboard.press("Enter");
  const deleteItem = page.getByRole("menuitem", { name: "Delete record" });
  await expect(deleteItem).toBeVisible();
  await page.keyboard.press("End");
  await expect(deleteItem).toBeFocused();
  await page.keyboard.press("Enter");

  const undo = headerUndo(sheet);
  await expect(undo).toBeFocused();
  const box = await undo.boundingBox();
  expect(box?.height).toBeGreaterThanOrEqual(44);
  await page.keyboard.press("Enter");
  await expect(headerStatus(sheet)).toHaveText("Record restored.");
  await expect(moreActions(sheet)).toBeFocused();
  expect(api.state.commands).toEqual([
    `DELETE ${firstPath}`,
    `POST ${firstPath}/restore`,
  ]);
});
