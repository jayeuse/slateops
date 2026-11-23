import { randomBytes } from "node:crypto";

import {
  authMeBody,
  defaultOrganization,
  expect,
  test,
  type Page,
} from "./helpers/test";
import { created, ids, mockAccessApi } from "./helpers/access-api";
import { openedSheet } from "./helpers/settled";

// Generated per run, so no literal secret sits in the repository (secret scan).
const TEMPORARY_PASSWORD = `Tp${randomBytes(12).toString("base64url")}9a`;

// DEC-0042: Slate Operations works without email. An administrator invites a
// person with a one-time link to copy and send by any channel, makes a new
// link for a pending invitation (the old one stops), and sets a temporary
// password for a person. Adapters and refusal words are owned by the isolated
// access specs; these journeys prove what the screens show and send.

const link =
  "https://slateops.example/auth/setup#token_hash=abc123&type=invite";
const newLink =
  "https://slateops.example/auth/setup#token_hash=def456&type=invite";
const operationId = "00000000-0000-4000-8000-000000000911";

function statusBody(email: "not_set_up" | "set_up") {
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

/** The clipboard keeps the last copied text on the page for the test. */
async function recordClipboard(page: Page) {
  await page.addInitScript(() =>
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (text: string) => {
          document.documentElement.dataset.copied = text;
        },
      },
    }),
  );
  return () =>
    page.evaluate(() => document.documentElement.dataset.copied ?? null);
}

async function setupAccess(page: Page, email: "not_set_up" | "set_up") {
  const api = await mockAccessApi(page);
  // Registered after the Access mock, so it answers the status read.
  await page.route("**/api/system/status", (route) =>
    route.fulfill({ json: statusBody(email) }),
  );
  api.on("POST", "/api/auth/invitations", (route, call) => {
    const body = call.body as { email: string; username: string };
    const user = {
      ...api.users.get(ids.cy)!,
      id: "00000000-0000-4000-8000-000000000199",
      email: body.email,
      username: body.username,
      invitation_sent_at: created,
    };
    const byLink = (call.body as { delivery?: string }).delivery === "link";
    return route.fulfill({
      status: 201,
      json: {
        user,
        delivery: byLink ? "link" : "email",
        invitation_url: byLink ? link : null,
      },
    });
  });
  return api;
}

test("AC-L-UI with email not set up an administrator invites by a link that shows once with Copy", async ({
  page,
}) => {
  const copied = await recordClipboard(page);
  const api = await setupAccess(page, "not_set_up");
  await page.goto("/access?view=people");
  await page.getByRole("button", { name: "Invite person" }).click();
  const dialog = page.getByRole("dialog", { name: "Invite a person" });
  await dialog.getByLabel("Email").fill("eve.stone@example.com");
  await expect(
    dialog.getByText(
      "Email is not set up, so you copy an invitation link and send it to them yourself.",
    ),
  ).toBeVisible();
  await expect(dialog.getByRole("radio")).toHaveCount(0);
  await expect(
    dialog.getByRole("button", { name: "Send invitation" }),
  ).toHaveCount(0);
  await dialog.getByRole("button", { name: "Create invitation link" }).click();

  const result = page.getByRole("dialog", {
    name: "Send this invitation link",
  });
  await expect(
    result.getByRole("textbox", {
      name: "Invitation link for eve.stone@example.com",
    }),
  ).toHaveValue(link);
  await expect(result).toContainText(
    "It works once, for 24 hours, and shows only now.",
  );
  expect(api.sent("POST", "/api/auth/invitations")[0]?.body).toMatchObject({
    email: "eve.stone@example.com",
    username: "eve_stone",
    delivery: "link",
  });
  await result.getByRole("button", { name: "Copy link" }).click();
  await expect(result.getByRole("button", { name: "Copied" })).toBeVisible();
  expect(await copied()).toBe(link);
  // D4: the copy is the one filled button; closing is secondary.
  await expect(
    result.getByRole("button", { name: "Close", exact: true }),
  ).toHaveAttribute("data-variant", "secondary");
  await result.getByRole("button", { name: "Close", exact: true }).click();
  await expect(result).toBeHidden();
});

