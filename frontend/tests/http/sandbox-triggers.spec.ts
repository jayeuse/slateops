import { answeredHeaders, expect, test, type Page } from "./helpers/test";
import {
  addInEntry,
  clickBesideBox,
  createEntry,
  expectBelowAppBar,
  openAuthenticatedSandbox,
} from "./helpers/sandbox-api";
import type { SandboxDocumentV4 } from "../../src/components/systems/sandbox/domain/document";
import type { Design } from "../../src/components/systems/sandbox/domain/model";
import { configuredSandboxDesign } from "../helpers/sandbox-fixtures";
import { settled } from "./helpers/layout";

// Phase 4 of the Sandbox UI/UX pass (docs/specs/sandbox-ui-ux-pass.md):
// TRG-1 to TRG-5. The list and When/If/Then rail come from the Sandbox
// relayout (docs/specs/sandbox-relayout.md S5 to S7); the structure region,
// the whole-trigger sentence, the typed pickers, and trigger drafts from
// docs/specs/sandbox-ux-redesign.md (TRIG-1 to TRIG-7, B1).

/** Chooses an option of a module or field picker (a combobox). */
async function choose(page: Page, picker: string, option: string) {
  await page.getByRole("combobox", { name: picker, exact: true }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

async function openTriggers(page: Page, design?: Design) {
  const sandbox = await openAuthenticatedSandbox(page, design);
  await page.getByRole("link", { name: "Triggers", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Trigger details" }),
  ).toBeVisible();
  return sandbox;
}

/** Three triggers, one Off, with different events and a long name. */
const listDesign: Design = {
  ...configuredSandboxDesign,
  rules: [
    ...configuredSandboxDesign.rules,
    {
      id: "sample-weekly",
      name: "Weekly maintenance review",
      trigger: "Schedule",
      condition: "Always",
      action: "Update a field",
      enabled: false,
    },
    {
      id: "sample-status",
      name: "Flag status changes for the operations follow-up review",
      trigger: "Field change",
      condition: "Status is open",
      action: "Update a field",
      enabled: true,
    },
  ],
};

test("a select condition offers option labels and stores the option ID", async ({
  page,
}) => {
  const sandbox = await openTriggers(page);
  const settings = page.getByRole("region", { name: "Trigger details" });
  await choose(page, "Condition 1 field", "Status, Choice list");
  await settings
    .getByLabel("Value", { exact: true })
    .first()
    .selectOption({ label: "In progress" });
  // The whole-trigger sentence names the choice by its label.
  await expect(settings).toHaveAccessibleDescription(
    /, if Status is In progress,/,
  );

  await page.getByRole("button", { name: "Save triggers" }).click();
  await expect.poll(sandbox.documentWrites).toBe(1);
  await expect(page.getByText("Triggers saved", { exact: true })).toBeVisible();
  const document = sandbox.document();
  const condition = document.triggers[0]!.conditionGroup.conditions[0]!;
  const status = document.design.modules
    .flatMap((modulePicker) => modulePicker.fields)
    .find((field) => field.id === condition.field.fieldId);
  if (status?.config.kind !== "select")
    throw new Error("The condition field is not a select field");
  const inProgress = status.config.options.find(
    (option) => option.label === "In progress",
  );
  expect(condition.value).toEqual({ kind: "literal", value: inProgress!.id });
});

test("unsaved triggers show their count and hold Review and Publish", async ({
  page,
}) => {
  await openTriggers(page);
  await expect(page.getByText(/unsaved trigger/)).toHaveCount(0);
  await page.getByLabel("Trigger name").fill("Renamed trigger");
  await expect(page.getByText(/· 1 unsaved trigger change$/)).toBeVisible();
  const publish = page.getByRole("button", { name: "Review & Publish" });
  await expect(publish).toHaveAttribute("aria-disabled", "true");
  await expect(publish).toHaveAccessibleDescription(
    "Save trigger changes first.",
  );
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(page.getByText(/unsaved trigger/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save triggers" })).toHaveCount(
    0,
  );
  // Discard can be undone from its notice.
  await expect(
    page.getByText("Changes discarded", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.getByLabel("Trigger name")).toHaveValue("Renamed trigger");
  await expect(page.getByText(/· 1 unsaved trigger change$/)).toBeVisible();
});

test("leaving with unsaved triggers asks Save, Discard, or Stay", async ({
  page,
}) => {
  const sandbox = await openTriggers(page);
  const build = page.getByRole("link", { name: "Build", exact: true });
  const dialog = page.getByRole("dialog", { name: "Unsaved trigger changes" });

  await page.getByLabel("Trigger name").fill("Stay with me");
  await build.click();
  await expect(dialog).toContainText("Discard removes 1 unsaved change.");
  // The named close button stays, like Stay.
  await dialog
    .getByRole("button", { name: "Close and stay", exact: true })
    .click();
  await expect(dialog).toBeHidden();
  await expect(page.getByLabel("Trigger name")).toHaveValue("Stay with me");
  await build.click();
  await dialog.getByRole("button", { name: "Stay", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL(/section=triggers/);
  await expect(page.getByLabel("Trigger name")).toHaveValue("Stay with me");

  await build.click();
  await dialog
    .getByRole("button", { name: "Save and leave", exact: true })
    .click();
  await expect(page).toHaveURL(/section=build/);
  expect(sandbox.documentWrites()).toBe(1);
  expect(sandbox.document().triggers[0]!.name).toBe("Stay with me");

  await page.getByRole("link", { name: "Triggers", exact: true }).click();
  await page.getByLabel("Trigger name").fill("Not kept");
  await build.click();
  await dialog.getByRole("button", { name: "Discard", exact: true }).click();
  await expect(page).toHaveURL(/section=build/);
  expect(sandbox.documentWrites()).toBe(1);
  expect(sandbox.document().triggers[0]!.name).toBe("Stay with me");
});

test("Back from Triggers keeps unsaved trigger edits", async ({ page }) => {
  const sandbox = await openTriggers(page);
  await page.getByLabel("Trigger name").fill("Kept on Back");
  await page.goBack();
  await expect(page).not.toHaveURL(/section=triggers/);
  // The edit is still waiting to be saved, not lost.
  await expect(page.locator("[data-sandbox-save-state]")).toHaveText(
    /· 1 unsaved trigger change$/,
  );
  await page.getByRole("link", { name: "Triggers", exact: true }).click();
  await expect(page.getByLabel("Trigger name")).toHaveValue("Kept on Back");
  expect(sandbox.documentWrites()).toBe(0);
});

test("a reload offers to restore unsaved trigger edits", async ({ page }) => {
  const sandbox = await openTriggers(page);
  const name = page.getByLabel("Trigger name");
  await name.fill("Survives reload");
  page.on("dialog", (dialog) => void dialog.accept());
  await page.reload();
  const prompt = page
    .getByRole("status")
    .filter({ hasText: "Restore unsaved trigger changes?" });
  // Nothing can be typed over the kept edits while the prompt waits.
  await expect(name).toBeDisabled();
  await expect(
    page.getByRole("switch", { name: "Trigger status" }),
  ).toBeDisabled();
  await prompt
    .getByRole("button", { name: "Restore trigger changes", exact: true })
    .click();
  await expect(prompt).toHaveCount(0);
  await expect(name).toBeEnabled();
  await expect(name).toHaveValue("Survives reload");
  await expect(page.locator("[data-sandbox-save-state]")).toHaveText(
    /· 1 unsaved trigger change$/,
  );

  // While the prompt waits, publishing waits too.
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Review & Publish" }),
  ).toHaveAccessibleDescription("Restore or discard trigger changes first.");
  // Discard can be undone from its notice: the prompt comes back.
  await prompt.getByRole("button", { name: "Discard", exact: true }).click();
  await expect(name).toHaveValue("Urgent request alert");
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(prompt).toBeVisible();
  await expect(name).toBeDisabled();
  // Discard again, then a reload offers nothing.
  await prompt.getByRole("button", { name: "Discard", exact: true }).click();
  await page.reload();
  await expect(name).toHaveValue("Urgent request alert");
  await expect(prompt).toHaveCount(0);
  expect(sandbox.documentWrites()).toBe(0);
});

test("Undo of a discarded prompt never replaces newer trigger edits", async ({
  page,
}) => {
  await openTriggers(page);
  const name = page.getByLabel("Trigger name");
  await name.fill("Older edit");
  page.on("dialog", (dialog) => void dialog.accept());
  await page.reload();
  const prompt = page
    .getByRole("status")
    .filter({ hasText: "Restore unsaved trigger changes?" });
  await prompt.getByRole("button", { name: "Discard", exact: true }).click();
  await name.fill("Newer edit");
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  // The prompt is back, the newer edit stays, and Restore waits for it.
  await expect(prompt).toBeVisible();
  await expect(name).toHaveValue("Newer edit");
  await expect(
    prompt.getByRole("button", {
      name: "Restore trigger changes",
      exact: true,
    }),
  ).toHaveAccessibleDescription(
    "Save or discard your current trigger edits first.",
  );
  // The newer edit stays editable, so it can be resolved here.
  await expect(name).toBeEnabled();
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(name).toBeDisabled();
  await expect(
    prompt.getByRole("button", {
      name: "Restore trigger changes",
      exact: true,
    }),
  ).toBeEnabled();
  // The kept edit is still stored: a reload offers it, and Restore applies it.
  await page.reload();
  await prompt
    .getByRole("button", { name: "Restore trigger changes", exact: true })
    .click();
  await expect(name).toHaveValue("Older edit");
});

test("unsaved triggers are marked, a step Save will refuse warns first, and Ctrl+S saves", async ({
  page,
}) => {
  const sandbox = await openTriggers(page);
  const list = page.getByRole("navigation", { name: "Trigger list" });
  const condition = page.getByRole("group", { name: "Condition 1" });
  await expect(list.getByText("Unsaved", { exact: true })).toHaveCount(0);

  // A required field with no value: the condition says so before Save.
  await choose(page, "Condition 1 field", "Request number, Text");
  await expect(list.getByText("Unsaved", { exact: true })).toHaveCount(1);
  await expect(condition).toHaveAccessibleDescription(
    "Request number is required.",
  );

  await choose(page, "Condition 1 field", "Title, Text");
  await expect(condition).not.toContainText("is required");
  await page.keyboard.press("ControlOrMeta+s");
  await expect.poll(sandbox.documentWrites).toBe(1);
  await expect(list.getByText("Unsaved", { exact: true })).toHaveCount(0);
  // With nothing unsaved, the shortcut writes nothing.
  await page.keyboard.press("ControlOrMeta+s");
  expect(sandbox.documentWrites()).toBe(1);
});

test("a failed trigger save keeps the edits when the shared draft reloads", async ({
  page,
}) => {
  await openAuthenticatedSandbox(page, undefined, {
    saveFailure: "Sandbox storage is unavailable.",
  });
  await page.getByRole("link", { name: "Triggers", exact: true }).click();
  await page.getByLabel("Trigger name").fill("Not lost");
  await page.getByRole("button", { name: "Save triggers" }).click();
  const reload = page.getByRole("button", { name: "Reload shared draft" });
  await reload.click();
  await expect(reload).toHaveCount(0);
  await expect(page.getByLabel("Trigger name")).toHaveValue("Not lost");
  await expect(page.locator("[data-sandbox-save-state]")).toHaveText(
    /· 1 unsaved trigger change$/,
  );
});

test("deleting a trigger can be undone from its notice", async ({ page }) => {
  const sandbox = await openTriggers(page);
  const list = page.getByRole("navigation", { name: "Trigger list" });
  const name = sandbox.document().triggers[0]!.name;
  await expect(list.getByRole("button", { name })).toBeVisible();

  await page.getByRole("button", { name: "Trigger options" }).click();
  await page.getByRole("menuitem", { name: "Delete trigger" }).click();
  await expect(list.getByRole("button", { name })).toHaveCount(0);
  // The only trigger is gone, so focus lands on New trigger, not the page.
  await expect(page.getByRole("button", { name: "New trigger" })).toBeFocused();
  const notice = page.getByText("Trigger deleted", { exact: true });
  await expect(notice).toBeVisible();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(list.getByRole("button", { name })).toHaveAttribute(
    "aria-current",
    "true",
  );
  await expect(list.getByRole("button", { name })).toBeFocused();
  await expect(page.getByText(/unsaved trigger/)).toHaveCount(0);
  expect(sandbox.documentWrites()).toBe(0);
});

// Phase 8 (S25): an Undo ends when the triggers save, and a discard's Undo
// also ends at the next edit, so an old notice never brings back a saved
// deletion or replaces newer work.
test("an old Undo never brings back a saved deletion or replaces a newer edit", async ({
  page,
}) => {
  const sandbox = await openTriggers(page);
  const list = page.getByRole("navigation", { name: "Trigger list" });
  const notices = page.getByRole("region", {
    name: "Status messages",
    exact: true,
  });
  const name = sandbox.document().triggers[0]!.name;

  await page.getByRole("button", { name: "Trigger options" }).click();
  await page.getByRole("menuitem", { name: "Delete trigger" }).click();
  await expect(notices.getByText("Trigger deleted")).toBeVisible();
  await page.getByRole("button", { name: "Save triggers" }).click();
  await expect.poll(sandbox.documentWrites).toBe(1);
  await expect(notices.getByText("Triggers saved")).toBeVisible();
  // The save closes the notice: no Undo is offered (S26).
  await expect(
    notices.getByRole("button", { name: "Undo", exact: true }),
  ).toHaveCount(0);
  await expect(list.getByRole("button", { name })).toHaveCount(0);
  await expect(page.getByText(/unsaved trigger/)).toHaveCount(0);
  expect(sandbox.document().triggers).toHaveLength(0);
});

test("a discard's Undo ends at the next edit", async ({ page }) => {
  await openTriggers(page);
  const notices = page.getByRole("region", {
    name: "Status messages",
    exact: true,
  });
  const triggerName = page.getByLabel("Trigger name");
  await triggerName.fill("Discarded edit");
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(notices.getByText("Changes discarded")).toBeVisible();
  await triggerName.fill("Newer edit");
  // The edit closes the notice: no Undo is offered (S26).
  await expect(
    notices.getByRole("button", { name: "Undo", exact: true }),
  ).toHaveCount(0);
  await expect(triggerName).toHaveValue("Newer edit");
  await expect(page.getByText(/· 1 unsaved trigger change$/)).toBeVisible();
});

// B1 rule c and T8: a new trigger starts empty (UXD-7), and Save checks it
// in the browser first: no request, the save bar names the first missing
// part, the row says Incomplete, and focus lands on the empty control.
test(
  "Save refuses an incomplete trigger with no request and points at its empty part",
  { tag: ["@UX-C18", "@UX-C15", "@UX-C21"] },
  async ({ page }) => {
    const sandbox = await openTriggers(page);
    const list = page.getByRole("navigation", { name: "Trigger list" });
    const detail = page.getByRole("region", { name: "Trigger details" });
    const modulePicker = page.getByRole("combobox", {
      name: "Event module",
      exact: true,
    });
    await page
      .getByRole("button", { name: "New trigger", exact: true })
      .click();
    // Module empty and focused; the sentence reads the missing parts, and
    // no required-value note shows as the trigger opens.
    await expect(modulePicker).toBeFocused();
    await expect(detail).not.toContainText("is required");
    await expect(modulePicker).toHaveText(/Choose a module/);
    await expect(detail).toHaveAccessibleDescription(
      "When a record is added to a module, no action yet.",
    );

    await page.getByRole("button", { name: "Save triggers" }).click();
    await expect(
      page.getByText("1 trigger is incomplete; choose a module.", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      list
        .getByRole("button", { name: /New trigger/ })
        .getByText("Incomplete", { exact: true }),
    ).toBeVisible();
    await expect(modulePicker).toBeFocused();
    expect(sandbox.documentWrites()).toBe(0);

    // Modules are grouped by department, with their field counts.
    await modulePicker.click();
    await expect(
      page.getByRole("group", { name: "Commercial" }).getByRole("option", {
        name: "Customers, 4 fields",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("option", { name: "Service requests, 4 fields", exact: true })
      .click();
    await expect(
      page.getByText("1 trigger is incomplete; add an action.", {
        exact: true,
      }),
    ).toBeVisible();

    // Then offers Set a field only; the new action starts with no field.
    const then = page.getByRole("region", { name: "Then", exact: true });
    await then.getByRole("button", { name: "Add action" }).click();
    const action = then.getByRole("group", { name: "Action 1" });
    await expect(action).toHaveAccessibleDescription("Choose a field.");
    // A chosen field with a required, empty value: Save still refuses it.
    await choose(page, "Set field target", "Request number, Text");
    await expect(action).toHaveAccessibleDescription(
      "Request number is required.",
    );
    await page.getByRole("button", { name: "Save triggers" }).click();
    expect(sandbox.documentWrites()).toBe(0);

    await action.getByRole("textbox").fill("R-100");
    await page.getByRole("button", { name: "Save triggers" }).click();
    await expect.poll(sandbox.documentWrites).toBe(1);
    await expect(list.getByText("Incomplete", { exact: true })).toHaveCount(0);
  },
);

test(
  "Save in the leave dialog refuses an incomplete trigger and stays open",
  { tag: "@UX-C18" },
  async ({ page }) => {
    const sandbox = await openTriggers(page);
    const dialog = page.getByRole("dialog", {
      name: "Unsaved trigger changes",
    });
    await page
      .getByRole("button", { name: "New trigger", exact: true })
      .click();
    await page.getByRole("link", { name: "Build", exact: true }).click();
    await dialog
      .getByRole("button", { name: "Save and leave", exact: true })
      .click();
    await expect(dialog).toContainText(
      "1 trigger is incomplete; choose a module.",
    );
    await expect(dialog).toBeVisible();
    await expect(page).toHaveURL(/section=triggers/);
    expect(sandbox.documentWrites()).toBe(0);
  },
);

test(
  "the structure region shows the module's fields, types and links beside the editor",
  { tag: "@UX-C14" },
  async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const sandbox = await openTriggers(page);
    await page.getByLabel("Trigger name").fill("Edited alert");
    const region = page.getByRole("complementary", { name: "Structure" });
    await expect(region).toBeVisible();
    await expect(region).toContainText("Service requests");
    await expect(region).toContainText("Operations");
    await expect(
      region.getByRole("listitem").filter({ hasText: "Title" }),
    ).toContainText("Text");
    await expect(
      region.getByRole("listitem").filter({ hasText: "Status" }),
    ).toContainText("Choice list");
    await expect(
      region.getByRole("listitem").filter({ hasText: "Equipment" }),
    ).toContainText("Links to");
    // Beside the editor, not instead of it; the unsaved edit stays.
    const editor = await page
      .getByRole("region", { name: "Trigger details" })
      .boundingBox();
    expect((await region.boundingBox())!.x).toBeGreaterThan(
      editor!.x + editor!.width,
    );
    await expect(page.getByLabel("Trigger name")).toHaveValue("Edited alert");
    await expect(page.locator("[data-sandbox-save-state]")).toHaveText(
      /· 1 unsaved trigger change$/,
    );
    await expect(page).toHaveURL(/section=triggers/);
    expect(sandbox.documentWrites()).toBe(0);
  },
);

// The list row rule (Product Designer, PR1 gate R5): status 2.75rem, the
// name the only part that clips (8rem floor), one badge on a second line
// under the name, and the event as its 16px icon at every width.
test(
  "trigger list rows fit their pane with one badge under the name and the event as an icon",
  { tag: "@UX-C18" },
  async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openTriggers(page, listDesign);
    const list = page.getByRole("navigation", { name: "Trigger list" });
    const rows = list.getByRole("button");
    const newRow = rows.filter({ hasText: "New trigger" });
    const longName = list.getByText(
      "Flag status changes for the operations follow-up review",
      { exact: true },
    );
    const fits = async (locator: typeof list) =>
      locator.evaluate((element) => element.scrollWidth - element.clientWidth);
    const close = (actual: number, expected: number) =>
      expect(Math.abs(actual - expected)).toBeLessThanOrEqual(1);
    async function checkRows(unmarked: number, marked: number) {
      expect(await fits(list)).toBe(0);
      for (const row of await rows.all()) {
        expect(await fits(row)).toBe(0);
        const box = (await row.boundingBox())!;
        const badged =
          (await row.getByText(/^(Unsaved|Incomplete)$/).count()) > 0;
        close(box.height, badged ? marked : unmarked);
        // Status cell 2.75rem; the event is a 16px icon inside the row.
        close((await row.getByText(/^(On|Off)$/).boundingBox())!.width, 44);
        const icon = (await row.locator("svg").boundingBox())!;
        close(icon.width, 16);
        close(icon.height, 16);
        expect(icon.x + icon.width).toBeLessThanOrEqual(box.x + box.width);
        // No event word shows; it stays for assistive technology.
        const word = row.getByText(/^(Record added|Schedule|Field changed)$/);
        expect((await word.boundingBox())!.width).toBeLessThanOrEqual(1);
      }
      // The name never drops below 8rem, and a long name ends in an ellipsis.
      const name = (await longName.boundingBox())!;
      expect(name.width).toBeGreaterThanOrEqual(128);
      expect(await fits(longName)).toBeGreaterThan(0);
    }
    async function checkBadge(word: "Unsaved" | "Incomplete") {
      const other = word === "Unsaved" ? "Incomplete" : "Unsaved";
      await expect(newRow.getByText(word, { exact: true })).toHaveCount(1);
      await expect(newRow.getByText(other, { exact: true })).toHaveCount(0);
      const badge = (await newRow
        .getByText(word, { exact: true })
        .boundingBox())!;
      const name = (await newRow
        .getByText("New trigger", { exact: true })
        .boundingBox())!;
      const row = (await newRow.boundingBox())!;
      close(badge.x, name.x);
      expect(badge.y).toBeGreaterThanOrEqual(name.y + name.height);
      expect(badge.x + badge.width).toBeLessThanOrEqual(row.x + row.width);
      expect(badge.y + badge.height).toBeLessThanOrEqual(row.y + row.height);
    }

    // T2: a new trigger is Unsaved only.
    await page
      .getByRole("button", { name: "New trigger", exact: true })
      .click();
    await checkBadge("Unsaved");
    // T8: Save refuses it; the row is Incomplete only.
    await page.getByRole("button", { name: "Save triggers" }).click();
    await checkBadge("Incomplete");
    await expect(newRow).toHaveAccessibleName(
      "On, New trigger, Record added, Incomplete",
    );

    for (const size of [
      { width: 1280, height: 720 },
      { width: 1440, height: 900 },
      { width: 1600, height: 900 },
    ]) {
      await page.setViewportSize(size);
      await checkRows(40, 64);
      await checkBadge("Incomplete");
    }
    // No page scroll at 1280×720.
    await page.setViewportSize({ width: 1280, height: 720 });
    expect(
      await page.evaluate(
        () =>
          document.scrollingElement!.scrollHeight -
          document.scrollingElement!.clientHeight,
      ),
    ).toBeLessThanOrEqual(0);
    // The event word still finds rows.
    await page
      .getByRole("searchbox", { name: "Search triggers" })
      .fill("added");
    await expect(rows).toHaveCount(2);
    await page.getByRole("searchbox", { name: "Search triggers" }).fill("");

    // On a phone: 52px rows, 76px with a badge.
    await page.setViewportSize({ width: 390, height: 844 });
    // Narrowing mid-edit keeps the trigger in view; Back shows the list.
    await page
      .getByRole("button", { name: "Back to Triggers", exact: true })
      .click();
    await expect(list).toBeVisible();
    await checkRows(52, 76);
  },
);

test(
  "on a phone, picker options are 44px tall",
  { tag: "@UX-C15" },
  async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const sandbox = await openAuthenticatedSandbox(page);
    await page.goto("/sandbox?section=triggers");
    await page
      .getByRole("navigation", { name: "Trigger list" })
      .getByRole("button", { name: sandbox.document().triggers[0]!.name })
      .click();
    await page
      .getByRole("combobox", { name: "Condition 1 field", exact: true })
      .click();
    // The picker's own list: closed native selects on the page (Event,
    // operator) hold options of their own.
    const options = page.getByRole("listbox").getByRole("option");
    await expect(options).toHaveCount(4);
    await settled(page);
    for (const option of await options.all())
      expect((await option.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  },
);

test(
  "on a phone the module's fields open as a sheet one action away",
  { tag: "@UX-C14" },
  async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const sandbox = await openAuthenticatedSandbox(page);
    await page.goto("/sandbox?section=triggers");
    const name = sandbox.document().triggers[0]!.name;
    await page
      .getByRole("navigation", { name: "Trigger list" })
      .getByRole("button", { name })
      .click();
    await page.getByLabel("Trigger name").fill("Edited on a phone");
    await expect(
      page.getByRole("complementary", { name: "Structure" }),
    ).toBeHidden();
    const open = page.getByRole("button", {
      name: "Service requests fields",
      exact: true,
    });
    expect((await open.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await open.click();
    const sheet = page.getByRole("dialog", { name: "Service requests" });
    await expect(sheet).toContainText("Request number");
    await expect(sheet).toContainText("Choice list");
    await sheet.getByRole("button", { name: "Close", exact: true }).click();
    await expect(sheet).toBeHidden();
    await expect(open).toBeFocused();
    await expect(page.getByLabel("Trigger name")).toHaveValue(
      "Edited on a phone",
    );
    expect(sandbox.documentWrites()).toBe(0);
  },
);

test("on a phone, choosing a trigger shows its detail first, with Back", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const sandbox = await openAuthenticatedSandbox(page);
  await page.goto("/sandbox?section=triggers");
  const list = page.getByRole("navigation", { name: "Trigger list" });
  const detail = page.getByRole("region", { name: "Trigger details" });
  const name = sandbox.document().triggers[0]!.name;
  await expect(list).toBeVisible();
  await expect(detail).toBeHidden();

  await list.getByRole("button", { name }).click();
  await expect(list).toBeHidden();
  const heading = page.getByRole("heading", { name, level: 2 });
  await expect(heading).toBeFocused();
  // The page title and the heading show whole, below the sticky app bar.
  await expectBelowAppBar(page, page.getByRole("heading", { level: 1 }));
  await expectBelowAppBar(page, heading);
  // The whole-trigger sentence describes the detail.
  await expect(detail).toHaveAccessibleDescription(
    /^When a record is added to Service requests/,
  );
  await expect(detail.getByLabel("Trigger name")).toBeVisible();
  // The Status switch has a tap target past its box: a click 20 px to its
  // right toggles it.
  const status = detail.getByRole("switch", { name: "Trigger status" });
  const checked = await status.getAttribute("aria-checked");
  await clickBesideBox(page, status);
  await expect(status).toHaveAttribute(
    "aria-checked",
    checked === "true" ? "false" : "true",
  );

  await page
    .getByRole("button", { name: "Back to Triggers", exact: true })
    .click();
  await expect(list.getByRole("button", { name })).toBeFocused();
});

test("the trigger list shows 40px rows with a state word, and All, On and Off filter it", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openTriggers(page, listDesign);
  const list = page.getByRole("navigation", { name: "Trigger list" });
  const rows = list.getByRole("button");
  await expect(rows).toHaveCount(3);
  for (const row of await rows.all()) {
    await expect(row).toContainText(/^(On|Off)/);
    expect((await row.boundingBox())!.height).toBeCloseTo(40, 0);
  }
  const weekly = list.getByRole("button", { name: /Weekly maintenance/ });
  await expect(weekly).toContainText("Off");
  await expect(weekly).toContainText("Schedule");
  // A long name stays on one line, and its full text is still there.
  await expect(
    list.getByText("Flag status changes for the operations follow-up review", {
      exact: true,
    }),
  ).toHaveAttribute(
    "title",
    "Flag status changes for the operations follow-up review",
  );

  const status = page.getByRole("group", { name: "Status", exact: true });
  await expect(status.getByRole("button", { pressed: true })).toHaveText(
    "All 3",
  );
  await status.getByRole("button", { name: /^Off/ }).click();
  await expect(rows).toHaveCount(1);
  await expect(weekly).toBeVisible();
  await status.getByRole("button", { name: /^On/ }).click();
  await expect(rows).toHaveCount(2);
  await expect(weekly).toHaveCount(0);

  // The search narrows the rows; the counts stay the whole list.
  await status.getByRole("button", { name: /^All/ }).click();
  await page.getByRole("searchbox", { name: "Search triggers" }).fill("flag");
  await expect(rows).toHaveCount(1);
  await expect(status.getByRole("button", { name: /^On/ })).toHaveText("On 2");
});

test("Status says On or Off beside its switch, and the list row follows", async ({
  page,
}) => {
  const sandbox = await openTriggers(page, listDesign);
  const list = page.getByRole("navigation", { name: "Trigger list" });
  await list.getByRole("button", { name: /Weekly maintenance/ }).click();
  const toggle = page.getByRole("switch", { name: "Trigger status" });
  await expect(toggle).not.toBeChecked();
  await expect(toggle).toHaveAccessibleDescription(
    "Off · won't run after publish",
  );

  await toggle.click();
  await expect(toggle).toBeChecked();
  await expect(toggle).toHaveAccessibleDescription("On");
  await expect(
    list.getByRole("button", { name: /Weekly maintenance/ }),
  ).toContainText(/^On/);
  expect(sandbox.documentWrites()).toBe(0);
});

test("the rail edits each step in place and the sentence follows", async ({
  page,
}) => {
  const sandbox = await openTriggers(page);
  const detail = page.getByRole("region", { name: "Trigger details" });
  const when = page.getByRole("region", { name: "When", exact: true });
  const ifStep = page.getByRole("region", { name: "If", exact: true });
  const then = page.getByRole("region", { name: "Then", exact: true });
  await expect(detail).toHaveAccessibleDescription(
    /^When a record is added to Service requests,/,
  );
  await expect(then.getByRole("group", { name: "Action 1" })).toBeVisible();
  await then.getByRole("button", { name: "Add action" }).click();
  await expect(then.getByLabel("Set field target")).toBeVisible();

  // The fields live in their step: the event changes the When rows.
  // A new event keeps the module (TRIG-5).
  await when.getByLabel("Event", { exact: true }).selectOption("schedule");
  await expect(detail).toHaveAccessibleDescription(
    /^Every day at 09:00 in Service requests,/,
  );
  await expect(when.getByLabel("Frequency")).toHaveValue("daily");
  await expect(when.getByLabel("Weekday")).toHaveCount(0);
  await when.getByLabel("Frequency").selectOption("weekly");
  await expect(when.getByLabel("Weekday")).toHaveValue("1");
  await expect(detail).toHaveAccessibleDescription(
    /^Every Monday at 09:00 in Service requests,/,
  );

  // All or Any shows only from two conditions.
  await expect(ifStep.getByLabel("Condition group operator")).toHaveCount(0);
  await ifStep.getByRole("button", { name: "Add condition" }).click();
  await expect(
    ifStep.getByRole("group", { name: "Condition 2" }),
  ).toBeVisible();
  await ifStep.getByLabel("Condition group operator").selectOption("any");
  await expect(detail).toHaveAccessibleDescription(/ or a field,/);
  await ifStep.getByRole("button", { name: "Remove condition 2" }).click();
  await expect(ifStep.getByRole("group", { name: "Condition 2" })).toHaveCount(
    0,
  );
  await expect(ifStep.getByLabel("Condition group operator")).toHaveCount(0);
  expect(sandbox.documentWrites()).toBe(0);
});

// With no page-wide attention banner (S18), a 1280×720 trigger detail shows
// its Name, Status and When rows above the Save bar.
test("at 1280×720 the trigger detail shows Name, Status and When above the Save bar", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await openTriggers(page);
  await page.getByLabel("Trigger name").fill("Urgent request alert, edited");
  const save = page.getByRole("button", { name: "Save triggers" });
  await expect(save).toBeVisible();
  const bar = await save.evaluate(
    (button) =>
      button.parentElement!.parentElement!.getBoundingClientRect().top,
  );
  for (const row of [
    page.getByLabel("Trigger name"),
    page.getByRole("switch", { name: "Trigger status" }),
    // Every When row: Event and Module.
    page.getByRole("region", { name: "When", exact: true }),
  ]) {
    await expect(row).toBeInViewport({ ratio: 1 });
    const box = await row.boundingBox();
    expect(box!.y + box!.height).toBeLessThanOrEqual(bar);
  }
});

// The header's attention control announces a new count politely, never on
// the first load; when nothing is left while its list is open, the list
// closes and focus moves to the section title.
test("the attention count is announced when it changes and focus moves to the title at zero", async ({
  page,
}) => {
  const design = structuredClone(configuredSandboxDesign);
  design.rules.push({
    ...structuredClone(design.rules[0]!),
    id: "sample-second",
    name: "Second request alert",
  });
  await openTriggers(page, design);
  const live = page.locator("[data-sandbox-attention-live]");
  const attention = page.getByRole("button", { name: /needs? attention$/ });
  await expect(attention).toHaveText("2 need attention");
  await expect(live).toHaveText("");

  // Replacing the first trigger's notification with Set field and saving
  // drops the count to one.
  const then = page.getByRole("region", { name: "Then", exact: true });
  await then.getByRole("button", { name: "Add action" }).click();
  await choose(page, "Set field target", "Title, Text");
  await then.getByRole("button", { name: "Remove action 1" }).click();
  await then.getByRole("textbox").fill("Follow up");
  await page.getByRole("button", { name: "Save triggers" }).click();
  await expect(attention).toHaveText("1 needs attention");
  await expect(live).toHaveText("1 needs attention");

  // Fix the second, open the list from the keyboard, and save with Ctrl+S.
  await page
    .getByRole("navigation", { name: "Trigger list" })
    .getByRole("button", { name: /Second request alert/ })
    .click();
  await then.getByRole("button", { name: "Add action" }).click();
  await choose(page, "Set field target", "Title, Text");
  await then.getByRole("button", { name: "Remove action 1" }).click();
  await then.getByRole("textbox").fill("Follow up");
  await attention.focus();
  await page.keyboard.press("Enter");
  const list = page.getByRole("dialog", { name: "Needs attention" });
  await expect(
    list.getByRole("button", { name: "Open trigger" }),
  ).toBeFocused();
  await page.keyboard.press("ControlOrMeta+s");
  await expect(attention).toHaveCount(0);
  await expect(list).toBeHidden();
  await expect(
    page.getByRole("heading", { level: 1, name: "Triggers" }),
  ).toBeFocused();
  await expect(live).toHaveText("Nothing needs attention");
});

test("opening another trigger starts its detail at the top", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await openTriggers(page, listDesign);
  const add = page.getByRole("button", { name: "Add condition" });
  for (let count = 0; count < 5; count += 1) await add.click();
  await add.scrollIntoViewIfNeeded();
  await expect(page.getByLabel("Trigger name")).not.toBeInViewport();

  await page
    .getByRole("navigation", { name: "Trigger list" })
    .getByRole("button", { name: /Weekly maintenance/ })
    .click();
  await expect(page.getByLabel("Trigger name")).toHaveValue(
    "Weekly maintenance review",
  );
  await expect(page.getByLabel("Trigger name")).toBeInViewport();
});

test("opening another trigger keeps unsaved edits, marked and counted, without a write", async ({
  page,
}) => {
  const sandbox = await openTriggers(page, listDesign);
  const list = page.getByRole("navigation", { name: "Trigger list" });
  const name = page.getByLabel("Trigger name");
  await name.fill("Urgent request alert, edited");
  await list.getByRole("button", { name: /Weekly maintenance/ }).click();
  await expect(name).toHaveValue("Weekly maintenance review");

  const edited = list.getByRole("button", { name: /edited/ });
  await expect(edited).toContainText("Unsaved");
  await expect(
    page.getByText("1 unsaved change", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save triggers" }),
  ).toBeVisible();
  await expect(page.locator("[data-sandbox-save-state]")).toHaveText(
    /· 1 unsaved trigger change$/,
  );
  await edited.click();
  await expect(name).toHaveValue("Urgent request alert, edited");
  expect(sandbox.documentWrites()).toBe(0);
});

// TRIG-8: "New trigger" in a module's item menu in Build opens Triggers with
// a new trigger on that module: the module chosen, the event next.

/** Triggers opened from Build with a new, unsaved trigger on `module`. */
async function expectNewTriggerOn(page: Page, module: string, fields: number) {
  const detail = page.getByRole("region", { name: "Trigger details" });
  await expect(detail).toBeVisible();
  await expect(page).toHaveURL(/section=triggers/);
  // The one-time request leaves the address once Triggers has used it.
  await expect(page).not.toHaveURL(/new-trigger/);
  await expect(
    page.getByRole("combobox", { name: "Event module", exact: true }),
  ).toHaveText(new RegExp(module));
  await expect(
    page.getByRole("combobox", { name: "Event", exact: true }),
  ).toBeFocused();
  await expect(detail).toHaveAccessibleDescription(
    `When a record is added to ${module}, no action yet.`,
  );
  // The structure region shows that module, not the whole design.
  await expect(
    page
      .getByRole("complementary", { name: "Structure" })
      .getByRole("heading", { name: `Fields ${fields}`, exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "Trigger list" })
      .getByRole("button", { name: "On, New trigger, Record added, Unsaved" }),
  ).toBeVisible();
}

// T8-C1
test("New trigger in a module's canvas menu opens Triggers with that module chosen", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const sandbox = await openAuthenticatedSandbox(page);
  await page.locator('[data-sandbox-node="sample-customers"]').click({
    button: "right",
    position: { x: 40, y: 12 },
  });
  await page
    .getByRole("menu", { name: "Actions for module Customers" })
    .getByRole("menuitem", { name: "New trigger", exact: true })
    .click();
  await expectNewTriggerOn(page, "Customers", 4);
  // The saved trigger stays; nothing is saved until Save triggers.
  await expect(
    page
      .getByRole("navigation", { name: "Trigger list" })
      .getByRole("button", { name: /Urgent request alert/ }),
  ).toBeVisible();
  expect(sandbox.documentWrites()).toBe(0);
});

// T8-C1
test("New trigger in a module's Structure menu opens Triggers from the keyboard", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const sandbox = await openAuthenticatedSandbox(page);
  await page
    .getByRole("tablist", { name: "Workbench view" })
    .getByRole("tab", { name: "Structure" })
    .click();
  const row = page
    .getByRole("complementary", { name: "Organization structure" })
    .getByRole("treeitem", { name: "Customers", exact: true });
  await row.focus();
  await page.keyboard.press("Shift+F10");
  const menu = page.getByRole("menu", { name: "Actions for module Customers" });
  await expect(menu).toBeVisible();
  // New trigger sits just above Delete module, the last item.
  await page.keyboard.press("End");
  await page.keyboard.press("ArrowUp");
  await expect(
    menu.getByRole("menuitem", { name: "New trigger", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expectNewTriggerOn(page, "Customers", 4);
  expect(sandbox.documentWrites()).toBe(0);
});

// T8-C1, N1 rule 5
test("New trigger waits for a held Build save, then opens on the module it added", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openAuthenticatedSandbox(page);
  let confirm: () => void = () => {};
  await page.route("**/api/sandbox/document", async (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    const body = route.request().postDataJSON() as {
      document: SandboxDocumentV4;
    };
    await new Promise<void>((resolve) => {
      confirm = resolve;
    });
    await route.fulfill({
      headers: answeredHeaders,
      json: {
        document: body.document,
        revision: 2,
        contentHash: "b".repeat(64),
        byteCount: JSON.stringify(body.document).length,
        issues: [],
        latestPublishedVersion: null,
        publishedHash: null,
        hasUnpublishedChanges: true,
      },
    });
  });
  await page
    .getByRole("tablist", { name: "Workbench view" })
    .getByRole("tab", { name: "Structure" })
    .click();
  const structure = page.getByRole("complementary", {
    name: "Organization structure",
  });
  await structure
    .getByRole("treeitem", { name: "Add module to Commercial", exact: true })
    .click();
  await addInEntry(createEntry(page, "Add module to Commercial"), ["Invoices"]);
  // The add is held: its save has not returned.
  const added = structure.getByRole("treeitem", {
    name: "Invoices",
    exact: true,
  });
  await expect(added).toBeVisible();
  await added.click({ button: "right" });
  await page
    .getByRole("menu", { name: "Actions for module Invoices" })
    .getByRole("menuitem", { name: "New trigger", exact: true })
    .click();
  await expect(page.getByRole("menu")).toHaveCount(0);
  // Focus stays on the row that opened the menu while the move waits.
  await expect(added).toBeFocused();
  // Still in Build while the save is held. The end state proves the wait:
  // Triggers reads the saved design, which has Invoices only after the save.
  await expect(page).not.toHaveURL(/section=triggers/);
  await expect(
    page.getByRole("region", { name: "Trigger details" }),
  ).toHaveCount(0);
  await expect(structure).toBeVisible();

  confirm();
  await expectNewTriggerOn(page, "Invoices", 0);
});
