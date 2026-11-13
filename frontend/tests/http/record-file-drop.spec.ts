import {
  defaultOrganization,
  expect,
  heldResponse,
  isEventStream,
  signedInAs,
  test,
  type Locator,
  type Page,
  type Route,
} from "./helpers/test";
import { installOpenViewEventSource } from "./helpers/openview-event-source";
import { keysetPageOf, pageOf } from "../helpers/pagination";
import { emptyWireQuery } from "../helpers/query-definitions";
import { wireField, wireRecord, wireView } from "../helpers/wire";
import { openedSheet } from "./helpers/settled";
import {
  installKanbanApi,
  installRecordSheetApi,
  kanbanHref,
  quoteRecordSummary,
  recordIds,
  stageIds,
  wireCard,
} from "./helpers/board-kanban-api";
import { createMemorySeed } from "../support/comms-memory/memory/seed";
import { validateMemoryState } from "../support/comms-memory/memory/snapshot";
import { createMemoryCommsRuntime } from "../support/comms-memory/memory-client";
import { installCommsLiveApi } from "./helpers/comms-live-api";

// A dropped or pasted file attaches as "Choose file" does (candidate 7 of
// docs/specs/subtle-interactions.md, SI-7.1 to SI-7.5, DR-SI-7.1 to 7.5): on
// the record Files tab of the OpenView record sheet and of the Boards record
// card sheet, and in the Files library. The drop and paste events here are
// synthetic, with a real DataTransfer: a synthetic event has no browser
// default, so "the browser does not open the file" is proved by the page
// cancelling the event (dispatchEvent returns false), the only thing that
// stops a real drop from opening the file. The one-file, type and size rules
// are owned by tests/isolated/platform/file-drop.spec.ts.

test.use({ trace: "off", screenshot: "off", video: "off" });

const userId = "00000000-0000-4000-8000-000000000f01";
const departmentId = "00000000-0000-4000-8000-000000000f02";
const moduleId = "00000000-0000-4000-8000-000000000f03";
const viewId = "00000000-0000-4000-8000-000000000f04";
const recordId = "00000000-0000-4000-8000-000000000f05";
const nameId = "00000000-0000-4000-8000-000000000f06";
const fileUuid = (index: number) =>
  `00000000-0000-4000-8000-${String(0xf100 + index).padStart(12, "0")}`;
const MAX_FILE_BYTES = 25 * 1024 * 1024;
const png =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6+SYAAAAASUVORK5CYII=";

type FileWire = {
  id: string;
  purpose: "record_attachment" | "library_document";
  record_id: string | null;
  department_id: string | null;
  board_id: null;
  creator_id: string;
  filename: string;
  media_type: string | null;
  expected_size: number;
  actual_size: number | null;
  state: "awaiting_upload" | "ready";
  failure_code: null;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
};

/**
 * The file endpoints of "Choose file": list, reserve, the bytes, and the
 * status read. It keeps every reserve and every byte upload, so a test can
 * prove that nothing went out, and it can hold the next byte upload.
 */
