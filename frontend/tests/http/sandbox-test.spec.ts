import { expect, test, type Page } from "./helpers/test";
import { openAuthenticatedSandbox } from "./helpers/sandbox-api";
import {
  initialDesign,
  type Design,
} from "../../src/components/systems/sandbox/domain/model";
import { configuredSandboxDesign } from "../helpers/sandbox-fixtures";
import type { SandboxTrigger } from "../../src/components/systems/sandbox/domain/document";

// Test (docs/specs/sandbox-ux-redesign.md TEST-1 to TEST-9, E1 to E11): a
// reading of the saved draft with no request, and runs only on Try it, Try
// this trigger, Try every event, and Run again. The rules (example values,
// the reading, the TEST-9 fill) are owned by isolated specs; these journeys
// prove the requests, the rendered states, and the refusals.

const ADMINISTRATOR_ID = "00000000-0000-4000-8000-000000000001";
// The draft parser requires a UUID for every choice id.
const OPEN = "00000000-0000-4000-8000-0000000000b1";
const REVIEW = "00000000-0000-4000-8000-0000000000b2";

const ordersDesign: Design = {
  departments: [{ id: "sales", name: "Sales", closed: false }],
  modules: [
    {
      id: "orders",
      department: "sales",
      name: "Orders",
      closed: false,
      x: 0,
      y: 0,
      fields: [
        {
          id: "amount",
          name: "Amount",
          type: "Number",
          required: true,
          value: "1",
          options: "",
          closed: false,
          config: { kind: "number", defaultValue: 1 },
        },
        {
          id: "status",
          name: "Status",
          type: "Select",
          required: true,
          value: OPEN,
          options: "Open, Review",
          closed: false,
          config: {
            kind: "select",
            defaultValue: OPEN,
            options: [
              { id: OPEN, label: "Open" },
              { id: REVIEW, label: "Review" },
            ],
          },
        },
        {
          id: "owner",
          name: "Owner",
          type: "User",
          required: true,
          value: "",
          options: "",
          closed: false,
          config: { kind: "user" },
        },
      ],
    },
  ],
  relationships: [],
  rules: [],
};

const added = { kind: "record-created", moduleId: "orders" } as const;

/** A: "if Amount is at least 100, set Status to Review" (priority 1). */
const flagLargeOrders: SandboxTrigger = {
  id: "flag",
  name: "Flag large orders",
  enabled: true,
  priority: 1,
  trigger: added,
  conditionGroup: {
    operator: "all",
    conditions: [
      {
        id: "flag-amount",
        field: { moduleId: "orders", fieldId: "amount" },
        operator: ">=",
        value: { kind: "literal", value: 100 },
      },
    ],
  },
  actions: [
    {
      id: "flag-status",
      kind: "set-field",
      target: { moduleId: "orders", fieldId: "status" },
      value: { kind: "literal", value: REVIEW },
    },
  ],
};

/** B: "if Status is Open, set Owner" (priority 2). */
const assignOpenOrders: SandboxTrigger = {
  id: "assign",
  name: "Assign open orders",
  enabled: true,
  priority: 2,
  trigger: added,
  conditionGroup: {
    operator: "all",
    conditions: [
      {
        id: "assign-status",
        field: { moduleId: "orders", fieldId: "status" },
        operator: "=",
        value: { kind: "literal", value: OPEN },
      },
    ],
  },
  actions: [
    {
      id: "assign-owner",
      kind: "set-field",
      target: { moduleId: "orders", fieldId: "owner" },
      value: { kind: "literal", value: ADMINISTRATOR_ID },
    },
  ],
};

const salesIsLive = [
  {
    kind: "department" as const,
    sandbox_id: "sales",
    parent_sandbox_id: null,
    live_id: "00000000-0000-4000-8000-0000000000a1",
    is_deleted: false,
  },
];

type RunRequest = {
  moduleId: string;
  values: Record<string, unknown>;
  event: { kind: string };
  triggerIds?: string[] | null;
};