test("AC-I2 the administrator copies a ready-to-send message that names the organization, the link and both sign-in names", async ({
  page,
}) => {
  const copied = await recordClipboard(page);
  const api = await setupAccess(page, "not_set_up");
  api.on("GET", "/api/auth/me", (route) =>
    route.fulfill({
      json: authMeBody({
        id: ids.rosa,
        role: "admin",
        current_organization: {
          ...defaultOrganization,
          name: "Harbor Logistics",
          role: "admin",
          access: [],
        },
      }),
    }),
  );
  await page.goto("/access?view=people");
  await page.getByRole("button", { name: "Invite person" }).click();
  const dialog = page.getByRole("dialog", { name: "Invite a person" });
  await dialog.getByLabel("Email").fill("eve.stone@example.com");
  await dialog.getByRole("button", { name: "Create invitation link" }).click();

  const result = page.getByRole("dialog", {
    name: "Send this invitation link",
  });
  const message =
    "You are invited to join Harbor Logistics on Slate Operations. " +
    `Open this link to choose your password: ${link} — it works once, for 24 hours. ` +
    "Then sign in with eve.stone@example.com or your username eve_stone.";
  // The message shows as the person will read it, and the link stays.
  await expect(
    result.getByRole("textbox", { name: "Message to send" }),
  ).toHaveValue(message);
  await expect(
    result.getByRole("textbox", {
      name: "Invitation link for eve.stone@example.com",
    }),
  ).toHaveValue(link);
  await result.getByRole("button", { name: "Copy invitation message" }).click();
  await expect(result.getByRole("button", { name: "Copied" })).toHaveCount(1);
  expect(await copied()).toBe(message);
  // The link alone can still be copied.
  await result.getByRole("button", { name: "Copy link" }).click();
  await expect.poll(copied).toBe(link);
});

test("AC-I2 on a phone the invitation message opens at its title, not at the form's scroll position", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const api = await setupAccess(page, "set_up");
  // A real link (56-character token), a long organization name and a long
  // address make the result taller than the phone's dialog, so it can keep
  // the form's scroll position.
  api.on("GET", "/api/auth/me", (route) =>
    route.fulfill({
      json: authMeBody({
        id: ids.rosa,
        role: "admin",
        current_organization: {
          ...defaultOrganization,
          name: "Harbor Operations Group",
          role: "admin",
          access: [],
        },
      }),
    }),
  );
  api.on("POST", "/api/auth/invitations", (route, call) =>
    route.fulfill({
      status: 201,
      json: {
        user: {
          ...api.users.get(ids.cy)!,
          id: "00000000-0000-4000-8000-000000000199",
          email: (call.body as { email: string }).email,
          username: (call.body as { username: string }).username,
          invitation_sent_at: created,
        },
        delivery: "link",
        invitation_url: `http://localhost:3000/auth/setup#token_hash=${"0123456789abcdef".repeat(3)}01234567&type=invite`,
      },
    }),
  );
  await page.goto("/access?view=people");
  await page.getByRole("button", { name: "Invite person" }).click();
  const dialog = page.getByRole("dialog", { name: "Invite a person" });
  await dialog.getByLabel("Email").fill("handson.1795443593151@openslate.test");
  await dialog
    .getByRole("radio", { name: "Copy a link to send yourself" })
    .click();
  // With many groups the form is long: the person scrolls to its end.
  await dialog.hover();
  await page.mouse.wheel(0, 3000);
  await expect(
    dialog.getByRole("heading", { name: "Invite a person" }),
  ).not.toBeInViewport();
  await dialog.getByRole("button", { name: "Create invitation link" }).click();
  const result = page.getByRole("dialog", {
    name: "Send this invitation link",
  });
  await expect(
    result.getByRole("textbox", { name: "Message to send" }),
  ).toBeVisible();
  await expect(
    result.getByRole("heading", { name: "Send this invitation link" }),
  ).toBeInViewport();
});

test("AC-L-UI with email set up an administrator chooses email or an invitation link", async ({
  page,
}) => {
  const api = await setupAccess(page, "set_up");
  await page.goto("/access?view=people");
  await page.getByRole("button", { name: "Invite person" }).click();
  const dialog = page.getByRole("dialog", { name: "Invite a person" });
  await dialog.getByLabel("Email").fill("eve.stone@example.com");
  await expect(
    dialog.getByRole("radio", { name: "Send from Slate Operations" }),
  ).toBeChecked();
  await dialog
    .getByRole("radio", { name: "Copy a link to send yourself" })
    .click();
  await dialog.getByRole("button", { name: "Create invitation link" }).click();
  await expect(
    page
      .getByRole("dialog", { name: "Send this invitation link" })
      .getByRole("textbox", {
        name: "Invitation link for eve.stone@example.com",
      }),
  ).toHaveValue(link);
  expect(api.sent("POST", "/api/auth/invitations")[0]?.body).toMatchObject({
    delivery: "link",
  });
});

