import {
  answeredHeaders,
  answeredRequestId,
  expect,
  expectAnsweredReference,
  expectNoHorizontalScroll,
  expectNoPageScroll,
  settleReact,
  signedInAs,
  signedOut,
  test,
  type Page,
} from "./helpers/test";

// DEC-0042: an installation runs before email is set up. Administrators learn
// it from one quiet line in the shell and read the steps in Manage → Email;
// members and guests see neither. The email word comes from the System health
// read (`GET /api/system/status`, part `email`).

const ADMIN = "00000000-0000-4000-8000-000000000001";
const MEMBER = "00000000-0000-4000-8000-000000000301";

type EmailWord = "not_set_up" | "set_up" | "working" | "not_working";

function statusBody(email: EmailWord) {
  return {
    parts: [
      { key: "data", status: "working" },
      { key: "signing_in", status: "working" },
      { key: "files", status: "working" },
      { key: "email", status: email },
    ],
    version: "0.1.0",
    checked_at: "2026-10-06T08:00:00Z",
    organization: null,
    installation: null,
  };
}

/** Answers the status read with the current email word; counts the reads. */
async function routeEmailStatus(page: Page, initial: EmailWord) {
  const state = { email: initial, reads: 0 };
  await page.route(
    (url) => url.pathname === "/api/system/status",
    (route) => {
      state.reads += 1;
      return route.fulfill({
        headers: { "Cache-Control": "no-store" },
        json: statusBody(state.email),
      });
    },
  );
  return state;
}

const notice = (page: Page) => page.locator('[data-slot="email-setup-notice"]');

test("AC-E1 an administrator sees one email notice that links to Manage → Email, and it goes once email is set up", async ({
  page,
}) => {
  await signedInAs(page, { id: ADMIN, role: "admin" });
  const status = await routeEmailStatus(page, "not_set_up");
  await page.goto("/manage?view=organization");

  await expect(notice(page)).toHaveCount(1);
  await expect(notice(page)).toContainText(
    "Email is not set up. Invitations and password emails cannot be sent.",
  );
  const link = notice(page).getByRole("link", {
    name: "How to set up email",
    exact: true,
  });
  await expect(link).toHaveAttribute("href", "/manage?view=email");
  // The notice is in the shell, above the page, and holds no live region.
  await expect(page.getByRole("main").locator(notice(page))).toHaveCount(0);
  await expect(notice(page).locator('[role="status"]')).toHaveCount(0);

  // Email gets set up on the server PC; Manage → Email reads it on open.
  status.email = "set_up";
  await link.click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Email", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Email is set up.", exact: true }),
  ).toBeVisible();
  await expect(notice(page)).toHaveCount(0);

  // Back on another page the notice stays gone, from the same cached read.
  const reads = status.reads;
  await page.goBack();
  await expect(
    page.getByRole("heading", { level: 1, name: "Organization", exact: true }),
  ).toBeVisible();
  await expect(notice(page)).toHaveCount(0);
  expect(status.reads).toBe(reads);
});

test("AC-E1 a member sees no email notice and reads no system status", async ({
  page,
}) => {
  await signedInAs(page, { id: MEMBER, role: "member" });
  const status = await routeEmailStatus(page, "not_set_up");
  // The notice waits for the verified identity, so the check does too.
  const identity = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/auth/me",
  );
  await page.goto("/manage?view=organization");
  await identity;
  await expect(
    page.getByRole("heading", { level: 1, name: "Organization", exact: true }),
  ).toBeVisible();
  await settleReact(page);
  await expect(notice(page)).toHaveCount(0);
  await expect(
    page.getByText("Email is not set up.", { exact: false }),
  ).toHaveCount(0);
  expect(status.reads).toBe(0);
});