async function installFileApi(page: Page) {
  const state = {
    files: [] as FileWire[],
    reserves: [] as Record<string, unknown>[],
    uploads: [] as string[],
    uploadHold: null as ReturnType<typeof heldResponse> | null,
    downloadHold: null as ReturnType<typeof heldResponse> | null,
  };
  await page.route("**/api/files**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (url.pathname === "/api/files" && method === "GET") {
      const record = url.searchParams.get("record_id");
      const department = url.searchParams.get("department_id");
      const limit = Number(url.searchParams.get("limit"));
      const offset = Number(url.searchParams.get("offset"));
      const listed = state.files.filter(
        (file) =>
          !file.is_deleted &&
          (record
            ? file.record_id === record
            : file.department_id === department),
      );
      const response = pageOf(listed.slice(offset, offset + limit), {
        limit,
        offset,
        total: listed.length,
      });
      return route.fulfill({
        json: department
          ? {
              ...response,
              creator_labels: {},
              storage_used_bytes: listed.reduce(
                (sum, file) => sum + (file.actual_size ?? 0),
                0,
              ),
            }
          : response,
      });
    }
    if (url.pathname === "/api/files" && method === "POST") {
      const body = request.postDataJSON() as {
        purpose: FileWire["purpose"];
        record_id?: string;
        department_id?: string;
        filename: string;
        expected_size: number;
      };
      state.reserves.push(body);
      const file: FileWire = {
        id: fileUuid(state.reserves.length),
        purpose: body.purpose,
        record_id: body.record_id ?? null,
        department_id: body.department_id ?? null,
        board_id: null,
        creator_id: userId,
        filename: body.filename,
        media_type: null,
        expected_size: body.expected_size,
        actual_size: null,
        state: "awaiting_upload",
        failure_code: null,
        is_deleted: false,
        created_at: "2026-11-13T01:00:00Z",
        updated_at: "2026-11-13T01:00:00Z",
      };
      state.files.push(file);
      return route.fulfill({ status: 201, json: file });
    }
    const file = state.files.find(
      (item) => item.id === url.pathname.split("/")[3],
    );
    if (!file)
      return route.fulfill({ status: 404, json: { detail: "Not found" } });
    if (method === "PUT" && url.pathname.endsWith("/content")) {
      state.uploads.push(file.filename);
      const hold = state.uploadHold;
      state.uploadHold = null;
      hold?.enter();
      await hold?.released;
      file.state = "ready";
      file.actual_size = file.expected_size;
      file.media_type = "application/pdf";
      return route.fulfill({ json: file });
    }
    if (method === "GET" && url.pathname.endsWith("/content")) {
      const hold = state.downloadHold;
      state.downloadHold = null;
      hold?.enter();
      await hold?.released;
      return route.fulfill({
        body: Buffer.alloc(file.expected_size),
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(file.filename)}`,
          "X-Content-Type-Options": "nosniff",
        },
      });
    }
    return route.fulfill({ json: file });
  });
  return {
    state,
    /** Holds the next download until `release` runs. */
    holdNextDownload() {
      const hold = heldResponse();
      state.downloadHold = hold;
      return hold;
    },
    /** Holds the next byte upload until `release` runs. */
    holdNextUpload() {
      const hold = heldResponse();
      state.uploadHold = hold;
      return hold;
    },
  };
}

type Role = "writer" | "reader";

/** A Contacts module page whose one record opens in the record sheet. */
async function installRecordPage(
  page: Page,
  options: { role?: Role; deleted?: boolean } = {},
) {
  await installOpenViewEventSource(page);
  const view = wireView({
    id: viewId,
    module_id: moduleId,
    name: "Contacts",
    is_default: true,
    definition: emptyWireQuery({
      columns: [{ field_id: nameId, expected_type: "text" }],
    }),
    presentation: {
      version: 1,
      layout: "table",
      column_field_ids: [nameId],
      pinned_field_ids: [],
      density: "comfortable",
      wrap: false,
      card_size: "comfortable",
      primary_field_id: nameId,
      secondary_field_id: null,
      group_by_field_id: null,
    },
    created_at: "2026-11-01T08:00:00Z",
    updated_at: "2026-11-01T08:00:00Z",
  });
  const fields = [
    wireField({
      id: nameId,
      module_id: moduleId,
      name: "Name",
      type: "text",
      required: true,
      position: 0,
    }),
  ];
  const record = wireRecord({
    id: recordId,
    module_id: moduleId,
    data: { [nameId]: "Harbor Supplies" },
    created_at: "2026-11-01T08:00:00Z",
    updated_at: "2026-11-12T09:00:00Z",
    deleted_at: options.deleted ? "2026-11-12T10:00:00Z" : null,
    is_deleted: options.deleted ?? false,
    performed_by: userId,
  });
  await page.route("**/api/**", async (route: Route) => {
    if (isEventStream(route)) return route.fallback();
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (url.pathname === "/api/departments")
      return route.fulfill({
        json: pageOf(
          [
            {
              id: departmentId,
              department_name: "Sales",
              created_at: "2026-11-01T08:00:00Z",
              updated_at: "2026-11-01T08:00:00Z",
              deleted_at: null,
              is_deleted: false,
              performed_by: userId,
            },
          ],
          { limit: 100 },
        ),
      });
    if (url.pathname === `/api/modules/${moduleId}`)
      return route.fulfill({
        json: {
          id: moduleId,
          module_name: "Contacts",
          department_id: departmentId,
          title_field_id: nameId,
          is_deleted: false,
        },
      });
    if (url.pathname === "/api/views/data-sources")
      return route.fulfill({
        json: pageOf(
          [
            {
              id: moduleId,
              name: "Contacts",
              department_id: departmentId,
              title_field_id: nameId,
            },
          ],
          { limit: 100 },
        ),
      });
    if (url.pathname === `/api/views/data-sources/${moduleId}/fields`)
      return route.fulfill({ json: pageOf(fields, { limit: 100 }) });
    if (url.pathname === "/api/views" && method === "GET")
      return route.fulfill({ json: pageOf([view], { limit: 100 }) });
    if (url.pathname === `/api/views/${viewId}` && method === "GET")
      return route.fulfill({ json: view });
    if (url.pathname === "/api/fields")
      return route.fulfill({ json: pageOf([], { limit: 100 }) });
    if (url.pathname === "/api/relationships" && method === "GET")
      return route.fulfill({
        json: keysetPageOf([], { limit: 100, offset: 0, total: 0 }),
      });
    if (url.pathname === "/api/records/query" && method === "POST")
      return route.fulfill({
        json: pageOf([record], { limit: 100 }),
      });
    if (url.pathname === `/api/records/${recordId}` && method === "GET")
      return route.fulfill({ json: record });
    return route.fallback();
  });
  await signedInAs(page, {
    id: userId,
    role: options.role === "reader" ? "member" : "admin",
    access:
      options.role === "reader"
        ? [{ department_id: departmentId, module_id: null, level: "read" }]
        : [],
  });
  return installFileApi(page);
}

/** Opens the record's Files tab; returns the tab panel. */
async function openRecordFiles(page: Page) {
  await page.goto(
    `/openview?section=views&module=${moduleId}&view=${viewId}&record=${recordId}`,
  );
  const sheet = await openedSheet(
    page.getByRole("dialog", { name: "Record details" }),
  );
  await sheet.getByRole("tab", { name: "Files", exact: true }).click();
  const panel = sheet.getByRole("tabpanel", { name: "Files" });
  await expect(panel.getByText("No files attached.")).toBeVisible();
  return { sheet, panel };
}

type DroppedFile = { name: string; size?: number; type?: string };

/**
 * Fires one drag or paste event at `target`, as the browser does: the drag
 * carries the files in its DataTransfer; a paste carries them, and optional
 * text, in its clipboard data. Returns whether the page cancelled the event.
 * (A constructed DataTransfer keeps no drop effect, so none is read here.)
 */
async function fire(
  target: Locator,
  kind: "dragenter" | "dragover" | "dragleave" | "drop" | "paste",
  files: readonly DroppedFile[],
  text?: string,
): Promise<boolean> {
  return target.evaluate(
    (node, { kind, files, text, png }) => {
      const transfer = new DataTransfer();
      for (const file of files)
        transfer.items.add(
          new File(
            [
              file.type === "image/png"
                ? Uint8Array.from(atob(png), (char) => char.charCodeAt(0))
                : new Uint8Array(file.size ?? 4),
            ],
            file.name,
            { type: file.type ?? "application/pdf" },
          ),
        );
      if (text) transfer.setData("text/plain", text);
      const init = { bubbles: true, cancelable: true, composed: true };
      const event =
        kind === "paste"
          ? new ClipboardEvent("paste", { ...init, clipboardData: transfer })
          : new DragEvent(kind, { ...init, dataTransfer: transfer });
      return !node.dispatchEvent(event);
    },
    { kind, files, text, png },
  );
}

/** A full drag of `files` over `target` and a drop on it. */
async function dropOn(target: Locator, files: readonly DroppedFile[]) {
  await fire(target, "dragenter", files);
  await fire(target, "dragover", files);
  return fire(target, "drop", files);
}

const quote = { name: "Quote.pdf" };

test("SI-C7.1 a file dragged over the record Files tab shows Drop to attach, and dropped it uploads as Choose file does", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const api = await installRecordPage(page);
  const { panel } = await openRecordFiles(page);
  const inside = panel.getByText("No files attached.");

  await fire(inside, "dragenter", [quote]);
  expect(await fire(inside, "dragover", [quote])).toBe(true);
  await expect(
    panel.getByText("Drop to attach", { exact: true }),
  ).toBeVisible();
  // Leaving the panel takes the drop state away.
  await fire(inside, "dragleave", [quote]);
  await expect(panel.getByText("Drop to attach", { exact: true })).toHaveCount(
    0,
  );

  expect(await dropOn(inside, [quote])).toBe(true);
  await expect(panel.getByText("Drop to attach", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    panel.getByRole("button", { name: "Download Quote.pdf" }),
  ).toBeVisible();
  // The same requests as Choose file: one reservation, then the bytes.
  expect(api.state.reserves).toEqual([
    {
      purpose: "record_attachment",
      record_id: recordId,
      filename: "Quote.pdf",
      expected_size: 4,
    },
  ]);
  expect(api.state.uploads).toEqual(["Quote.pdf"]);
});

test("SI-C7.3 two files, a file over 25 MB, or a drop during an upload uploads nothing and says why", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const api = await installRecordPage(page);
  const { panel } = await openRecordFiles(page);
  const inside = panel.getByText("No files attached.");

  await dropOn(inside, [quote, { name: "Terms.pdf" }]);
  await expect(panel.getByRole("alert")).toHaveText("Drop one file at a time.");
  await dropOn(inside, [{ name: "Scan.pdf", size: MAX_FILE_BYTES + 1 }]);
  await expect(panel.getByRole("alert")).toHaveText(
    "Choose a file larger than 0 bytes and no larger than 25 MB.",
  );
  expect(api.state.reserves).toEqual([]);

  // While one upload runs, a second drop waits for nothing and sends nothing.
  const upload = api.holdNextUpload();
  await dropOn(inside, [quote]);
  await upload.entered;
  await dropOn(panel.getByText("Uploading file…"), [{ name: "Terms.pdf" }]);
  await expect(panel.getByRole("alert")).toHaveText(
    "Wait for the current upload to finish.",
  );
  upload.release();
  await expect(
    panel.getByRole("button", { name: "Download Quote.pdf" }),
  ).toBeVisible();
  expect(api.state.reserves.map((body) => body.filename)).toEqual([
    "Quote.pdf",
  ]);
  expect(api.state.uploads).toEqual(["Quote.pdf"]);
});

test("SI-C7.3 a file dropped while a download runs uploads nothing and asks to drop it again", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const api = await installRecordPage(page);
  const { panel } = await openRecordFiles(page);
  await dropOn(panel.getByText("No files attached."), [quote]);
  const download = panel.getByRole("button", { name: "Download Quote.pdf" });
  await expect(download).toBeVisible();

  // The panel runs one operation at a time; a download is not an upload.
  const held = api.holdNextDownload();
  await download.click();
  await held.entered;
  await dropOn(panel.getByText("Downloading file…"), [{ name: "Terms.pdf" }]);
  await expect(panel.getByRole("alert")).toHaveText(
    "Wait a moment, then drop the file again.",
  );
  held.release();
  await expect(panel.getByText("Downloading file…")).toHaveCount(0);
  expect(api.state.reserves.map((body) => body.filename)).toEqual([
    "Quote.pdf",
  ]);
  expect(api.state.uploads).toEqual(["Quote.pdf"]);
});

for (const setup of [
  { who: "a reader", options: { role: "reader" as const } },
  { who: "a writer on a deleted record", options: { deleted: true } },
]) {
  test(`SI-C7.4 for ${setup.who} the record Files tab takes no drop, and no dropped file opens in the browser`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const api = await installRecordPage(page, setup.options);
    const { sheet, panel } = await openRecordFiles(page);
    await expect(panel.getByText("Choose file")).toHaveCount(0);
    const inside = panel.getByText("No files attached.");
    const beside = sheet.getByRole("tab", { name: "Details", exact: true });

    for (const target of [inside, beside]) {
      await fire(target, "dragenter", [quote]);
      // The page cancels the drag and the drop, so a real browser neither
      // offers the drop nor opens the file.
      expect(await fire(target, "dragover", [quote])).toBe(true);
      await expect(panel.getByText("Drop to attach")).toHaveCount(0);
      expect(await fire(target, "drop", [quote])).toBe(true);
    }
    // A paste in the panel attaches nothing either.
    expect(await fire(inside, "paste", [quote])).toBe(false);
    await expect(page).toHaveURL(/record=/);
    expect(api.state.reserves).toEqual([]);
    expect(api.state.uploads).toEqual([]);
  });
}

test("SI-C7.4 on a writer's module page, a file dropped beside the Files tab is ignored and opens nothing", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const api = await installRecordPage(page);
  const { sheet } = await openRecordFiles(page);
  const beside = sheet.getByRole("tab", { name: "Details", exact: true });
  expect(await fire(beside, "dragover", [quote])).toBe(true);
  expect(await fire(beside, "drop", [quote])).toBe(true);
  expect(api.state.reserves).toEqual([]);
});

test("SI-C7.6 at 390 px Choose file uploads to the record Files tab as now, on a 44 px target", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const api = await installRecordPage(page);
  const { panel } = await openRecordFiles(page);
  const choose = panel.getByRole("button", { name: "Choose file" });
  expect((await choose.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  await panel.getByLabel("Upload file", { exact: true }).setInputFiles({
    name: "Quote.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF"),
  });
  await expect(
    panel.getByRole("button", { name: "Download Quote.pdf" }),
  ).toBeVisible();
  expect(api.state.uploads).toEqual(["Quote.pdf"]);
});

// The Files library of one department.
async function installLibraryPage(page: Page, role: Role) {
  await installOpenViewEventSource(page);
  const department = {
    id: departmentId,
    department_name: "Sales",
    created_at: "2026-11-01T08:00:00Z",
    updated_at: "2026-11-01T08:00:00Z",
    deleted_at: null,
    is_deleted: false,
    performed_by: userId,
  };
  await page.route("**/api/workspace", (route) =>
    route.fulfill({
      json: {
        id: fileUuid(900),
        display_name: "Drop test workspace",
        legal_name: null,
        description: null,
        contact_email: null,
        contact_phone: null,
        postal_address: null,
        locale: "en-GB",
        timezone: "Asia/Manila",
        logo_file_id: null,
        mark: "DT",
        currency: "PHP",
        week_start: "monday",
        business_hours: "09:00–18:00",
        theme: "slate",
        revision: 1,
      },
    }),
  );
  await page.route("**/api/departments?*", (route) => {
    const parameters = new URL(route.request().url()).searchParams;
    return route.fulfill({
      json: pageOf([department], {
        limit: Number(parameters.get("limit")) || 100,
        offset: 0,
        total: 1,
      }),
    });
  });
  await page.route(/\/api\/departments\/[0-9a-z-]+$/, (route) =>
    route.fulfill({ json: department }),
  );
  await signedInAs(page, {
    id: userId,
    role: role === "reader" ? "member" : "admin",
    access:
      role === "reader"
        ? [{ department_id: departmentId, module_id: null, level: "read" }]
        : [],
  });
  const api = await installFileApi(page);
  await page.goto(`/platform?section=files&department=${departmentId}`);
  await expect(
    page.getByRole("heading", { name: "Department file library" }),
  ).toBeVisible();
  const search = page.getByRole("searchbox", { name: "Search files by name" });
  await expect(search).toBeVisible();
  await expect(page.getByText("Storage used:")).toBeVisible();
  return { api, search };
}

test("SI-C7.2 in the Files library a pasted file uploads, a dragged file shows Drop to upload, and a paste in the search box stays text", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const { api, search } = await installLibraryPage(page, "writer");
  const choose = page.getByRole("button", { name: "Choose file" });
  await choose.focus();

  await fire(choose, "dragenter", [quote]);
  await fire(choose, "dragover", [quote]);
  await expect(page.getByText("Drop to upload", { exact: true })).toBeVisible();
  await fire(choose, "dragleave", [quote]);
  await expect(page.getByText("Drop to upload", { exact: true })).toHaveCount(
    0,
  );

  const pasted = { name: "Yard.png", type: "image/png" };
  expect(await fire(choose, "paste", [pasted])).toBe(true);
  await expect(
    page.getByRole("button", { name: "Download Yard.png" }),
  ).toBeVisible();
  expect(api.state.reserves).toEqual([
    {
      purpose: "library_document",
      department_id: departmentId,
      filename: "Yard.png",
      expected_size: 68,
    },
  ]);

  // In the search box the paste is the browser's: the page leaves it alone.
  await search.focus();
  expect(await fire(search, "paste", [{ name: "Terms.pdf" }], "Terms")).toBe(
    false,
  );
  expect(api.state.reserves).toHaveLength(1);
});

test("SI-C7.4 a Files library reader gets no drop state, and no dropped or pasted file uploads or opens", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const { api } = await installLibraryPage(page, "reader");
  await expect(page.getByRole("button", { name: "Choose file" })).toHaveCount(
    0,
  );
  const inside = page.getByText("Storage used:");
  await fire(inside, "dragenter", [quote]);
  expect(await fire(inside, "dragover", [quote])).toBe(true);
  await expect(page.getByText("Drop to upload")).toHaveCount(0);
  expect(await fire(inside, "drop", [quote])).toBe(true);
  expect(await fire(inside, "paste", [quote])).toBe(false);
  expect(api.state.reserves).toEqual([]);
});

test("SI-C7.5 the Files tab of a Kanban record card sheet attaches a dropped file to its record", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const card = wireCard(null, stageIds.doing, 1024, {
    kind: "record",
    record: quoteRecordSummary,
  });
  await installKanbanApi(page, { level: "write", cards: [card] });
  await installRecordSheetApi(page);
  const api = await installFileApi(page);
  await page.goto(kanbanHref(`card=${card.id}`));
  const sheet = await openedSheet(
    page.getByRole("dialog", { name: "Q-24112", exact: true }),
  );
  await sheet
    .getByRole("tablist", { name: "Record sections" })
    .getByRole("tab", { name: "Files", exact: true })
    .click();
  const panel = sheet.getByRole("tabpanel", { name: "Files" });
  const inside = panel.getByText("No files attached.");
  await expect(inside).toBeVisible();

  await fire(inside, "dragenter", [quote]);
  await fire(inside, "dragover", [quote]);
  await expect(
    panel.getByText("Drop to attach", { exact: true }),
  ).toBeVisible();
  expect(await fire(inside, "drop", [quote])).toBe(true);
  await expect(
    panel.getByRole("button", { name: "Download Quote.pdf" }),
  ).toBeVisible();
  expect(api.state.reserves).toEqual([
    {
      purpose: "record_attachment",
      record_id: recordIds.quote,
      filename: "Quote.pdf",
      expected_size: 4,
    },
  ]);
  // Beside the panel, the card sheet ignores a dropped file.
  const beside = sheet.getByRole("button", { name: "Close card" });
  expect(await fire(beside, "dragover", [quote])).toBe(true);
  expect(await fire(beside, "drop", [quote])).toBe(true);
  expect(api.state.reserves).toHaveLength(1);
});

test("SI-C7.5 the OpenComms composer takes a dropped file as before", async ({
  page,
}) => {
  const owner = {
    user_id: "00000000-0000-4000-8000-000000000101",
    org_id: defaultOrganization.org_id,
  };
  await signedInAs(page, { id: owner.user_id, role: "admin" });
  const seed = createMemorySeed(owner, {
    role: "admin",
    display_name: "Composer owner",
  });
  seed.configuration.workspace = {
    settings: {},
    capabilities: {
      scope: { kind: "workspace" },
      everyone: {},
      group_grants: [],
    },
  };
  validateMemoryState(seed, owner.org_id);
  await installCommsLiveApi(page, {
    userId: owner.user_id,
    organizationId: owner.org_id,
    runtime: createMemoryCommsRuntime({ owner, initial: seed }),
  });
  await page.goto("/comms");
  const input = page.getByRole("textbox", { name: "Message", exact: true });
  await expect(input).toBeEnabled();
  expect(
    await fire(input, "drop", [{ name: "Yard.png", type: "image/png" }]),
  ).toBe(true);
  await expect(
    page.getByRole("button", { name: "Remove Yard.png", exact: true }),
  ).toBeVisible();
});