/** Opens Test on Orders and records every Test run request. */
async function openTest(
  page: Page,
  options: {
    design?: Design;
    testRuns?: unknown[];
    testTotal?: number;
    refusal?: (request: RunRequest, index: number) => string | undefined;
    bindings?: typeof salesIsLive;
    hasUnpublishedChanges?: boolean;
  } = {},
) {
  const requests: RunRequest[] = [];
  let runs = 0;
  await openAuthenticatedSandbox(page, options.design ?? ordersDesign, {
    triggers: [flagLargeOrders, assignOpenOrders],
    bindings: options.bindings ?? salesIsLive,
    hasUnpublishedChanges: options.hasUnpublishedChanges,
    testRuns: options.testRuns,
    testTotal: options.testTotal,
    testRunEcho: {
      id: "00000000-0000-4000-8000-000000000031",
      createdAt: "2026-11-10T10:00:00Z",
      onRequest: (request) => {
        requests.push(request);
      },
      refusal: (request) => options.refusal?.(request, runs++),
      // A ran when the values meet its condition: Status becomes Review.
      resultValues: (values) =>
        Number(values.amount) >= 100 ? { ...values, status: REVIEW } : values,
      triggerTraces: (request) => {
        const chosen = request.triggerIds ?? ["flag", "assign"];
        return [
          ...(chosen.includes("flag")
            ? [
                {
                  triggerId: "flag",
                  label: "Flag large orders",
                  outcome:
                    Number(request.values.amount) >= 100
                      ? "Applied"
                      : "Conditions not met",
                },
              ]
            : []),
          ...(chosen.includes("assign")
            ? [
                {
                  triggerId: "assign",
                  label: "Assign open orders",
                  outcome: "Conditions not met",
                },
              ]
            : []),
        ];
      },
    },
  });
  await page.goto("/sandbox?section=test");
  const reading = page.getByRole("region", { name: "Reading", exact: true });
  await expect(reading.getByRole("heading", { name: "Orders" })).toBeVisible();
  return { requests, reading };
}

test(
  "the reading shows each event's triggers and sends no test run on open or module choice",
  { tag: "@UX-C22" },
  async ({ page }) => {
    const posts: string[] = [];
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        new URL(request.url()).pathname === "/api/sandbox/tests"
      )
        posts.push(request.url());
    });
    const { reading } = await openTest(page);
    await page
      .getByRole("region", { name: "Modules" })
      .getByRole("button", { name: /^Orders/ })
      .click();

    await expect(
      reading.getByRole("heading", { name: "When an item is added" }),
    ).toBeVisible();
    await expect(reading.getByText("if Amount is at least 100")).toBeVisible();
    await expect(reading.getByText("if Status is Open")).toBeVisible();
    await expect(
      reading.getByText("Sales · 3 fields · 2 triggers"),
    ).toBeVisible();
    expect(posts).toEqual([]);
  },
);

test(
  "Try this trigger runs that trigger alone with its condition met and says the other did not run",
  { tag: "@UX-C33" },
  async ({ page }) => {
    const { requests, reading } = await openTest(page);
    await reading
      .getByRole("listitem")
      .filter({ hasText: "Flag large orders" })
      .getByRole("button", { name: "Try this trigger" })
      .click();

    const result = reading.getByRole("region", {
      name: "Example item · Flag large orders only",
    });
    await expect(result).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({
      moduleId: "orders",
      event: { kind: "record-created" },
      triggerIds: ["flag"],
      values: { amount: 100, status: OPEN, owner: ADMINISTRATOR_ID },
    });
    await expect(
      result
        .getByRole("region", { name: "Values used" })
        .getByText("Set for this trigger"),
    ).toBeVisible();
    const happened = result.getByRole("region", { name: "What happened" });
    await expect(happened.getByText("Flag large orders ran")).toBeVisible();
    await expect(happened.getByText("Status Open → Review")).toBeVisible();
    await expect(
      happened.getByText("Other triggers on Orders did not run in this test."),
    ).toBeVisible();
  },
);

