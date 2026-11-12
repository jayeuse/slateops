import {
  answeredHeaders,
  answeredRequestId,
  authMeBody,
  expect,
  expectAnsweredReference,
  heldResponse,
  test,
  type Page,
  type Route,
} from "./helpers/test";

// docs/specs/ux-friction-pass.md item 13 (DR-13.1 to DR-13.3): after sign-in
// an account in several organizations opens the one this browser opened
// last, through the same server check as a pick. A refusal shows the chooser
// with its reason and never enters a two-step or network screen by itself.
// The pure rule (membership check, stored value) is owned by
// isolated/auth/last-organization.spec.ts.

const userId = "00000000-0000-4000-8000-0000000000b1";
const harbor = {
  org_id: "00000000-0000-4000-8000-0000000000a1",
  name: "Harbor Operations Group",
  slug: "harbor",
  role: "member" as const,
};
const school = {
  org_id: "00000000-0000-4000-8000-0000000000a2",
  name: "Riverside School",
  slug: "riverside",
  role: "member" as const,
};
const lastOrganizationKey = "slateops-last-organization";

type Selection = {
  status: number;
  code?: string;
  /** The account the 200 answer names; this account by default. */
  account?: string;
  /** Answers each select itself; `attempt` counts from 1. */
  answer?: (route: Route, attempt: number) => Promise<void>;
};

async function installTwoOrganizations(
  page: Page,
  selection: Selection,
  stored: string = school.org_id,
) {
  const state = {
    selects: [] as string[],
    mfaReads: 0,
    sessionReads: 0,
    // A dead session reads as signed out; the sign-in page signs in again.
    signedIn: true,
    // Refreshes that succeed (and sign the session in again); others are 401.
    refreshGrants: 0,
  };
  // This browser opened Riverside School last; a reload keeps what the app
  // stores after that.
  await page.addInitScript(
    ([key, orgId]) => {
      if (!localStorage.getItem(key)) localStorage.setItem(key, orgId);
      // Records whether the chooser ever rendered, even for one frame.
      new MutationObserver(() => {
        if (document.body?.textContent?.includes("Choose an organization"))
          (window as Window & { chooserSeen?: boolean }).chooserSeen = true;
      }).observe(document, { childList: true, subtree: true });
    },
    [lastOrganizationKey, stored],
  );
  await page.route("**/api/auth/login", (route) => {
    state.signedIn = true;
    return route.fulfill({
      json: { authenticated: true, setup_required: false },
    });
  });
  await page.route("**/api/auth/refresh", (route) => {
    if (state.refreshGrants === 0)
      return route.fulfill({
        status: 401,
        json: { detail: "Unauthenticated" },
      });
    state.refreshGrants -= 1;
    state.signedIn = true;
    return route.fulfill({ json: { authenticated: true } });
  });
  await page.route("**/api/auth/session", (route) => {
    state.sessionReads += 1;
    if (!state.signedIn)
      return route.fulfill({ json: { authenticated: false } });
    return route.fulfill({
      json: {
        authenticated: true,
        user_id: userId,
        // Signed in: the session has no organization yet.
        organization_id: null,
        default_organization_blocked: null,
        setup_required: false,
      },
    });
  });
  await page.route("**/api/auth/me", (route) => {
    const tab = route.request().headers()["x-org"];
    const current = [harbor, school].find((entry) => entry.org_id === tab);
    return route.fulfill({
      json: authMeBody({
        id: userId,
        role: "member",
        memberships: [harbor, school],
        current_organization: current ? { ...current, access: [] } : null,
      }),
    });
  });
  await page.route("**/api/auth/session/organization", (route) => {
    const body = route.request().postDataJSON() as { org_id: string };
    state.selects.push(body.org_id);
    if (selection.answer) return selection.answer(route, state.selects.length);
    return selection.status === 200
      ? route.fulfill({
          json: authMeBody({
            id: selection.account ?? userId,
            role: "member",
            memberships: [harbor, school],
            current_organization: { ...school, access: [] },
          }),
        })
      : route.fulfill({
          status: selection.status,
          // The server's answers carry their request ID.
          headers: answeredHeaders,
          json: {
            detail: {
              code: selection.code,
              message: "Refused by the organization",
            },
          },
        });
  });
  await page.route(
    (url) => url.pathname.startsWith("/api/auth/mfa"),
    (route) => {
      state.mfaReads += 1;
      return route.fulfill({ status: 500, body: "" });
    },
  );
  return state;
}

const chooserSeen = (page: Page) =>
  page.evaluate(
    () => (window as Window & { chooserSeen?: boolean }).chooserSeen === true,
  );

