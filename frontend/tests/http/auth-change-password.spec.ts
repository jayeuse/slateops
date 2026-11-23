import {
  authMeBody,
  defaultSignedInIdentity,
  expect,
  test,
  type Page,
} from "./helpers/test";

// Generated per run, so no literal secret sits in the repository (secret scan).
const TEMPORARY_PASSWORD = `Tp${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;

// DEC-0042: after an administrator sets a temporary password, the server
// answers every call except a few auth routes with 403
// `password_change_required` until the person chooses a new password. The
// app sends the person to "Choose a new password" and opens normally after
// the change. The start-route rule is owned by isolated/auth/workspace-start.

const open = new Set([
  "/api/auth/me",
  "/api/auth/session",
  "/api/auth/login",
  "/api/auth/logout",
  "/api/auth/refresh",
  "/api/auth/password/change",
  "/api/workspace/appearance",
]);

/** The server's forced change: refusals while the mark is set. */
async function forcedChange(page: Page, signedIn: boolean) {
  const state = { required: true, signedIn, changes: [] as unknown[] };
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!state.required || open.has(path)) return route.fallback();
    // A marked session opens no event stream (backend AC-T2).
    if (path === "/api/events")
      return route.fulfill({
        status: 401,
        json: { detail: "Unauthenticated" },
      });
    return route.fulfill({
      status: 403,
      json: {
        detail: {
          code: "password_change_required",
          message: "Choose a new password to continue.",
        },
      },
    });
  });
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({
      json: state.signedIn
        ? {
            authenticated: true,
            user_id: defaultSignedInIdentity.id,
            organization_id: "00000000-0000-4000-8000-000000000102",
            default_organization_blocked: null,
            setup_required: false,
          }
        : { authenticated: false },
    }),
  );
  // A browser without session cookies has its refresh refused.
  await page.route("**/api/auth/refresh", (route) =>
    state.signedIn
      ? route.fallback()
      : route.fulfill({ status: 401, json: { detail: "Unauthenticated" } }),
  );
  await page.route("**/api/auth/login", (route) => {
    state.signedIn = true;
    return route.fulfill({
      json: { authenticated: true, setup_required: false },
    });
  });
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      json: authMeBody({
        id: defaultSignedInIdentity.id,
        role: "member",
        password_change_required: state.required,
      }),
    }),
  );
  await page.route("**/api/auth/password/change", (route) => {
    state.changes.push(route.request().postDataJSON());
    state.required = false;
    return route.fulfill({
      json: { authenticated: true, setup_required: false },
    });
  });
  return state;
}

test("AC-F-UI signing in with a temporary password opens Choose a new password, and the new password opens the app", async ({
  page,
}) => {
  const state = await forcedChange(page, false);
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("ben@example.com");
  await page.getByLabel("Password", { exact: true }).fill(TEMPORARY_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/auth\/change-password$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Choose a new password" }),
  ).toBeVisible();
  await page
    .getByLabel("Temporary password", { exact: true })
    .fill(TEMPORARY_PASSWORD);
  await page
    .getByLabel("New password", { exact: true })
    .fill("my own long password");
  await page
    .getByLabel("Confirm new password", { exact: true })
    .fill("my own long password");
  await page.getByRole("button", { name: "Save new password" }).click();

  await expect(page).not.toHaveURL(/\/auth\/change-password/);
  await expect(page).toHaveURL(/\/(openview|sandbox|boards)/);
  expect(state.changes).toEqual([
    {
      current_password: TEMPORARY_PASSWORD,
      password: "my own long password",
    },
  ]);
});

test("AC-F-UI a signed-in person who must choose a new password is sent there from any page", async ({
  page,
}) => {
  await forcedChange(page, true);
  await page.goto("/boards");
  await expect(page).toHaveURL(/\/auth\/change-password$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Choose a new password" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
});