test("AC-E2 an administrator reads the email status and the four setup steps in reading order", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await signedInAs(page, { id: ADMIN, role: "admin" });
  await routeEmailStatus(page, "not_set_up");
  await page.goto("/manage?view=email");

  await expect(
    page.getByRole("heading", { level: 1, name: "Email", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "See whether email is set up, and how to set it up on the server PC.",
      { exact: true },
    ),
  ).toBeVisible();
  // The navigation lists Email in Manage for an administrator.
  await expect(
    page.getByRole("link", { name: "Email", exact: true }).first(),
  ).toHaveAttribute("href", "/manage?view=email");

  const band = page.getByRole("region", {
    name: "Email is not set up.",
    exact: true,
  });
  await expect(band).toContainText(
    "Invitations and password emails cannot be sent until it is.",
  );

  const server = page.getByRole("region", {
    name: "On the server PC",
    exact: true,
  });
  const provider = page.getByRole("region", {
    name: "In Set up email",
    exact: true,
  });
  await expect(server.getByRole("listitem")).toHaveText([
    "1Open Slate Operations settings from the Start menu.",
    "2Select Set up email.",
  ]);
  await expect(provider).toContainText(
    "3For Gmail:a. Turn on 2-Step Verification for the Gmail account.b. Make an app password, and type it in Set up email.",
  );
  await expect(provider).toContainText(
    "4For another provider: type its mail server name, port, and password in Set up email.",
  );
  await expect(
    provider.getByRole("link", { name: "2-Step Verification" }),
  ).toHaveAttribute(
    "href",
    "https://myaccount.google.com/signinoptions/two-step-verification",
  );
  await expect(
    provider.getByRole("link", { name: "app password" }),
  ).toHaveAttribute("href", "https://myaccount.google.com/apppasswords");
  // Steps 1 and 2 come before 3 and 4 in reading order.
  const serverBox = await server.boundingBox();
  const providerBox = await provider.boundingBox();
  expect(serverBox!.x).toBeLessThan(providerBox!.x);

  // The page stays still at 1440, and reads on a phone without sideways scroll.
  await expectNoPageScroll(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(provider).toBeVisible();
  await expectNoHorizontalScroll(page);
});

test("AC-E2 a member who follows an Email link sees that it is not available, with no Email entry and no status read", async ({
  page,
}) => {
  await signedInAs(page, { id: MEMBER, role: "member" });
  const status = await routeEmailStatus(page, "not_set_up");
  await page.goto("/manage?view=email");
  await expect(
    page.getByText("Email is not available to your account.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Go to Organization", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "On the server PC" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Email", exact: true }),
  ).toHaveCount(0);
  expect(status.reads).toBe(0);
});

test.describe("Forgot password", () => {
  test.beforeEach(async ({ page }) => {
    await signedOut(page);
  });

  test("AC-E3 with email not set up the reset request names the server PC settings and shows no reference; another failure keeps its reference", async ({
    page,
  }) => {
    let notConfigured = true;
    await page.route("**/api/auth/recovery/request", (route) =>
      route.fulfill({
        status: 503,
        headers: answeredHeaders,
        json: notConfigured
          ? {
              detail: {
                code: "email_not_configured",
                message:
                  "Email is not set up yet. Set it up in Slate Operations settings on the server PC.",
              },
            }
          : { detail: "Recovery service unavailable" },
      }),
    );
    await page.goto("/auth/recovery");
    await page.getByLabel("Email", { exact: true }).fill("member@example.test");
    await page.getByRole("button", { name: "Request recovery" }).click();
    const alert = page.getByRole("alert").filter({
      hasText:
        "Email is not set up yet. Set it up in Slate Operations settings on the server PC.",
    });
    await expect(alert).toBeVisible();
    await expect(alert.getByTitle(answeredRequestId)).toHaveCount(0);
    await expect(alert).not.toContainText("Reference");

    notConfigured = false;
    await page.getByRole("button", { name: "Request recovery" }).click();
    const failure = page.getByRole("alert").filter({
      hasText: "We could not process that request. Try again shortly.",
    });
    await expect(failure).toBeVisible();
    await expectAnsweredReference(failure);
  });
});