test("UF-C13.1 sign-in opens the organization this browser opened last, with no chooser", async ({
  page,
}) => {
  const state = await installTwoOrganizations(page, { status: 200 });
  await page.goto("/platform?section=notifications");
  // The workspace opens, and the tab works in Riverside School.
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("slateops-organization")),
  ).toBe(school.org_id);
  expect(state.selects).toEqual([school.org_id]);
  await expect(
    page.getByRole("heading", { name: "Choose an organization" }),
  ).toHaveCount(0);
  expect(await chooserSeen(page)).toBe(false);
});

test("UF-C13.3 a refused automatic open shows the chooser with the reason and enters no two-step screen", async ({
  page,
}) => {
  const state = await installTwoOrganizations(page, {
    status: 403,
    code: "mfa_required",
  });
  await page.goto("/platform?section=notifications");
  await expect(
    page.getByRole("heading", { name: "Choose an organization" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Riverside School asks for two-step verification. Choose it to continue.",
      { exact: true },
    ),
  ).toBeVisible();
  // A policy the person meets, not a failure (DR-13.3).
  await expect(
    refusalAlert(page, "Riverside School asks for two-step verification."),
  ).toHaveAttribute("data-variant", "warning");
  expect(state.selects).toEqual([school.org_id]);
  await expect(
    page.getByRole("heading", { name: "Complete two-step verification" }),
  ).toHaveCount(0);
  expect(state.mfaReads).toBe(0);
  // The tab took no organization; both stay choosable.
  expect(
    await page.evaluate(() => sessionStorage.getItem("slateops-organization")),
  ).toBeNull();
  await expect(
    page.getByRole("button", { name: /^Harbor Operations Group/ }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: /^Riverside School/ }),
  ).toBeEnabled();
  // A later check (here, the window regaining focus) does not try again and
  // keeps the reason.
  const reads = state.sessionReads;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect.poll(() => state.sessionReads).toBeGreaterThan(reads);
  await expect(
    page.getByRole("heading", { name: "Choose an organization" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Riverside School asks for two-step verification. Choose it to continue.",
      { exact: true },
    ),
  ).toBeVisible();
  expect(state.selects).toEqual([school.org_id]);
  expect(state.mfaReads).toBe(0);
});

test("UF-C13.2 an organization this account does not belong to never opens: the chooser shows and nothing is selected", async ({
  page,
}) => {
  // Another account opened it last in this browser.
  const state = await installTwoOrganizations(
    page,
    { status: 200 },
    "00000000-0000-4000-8000-0000000000f9",
  );
  await page.goto("/platform?section=notifications");
  await expect(
    page.getByRole("heading", { name: "Choose an organization" }),
  ).toBeVisible();
  expect(state.selects).toEqual([]);
  await expect(
    page.getByText(/asks for two-step|could not be opened|from this network/),
  ).toHaveCount(0);
});

const tabOrganization = (page: Page) =>
  page.evaluate(() => sessionStorage.getItem("slateops-organization"));
const refusalAlert = (page: Page, words: string) =>
  page.locator('[data-slot="alert"]').filter({ hasText: words });

// Security review F1: the select's answer must name this account.
test("UF-C13.2 a select answered for another account opens nothing and the session check reads as unavailable", async ({
  page,
}) => {
  const state = await installTwoOrganizations(page, {
    status: 200,
    account: "00000000-0000-4000-8000-0000000000f8",
  });
  await page.goto("/platform?section=notifications");
  await expect(
    page.getByText("We can’t verify your session right now.", {
      exact: false,
    }),
  ).toBeVisible();
  expect(await tabOrganization(page)).toBeNull();
  expect(state.selects).toEqual([school.org_id]);
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveCount(0);
});

// Security review F2: one example per remaining refusal class.
test("UF-C13.3 a network refusal of the automatic open shows its reason on the chooser and no network screen", async ({
  page,
}) => {
  const state = await installTwoOrganizations(page, {
    status: 403,
    code: "ip_not_allowed",
  });
  await page.goto("/platform?section=notifications");
  await expect(
    page.getByRole("heading", { name: "Choose an organization" }),
  ).toBeVisible();
  await expect(
    refusalAlert(
      page,
      "Riverside School does not allow sign-in from this network.",
    ),
  ).toHaveAttribute("data-variant", "warning");
  await expect(
    page.getByText("Access from this address is not allowed", { exact: false }),
  ).toHaveCount(0);
  await expect(page.getByTitle(answeredRequestId)).toHaveCount(0);
  expect(await tabOrganization(page)).toBeNull();
  expect(state.selects).toEqual([school.org_id]);
});

test('UF-C13.3 a 503 on the automatic open shows "could not be opened" with its reference', async ({
  page,
}) => {
  const state = await installTwoOrganizations(page, { status: 503 });
  await page.goto("/platform?section=notifications");
  await expect(
    page.getByRole("heading", { name: "Choose an organization" }),
  ).toBeVisible();
  const alert = refusalAlert(page, "Riverside School could not be opened.");
  await expect(alert).toHaveAttribute("data-variant", "destructive");
  await expectAnsweredReference(alert);
  expect(await tabOrganization(page)).toBeNull();
  expect(state.selects).toEqual([school.org_id]);
});

// DR-13.3 (PR2 screen review): a 401 is not an organization refusal. The
// session check takes it (refresh, then the sign-in page). One automatic try
// belongs to each mount of the signed-in app: the sign-in page unmounts it,
// so the next sign-in may try once more.
test("UF-C13.3 a 401 on the automatic open follows the session check to the sign-in page, and the next sign-in tries once more", async ({
  page,
}) => {
  const state = await installTwoOrganizations(page, {
    status: 0,
    answer: async (route, attempt) => {
      if (attempt === 1) {
        // The session died between the session read and the select.
        state.signedIn = false;
        await route.fulfill({
          status: 401,
          headers: answeredHeaders,
          json: { detail: "Invalid authentication credentials" },
        });
        return;
      }
      await route.fulfill({
        json: authMeBody({
          id: userId,
          role: "member",
          memberships: [harbor, school],
          current_organization: { ...school, access: [] },
        }),
      });
    },
  });
  await page.goto("/platform?section=notifications");
  await expect(page).toHaveURL(/\/login$/);
  expect(state.selects).toEqual([school.org_id]);
  expect(await chooserSeen(page)).toBe(false);
  expect(await tabOrganization(page)).toBeNull();

  await page.getByLabel("Email", { exact: true }).fill("member@example.test");
  await page.getByLabel("Password").fill("correct horse battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
  expect(state.selects).toEqual([school.org_id, school.org_id]);
  expect(await tabOrganization(page)).toBe(school.org_id);
});

// Security review F3: a newer check interrupts the select. It tries exactly
// once more, then never again, and the interrupted try leaves no trace.
test("UF-C13.3 an interrupted automatic open tries once more, then never again, and leaves nothing behind", async ({
  page,
}) => {
  const first = heldResponse();
  const state = await installTwoOrganizations(page, {
    status: 0,
    answer: async (route, attempt) => {
      if (attempt === 1) {
        first.enter();
        await first.released;
        // Late: the browser already dropped this request.
        await route
          .fulfill({
            status: 403,
            headers: answeredHeaders,
            json: { detail: { code: "mfa_required", message: "Refused" } },
          })
          .catch(() => {});
        return;
      }
      await route.fulfill({
        status: 403,
        headers: answeredHeaders,
        json: { detail: { code: "ip_not_allowed", message: "Refused" } },
      });
    },
  });
  try {
    await page.goto("/platform?section=notifications");
    await first.entered;
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(
      refusalAlert(
        page,
        "Riverside School does not allow sign-in from this network.",
      ),
    ).toBeVisible();
  } finally {
    first.release();
  }
  expect(state.selects).toEqual([school.org_id, school.org_id]);
  await expect(page.getByText(/asks for two-step verification/)).toHaveCount(0);
  expect(await tabOrganization(page)).toBeNull();
  const reads = state.sessionReads;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect.poll(() => state.sessionReads).toBeGreaterThan(reads);
  await expect(
    page.getByRole("heading", { name: "Choose an organization" }),
  ).toBeVisible();
  expect(state.selects).toEqual([school.org_id, school.org_id]);
});

// Security delta review F4: a 401 while the session stays live (say, a CSRF
// failure). The re-check refreshes and finds the session; the one try is
// spent, so it shows the chooser and never selects again. Selects after the
// second are held, so a build that loops stops instead of running on.
test("UF-C13.3 a 401 on the automatic open while the session stays live does not try again: the chooser shows with no reason", async ({
  page,
}) => {
  const state = await installTwoOrganizations(page, {
    status: 0,
    answer: async (route, attempt) => {
      if (attempt > 2) return new Promise<void>(() => {});
      if (attempt === 1) {
        state.signedIn = false;
        state.refreshGrants = 1;
      }
      await route.fulfill({
        status: 401,
        headers: answeredHeaders,
        json: { detail: "Invalid authentication credentials" },
      });
    },
  });
  await page.goto("/platform?section=notifications");
  await expect
    .poll(async () => state.selects.length > 1 || (await chooserSeen(page)))
    .toBe(true);
  expect(state.selects).toEqual([school.org_id]);
  await expect(
    page.getByRole("heading", { name: "Choose an organization" }),
  ).toBeVisible();
  await expect(page.locator('[data-slot="alert"]')).toHaveCount(0);
  expect(await tabOrganization(page)).toBeNull();
  await expect(page).not.toHaveURL(/\/login$/);
  const reads = state.sessionReads;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect.poll(() => state.sessionReads).toBeGreaterThan(reads);
  await expect(
    page.getByRole("heading", { name: "Choose an organization" }),
  ).toBeVisible();
  expect(state.selects).toEqual([school.org_id]);
});