test("AC-L-UI a pending invitation gets Copy a new link, and the old link stops", async ({
  page,
}) => {
  const copied = await recordClipboard(page);
  const api = await setupAccess(page, "not_set_up");
  api.on("GET", "/api/auth/me", (route) =>
    route.fulfill({
      json: authMeBody({
        id: ids.rosa,
        role: "admin",
        current_organization: {
          ...defaultOrganization,
          name: "Harbor Logistics",
          role: "admin",
          access: [],
        },
      }),
    }),
  );
  const cy = api.users.get(ids.cy)!;
  api.users.set(ids.cy, { ...cy, invitation_sent_at: created });
  api.on("POST", `/api/auth/invitations/${ids.cy}/link`, (route) =>
    route.fulfill({
      json: {
        user: api.users.get(ids.cy),
        delivery: "link",
        invitation_url: newLink,
      },
    }),
  );
  await page.goto(`/access?view=people&user=${ids.cy}`);
  const sheet = await openedSheet(
    page.getByRole("dialog", { name: "cy", exact: true }),
  );
  await sheet.getByRole("button", { name: "Copy a new link" }).click();
  const confirm = page.getByRole("alertdialog", {
    name: "Make a new invitation link?",
  });
  await expect(confirm).toContainText(
    "The earlier link or invitation email for cy@example.com stops working. The new link works once, for 24 hours.",
  );
  await confirm.getByRole("button", { name: "Make new link" }).click();
  const result = page.getByRole("alertdialog", {
    name: "Send this invitation link",
  });
  await expect(
    result.getByRole("textbox", { name: "Invitation link for cy@example.com" }),
  ).toHaveValue(newLink);
  // D2: a new link comes with the same ready-to-send message.
  const message =
    "You are invited to join Harbor Logistics on Slate Operations. " +
    `Open this link to choose your password: ${newLink} — it works once, for 24 hours. ` +
    "Then sign in with cy@example.com or your username cy.";
  await expect(
    result.getByRole("textbox", { name: "Message to send" }),
  ).toHaveValue(message);
  await result.getByRole("button", { name: "Copy invitation message" }).click();
  await expect(result.getByRole("button", { name: "Copied" })).toHaveCount(1);
  expect(await copied()).toBe(message);
  await result.getByRole("button", { name: "Copy link" }).click();
  await expect.poll(copied).toBe(newLink);
  expect(api.sent("POST", `/api/auth/invitations/${ids.cy}/link`)).toEqual([
    {
      method: "POST",
      path: `/api/auth/invitations/${ids.cy}/link`,
      body: {},
    },
  ]);
  await expect(
    result.getByRole("button", { name: "Close", exact: true }),
  ).toHaveAttribute("data-variant", "secondary");
  await result.getByRole("button", { name: "Close", exact: true }).click();
  await expect(result).toBeHidden();
  await expect(
    sheet.getByRole("button", { name: "Copy a new link" }),
  ).toBeFocused();
});

async function openSecurity(page: Page, userId: string, name: string) {
  await page.goto(`/access?view=people&user=${userId}`);
  const sheet = await openedSheet(
    page.getByRole("dialog", { name, exact: true }),
  );
  await sheet.getByRole("tab", { name: "Security", exact: true }).click();
  await expect(
    sheet.getByRole("heading", { name: "Sign-in security" }),
  ).toBeVisible();
  return sheet;
}

async function setupSecurity(page: Page) {
  const api = await mockAccessApi(page);
  for (const userId of [ids.ben, ids.rosa])
    api.on("GET", `/api/users/${userId}/security`, (route) =>
      route.fulfill({
        json: {
          user_id: userId,
          verified_factor_count: 0,
          target_eligible: true,
          smtp_configured: false,
        },
      }),
    );
  // The panel reads the administrator's own two-step level with the person.
  api.on("GET", "/api/auth/mfa", (route) =>
    route.fulfill({
      json: {
        user_id: ids.rosa,
        assurance_level: "aal2",
        required: false,
        policy_required: false,
        required_since: null,
        enrollment_deadline: null,
        factors: [],
      },
    }),
  );
  return api;
}