test(
  "Try it uses the administrator for a Person field, and Change values runs again with the changed value and the checked triggers",
  { tag: ["@UX-C24", "@UX-C25", "@UX-C26"] },
  async ({ page }) => {
    const { requests, reading } = await openTest(page);
    await reading
      .getByRole("button", { name: "Try it: When an item is added" })
      .click();

    const result = reading.getByRole("region", {
      name: "Example item",
      exact: true,
    });
    await expect(result).toBeVisible();
    // No triggerIds: every enabled trigger runs.
    expect(requests[0]?.triggerIds ?? null).toBeNull();
    expect(requests[0]?.values).toEqual({
      amount: 1,
      status: OPEN,
      owner: ADMINISTRATOR_ID,
    });
    const values = result.getByRole("region", { name: "Values used" });
    await expect(values.getByText("signed_in_person")).toBeVisible();
    await expect(
      result
        .getByRole("region", { name: "What happened" })
        .getByText("Amount is 1; it needs at least 100."),
    ).toBeVisible();

    await values.getByRole("button", { name: "Change values" }).click();
    await expect(values.getByLabel("Owner")).toHaveValue(ADMINISTRATOR_ID);
    await values.getByLabel("Amount").fill("150");
    await expect(values.getByText("Edited")).toBeVisible();
    await values.getByRole("checkbox", { name: "Assign open orders" }).click();
    await result.getByRole("button", { name: "Run again" }).click();

    await expect.poll(() => requests.length).toBe(2);
    expect(requests[1]).toMatchObject({
      values: { amount: 150, status: OPEN },
      triggerIds: ["flag"],
    });
    const happened = result.getByRole("region", { name: "What happened" });
    await expect(happened.getByText("Flag large orders ran")).toBeVisible();
    await expect(happened.getByText("Status Open → Review")).toBeVisible();
    await expect(
      happened.getByText("Assign open orders did not run in this test."),
    ).toBeVisible();
  },
);

test(
  "at 49 stored runs the first Try it keeps run 50 and Try then waits for Clear results",
  { tag: "@UX-C27" },
  async ({ page }) => {
    const { requests, reading } = await openTest(page, { testTotal: 49 });
    const modules = page.getByRole("region", { name: "Modules" });
    await expect(modules.getByText("Results 49 of 50")).toBeVisible();
    // Reading added no run.
    expect(requests).toHaveLength(0);
    await expect(
      reading.getByRole("button", { name: /Try every event · 1 run/ }),
    ).toBeEnabled();

    await reading
      .getByRole("button", { name: "Try it: When an item is added" })
      .click();
    await expect(
      reading.getByRole("region", { name: "Example item", exact: true }),
    ).toBeVisible();
    await expect(modules.getByText("Results 50 of 50")).toBeVisible();
    const tryIt = reading.getByRole("button", {
      name: "Try it: When an item is added",
    });
    await expect(tryIt).toHaveAttribute("aria-disabled", "true");
    await expect(tryIt).toHaveAccessibleDescription("Clear results first.");
    await expect(
      modules.getByRole("button", { name: "Clear results" }),
    ).toBeEnabled();
    // No alert in the page content; Next's empty route announcer (also
    // role="alert") sits outside main.
    await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
    expect(requests).toHaveLength(1);
  },
);