test("AC-T-UI an administrator sets a temporary password the server makes, and sees it once with Copy", async ({
  page,
}) => {
  const copied = await recordClipboard(page);
  const api = await setupSecurity(page);
  api.on("POST", `/api/users/${ids.ben}/temporary-password`, (route) =>
    route.fulfill({
      json: {
        operation_id: operationId,
        user_id: ids.ben,
        temporary_password: TEMPORARY_PASSWORD,
        local_revocation: "committed",
        revoked_sessions: 2,
      },
    }),
  );
  const sheet = await openSecurity(page, ids.ben, "Ben Cruz");
  await sheet.getByRole("button", { name: "Set a temporary password" }).click();
  const dialog = page.getByRole("dialog", {
    name: "Set a temporary password for Ben Cruz?",
  });
  await expect(dialog).toContainText(
    "Their sessions end on every device. At their next sign-in they use this password once, then choose their own.",
  );
  await expect(
    dialog.getByRole("radio", { name: "Make one for me" }),
  ).toBeChecked();
  await dialog.getByRole("button", { name: "Set temporary password" }).click();
  const shown = page.getByRole("dialog", {
    name: "Temporary password for Ben Cruz",
  });
  await expect(
    shown.getByRole("textbox", { name: "Temporary password" }),
  ).toHaveValue(TEMPORARY_PASSWORD);
  await shown.getByRole("button", { name: "Copy password" }).click();
  expect(await copied()).toBe(TEMPORARY_PASSWORD);
  expect(
    api.sent("POST", `/api/users/${ids.ben}/temporary-password`)[0]?.body,
  ).toEqual({});
  await shown.getByRole("button", { name: "Done" }).click();
  await expect(shown).toBeHidden();
});

test("AC-T-UI a typed temporary password is sent as typed, and an owner refusal says why", async ({
  page,
}) => {
  const api = await setupSecurity(page);
  let refuse = false;
  api.on("POST", `/api/users/${ids.ben}/temporary-password`, (route) =>
    refuse
      ? route.fulfill({
          status: 409,
          json: {
            detail: {
              code: "security_target_owner",
              message: "Owners cannot be changed here",
            },
          },
        })
      : route.fulfill({
          json: {
            operation_id: operationId,
            user_id: ids.ben,
            temporary_password: null,
            local_revocation: "committed",
            revoked_sessions: 1,
          },
        }),
  );
  const sheet = await openSecurity(page, ids.ben, "Ben Cruz");
  await sheet.getByRole("button", { name: "Set a temporary password" }).click();
  const dialog = page.getByRole("dialog", {
    name: "Set a temporary password for Ben Cruz?",
  });
  await dialog.getByRole("radio", { name: "Type one" }).click();
  await dialog
    .getByRole("textbox", { name: "Temporary password" })
    .fill("a typed temporary one");
  await dialog.getByRole("button", { name: "Set temporary password" }).click();
  await expect(dialog).toBeHidden();
  await expect(
    sheet.getByText(
      "Temporary password set for Ben Cruz. Their sessions ended, and they choose a new password at their next sign-in.",
    ),
  ).toBeVisible();
  expect(
    api.sent("POST", `/api/users/${ids.ben}/temporary-password`)[0]?.body,
  ).toEqual({ password: "a typed temporary one" });

  refuse = true;
  await sheet.getByRole("button", { name: "Set a temporary password" }).click();
  await dialog.getByRole("button", { name: "Set temporary password" }).click();
  await expect(dialog.getByRole("alert")).toContainText(
    "You cannot set a temporary password for an owner of this organization or of the installation.",
  );
});

test("AC-T-UI an administrator's own Security tab offers no temporary password", async ({
  page,
}) => {
  await setupSecurity(page);
  const sheet = await openSecurity(page, ids.rosa, "Rosa Reyes");
  await expect(
    sheet.getByRole("button", { name: "Send recovery email" }),
  ).toBeVisible();
  await expect(
    sheet.getByRole("button", { name: "Set a temporary password" }),
  ).toHaveCount(0);
});