test("a refused run for a full store shows the limit, and a changed draft says to reload", async ({
  page,
}) => {
  const { reading } = await openTest(page, {
    testTotal: 10,
    refusal: (_request, index) =>
      index === 0 ? "run_history_full" : "stale_revision",
  });
  await page.route("**/api/sandbox/tests", (route) =>
    route.request().method() === "DELETE"
      ? route.fulfill({ contentType: "application/json", body: "null" })
      : route.fallback(),
  );
  await reading
    .getByRole("button", { name: "Try it: When an item is added" })
    .click();
  await expect(
    page.getByRole("region", { name: "Modules" }).getByText("Results 50 of 50"),
  ).toBeVisible();
  await page
    .getByRole("region", { name: "Modules" })
    .getByRole("button", { name: "Clear results" })
    .click();
  await reading
    .getByRole("button", { name: "Try it: When an item is added" })
    .click();
  // One alert in the page content (Next's route announcer sits outside
  // main); the answered request's reference follows the page's own words.
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Sandbox draft changed; reload before testing.",
  );
});

test(
  "a new department's module points to Review & Publish and lists no setup items",
  { tag: "@UX-C28" },
  async ({ page }) => {
    // A new department is an unpublished change: Review & Publish is open.
    const { reading } = await openTest(page, {
      bindings: [],
      hasUnpublishedChanges: true,
    });
    await expect(reading.getByText("New", { exact: true })).toBeVisible();
    await expect(
      reading.getByText("Review & Publish lists what publishing creates."),
    ).toBeVisible();
    for (const item of ["Groups", "Dashboard", "Board", "Category", "Channel"])
      await expect(reading.getByText(item, { exact: true })).toHaveCount(0);
    await reading.getByRole("button", { name: "Open review" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
  },
);

test("a field whose settings allow no value opens Change values and sends nothing", async ({
  page,
}) => {
  const design = structuredClone(ordersDesign);
  design.modules[0]!.fields.push({
    id: "stage",
    name: "Stage",
    type: "Select",
    required: true,
    value: "",
    options: "",
    closed: false,
    config: { kind: "select", defaultValue: null, options: [] },
  });
  const { requests, reading } = await openTest(page, { design });
  await reading
    .getByRole("button", { name: "Try it: When an item is added" })
    .click();
  const result = reading.getByRole("region", {
    name: "Example item",
    exact: true,
  });
  // The result opens in Change values and takes focus; the field says why,
  // once, under itself (F15, PR1 Product Designer finding).
  await expect(
    result.getByRole("heading", { name: "Example item", exact: true }),
  ).toBeFocused();
  await expect(result.getByLabel("Amount")).toBeVisible();
  await expect(result.getByLabel("Stage")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  await expect(result.getByLabel("Stage")).toHaveAccessibleDescription(
    "Its settings allow no value. Enter one to run.",
  );
  // Run again still waits for the value: nothing is sent.
  await result.getByRole("button", { name: "Run again" }).click();
  await expect(result.getByLabel("Stage")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(requests).toHaveLength(0);
});

test("on a phone, Test is the list, then the reading with a way back, and Try targets are 44 px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAuthenticatedSandbox(page, ordersDesign, {
    triggers: [flagLargeOrders, assignOpenOrders],
    bindings: salesIsLive,
  });
  await page.goto("/sandbox?section=test");
  const modules = page.getByRole("region", { name: "Modules" });
  await modules.getByRole("button", { name: /^Orders/ }).click();
  const reading = page.getByRole("region", { name: "Reading", exact: true });
  await expect(modules).toBeHidden();
  const tryIt = reading.getByRole("button", {
    name: "Try it: When an item is added",
  });
  const box = await tryIt.boundingBox();
  expect(box?.height).toBeGreaterThanOrEqual(44);
  await reading.getByRole("button", { name: "Modules" }).click();
  await expect(modules).toBeVisible();
});

test("no result shows before Try it; a run shows the Test-only chip, and its time reads as History's", async ({
  page,
}) => {
  const { reading } = await openTest(page);
  await expect(
    reading.getByRole("region", { name: /^Example item/ }),
  ).toHaveCount(0);
  await reading
    .getByRole("button", { name: "Try it: When an item is added" })
    .click();
  const result = reading.getByRole("region", {
    name: "Example item",
    exact: true,
  });
  await expect(
    result.getByText("Test only · live data unchanged"),
  ).toBeVisible();
  // The kept run's time reads as History's times do (S26).
  await page
    .getByRole("region", { name: "Modules" })
    .getByRole("button", { name: "Results 1 of 50" })
    .click();
  await expect(
    page
      .getByRole("list", { name: "Recent results" })
      .getByText("Nov 10, 2026, 10:00 AM"),
  ).toBeVisible();
});

test("on a phone, Try it and Try this trigger show their result in the reading and focus it", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAuthenticatedSandbox(page, ordersDesign, {
    triggers: [flagLargeOrders, assignOpenOrders],
    bindings: salesIsLive,
    testRunEcho: {
      id: "00000000-0000-4000-8000-000000000032",
      createdAt: "2026-11-10T10:00:00Z",
    },
  });
  await page.goto("/sandbox?section=test");
  const modules = page.getByRole("region", { name: "Modules" });
  await modules.getByRole("button", { name: /^Orders/ }).click();
  const reading = page.getByRole("region", { name: "Reading", exact: true });
  await reading
    .getByRole("button", { name: "Try it: When an item is added" })
    .click();
  // The result heading takes focus, so the result is read first.
  await expect(
    reading.getByRole("heading", { name: "Example item", exact: true }),
  ).toBeFocused();
  await expect(modules).toBeHidden();
  await reading
    .getByRole("listitem")
    .filter({ hasText: "Flag large orders" })
    .getByRole("button", { name: "Try this trigger" })
    .click();
  await expect(
    reading.getByRole("heading", {
      name: "Example item · Flag large orders only",
    }),
  ).toBeFocused();
});

test("with no module, Test says there is nothing to test and opens Build", async ({
  page,
}) => {
  await openAuthenticatedSandbox(page, initialDesign);
  await page.goto("/sandbox?section=test");
  await expect(
    page.getByRole("heading", { name: "Nothing to test yet" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open Build" }).click();
  await expect(page).not.toHaveURL(/section=test/);
});

function storedRun(
  moduleId: string,
  issues: { code: string; message: string; targetId: string | null }[] = [],
) {
  return {
    id: "00000000-0000-4000-8000-000000000051",
    createdAt: "2026-10-20T09:00:00Z",
    documentRevision: 1,
    input: { moduleId, values: {} },
    event: { kind: "record-created" },
    triggerIds: null,
    result: { values: {}, routes: [], triggerTraces: [], issues },
  };
}

test("a stored result shows only on the module it was run on, opened from the results list", async ({
  page,
}) => {
  await openAuthenticatedSandbox(page, configuredSandboxDesign, {
    testRuns: [storedRun("sample-equipment")],
  });
  await page.goto("/sandbox?section=test");
  const reading = page.getByRole("region", { name: "Reading", exact: true });
  await expect(
    reading.getByRole("heading", { name: "Service requests" }),
  ).toBeVisible();
  await expect(
    reading.getByText("Test only · live data unchanged"),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Results 1 of 50" }).click();
  await page
    .getByRole("list", { name: "Recent results" })
    .getByRole("button")
    .click();
  await expect(
    reading.getByRole("heading", { name: "Equipment" }),
  ).toBeVisible();
  await expect(
    reading.getByText("Test only · live data unchanged"),
  ).toBeVisible();
});

test("no field shows an error before a run, and a run's field issue reads in What happened by its field", async ({
  page,
}) => {
  await openAuthenticatedSandbox(page, configuredSandboxDesign, {
    testRuns: [
      storedRun("sample-requests", [
        {
          code: "value_required",
          message: "Enter a value for this required field.",
          targetId: "sample-field-Request number",
        },
      ]),
    ],
  });
  await page.route("**/api/sandbox/tests", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const request = route.request().postDataJSON() as {
      moduleId: string;
      values: Record<string, unknown>;
      event: unknown;
    };
    await route.fulfill({
      status: 201,
      json: {
        ...storedRun("sample-requests", [
          {
            code: "value_invalid",
            message: "Use letters and numbers only.",
            targetId: "sample-field-Request number",
          },
        ]),
        id: "00000000-0000-4000-8000-000000000052",
        input: { moduleId: request.moduleId, values: request.values },
        event: request.event,
      },
    });
  });
  await page.goto("/sandbox?section=test");
  const reading = page.getByRole("region", { name: "Reading", exact: true });
  await expect(
    reading.getByRole("heading", { name: "Service requests" }),
  ).toBeVisible();
  // The stored issue does not mark the reading before a run.
  await expect(
    reading.getByText("Enter a value for this required field."),
  ).toHaveCount(0);
  await reading
    .getByRole("button", { name: "Try it: When an item is added" })
    .click();
  await expect(
    reading
      .getByRole("region", { name: "What happened" })
      .getByText("Request number: Use letters and numbers only."),
  ).toBeVisible();
});

test("changed values and their Edited marks stay when another module is chosen and the first comes back", async ({
  page,
}) => {
  const design = structuredClone(ordersDesign);
  design.modules.push({
    id: "customers",
    department: "sales",
    name: "Customers",
    closed: false,
    x: 400,
    y: 0,
    fields: [],
  });
  const { reading } = await openTest(page, { design });
  await reading
    .getByRole("button", { name: "Try it: When an item is added" })
    .click();
  const result = reading.getByRole("region", {
    name: "Example item",
    exact: true,
  });
  await result.getByRole("button", { name: "Change values" }).click();
  await result.getByLabel("Amount").fill("150");
  await expect(result.getByText("Edited")).toBeVisible();
  const modules = page.getByRole("region", { name: "Modules" });
  await modules.getByRole("button", { name: /^Customers/ }).click();
  await expect(
    reading.getByRole("heading", { name: "Customers" }),
  ).toBeVisible();
  await modules.getByRole("button", { name: /^Orders/ }).click();
  await expect(result.getByLabel("Amount")).toHaveValue("150");
  await expect(result.getByText("Edited")).toBeVisible();
});

test("from 640 to 1279 px every Test control keeps a 44 px target", async ({
  page,
}) => {
  // The Sandbox uses slim 32 px controls only from 1280 px (xl).
  await page.setViewportSize({ width: 1024, height: 768 });
  const { reading } = await openTest(page);
  const tryIt = reading.getByRole("button", {
    name: "Try it: When an item is added",
  });
  await tryIt.click();
  const result = reading.getByRole("region", {
    name: "Example item",
    exact: true,
  });
  await expect(result).toBeVisible();
  const modules = page.getByRole("region", { name: "Modules" });
  for (const control of [
    tryIt,
    reading.getByRole("button", { name: /^Try every event/ }),
    reading
      .getByRole("listitem")
      .filter({ hasText: "Flag large orders" })
      .getByRole("button", { name: "Try this trigger" }),
    result.getByRole("button", { name: "Show on canvas" }),
    result.getByRole("button", { name: "Change values" }),
    result.getByRole("button", { name: "Run again" }),
    modules.getByRole("button", { name: /^Orders/ }),
    modules.getByRole("button", { name: /^Results/ }),
    modules.getByRole("button", { name: "Clear results" }),
  ]) {
    const box = await control.boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
  }
});

test("on a phone with no module, Test still leads to Build", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAuthenticatedSandbox(page, initialDesign);
  await page.goto("/sandbox?section=test");
  await expect(
    page.getByRole("region", { name: "Modules" }).getByText("No modules yet"),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Nothing to test yet" }),
  ).toBeVisible();
  const openBuild = page.getByRole("button", { name: "Open Build" });
  const box = await openBuild.boundingBox();
  expect(box?.height).toBeGreaterThanOrEqual(44);
  await openBuild.click();
  await expect(page).not.toHaveURL(/section=test/);
});
