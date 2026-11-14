import {
  answeredHeaders,
  answeredReference,
  expect,
  expectNoHorizontalScroll,
  heldResponse,
  signedInAs,
  defaultOrganization,
  test,
} from "./helpers/test";
import { profilePreferences } from "./helpers/profile-api";
import { wireWorkspace } from "../helpers/wire";
import type { Page } from "@playwright/test";
import { createMemorySeed } from "../support/comms-memory/memory/seed";
import { createMemoryCommsRuntime } from "../support/comms-memory/memory-client";
import { installCommsLiveApi } from "./helpers/comms-live-api";
import {
  createCommsTestClock,
  type CommsTestClock,
} from "./helpers/comms-world";

const userId = "00000000-0000-4000-8000-000000000101";
async function seedSidebar(
  page: Page,
  role: "admin" | "member" | "guest" = "admin",
  directAllowed = true,
  scenario?: "nonmembers" | "empty",
  options: {
    clock?: CommsTestClock;
    notifications?: boolean;
    /** More categories, each with one channel, to fill a first screen. */
    extraCategories?: number;
    /** One more category with no channel, so "No channels here." shows. */
    emptyCategory?: boolean;
  } = {},
) {
  await signedInAs(page, { id: userId, role });
  const owner = { user_id: userId, org_id: defaultOrganization.org_id };
  const initial = createMemorySeed(owner, {
    role,
    display_name: "Sidebar owner",
  });
  if (!directAllowed) initial.dm_rule = "none";
  const category = Object.values(initial.categories)[0];
  const channel = Object.values(initial.conversations)[0];
  if (channel.kind !== "channel") throw new Error("Expected the seed channel");
  const root = Object.values(initial.messages).find(
    (message) => !message.parent_id,
  )!;
  const second = "76000000-0000-4000-8000-000000000001";
  const secondCategory = "76000000-0000-4000-8000-000000000002";
  initial.categories[secondCategory] = {
    ...category,
    id: secondCategory,
    name: "Planning",
    position: 1,
  };
  initial.conversations[second] = {
    ...channel,
    id: second,
    name: "deliveries",
    category_id: secondCategory,
    position: 1,
  };
  initial.members[second] = structuredClone(initial.members[channel.id]);
  initial.high_water_seq[second] = 1;
  for (let index = 1; index <= (options.extraCategories ?? 0); index += 1) {
    const suffix = String(index).padStart(2, "0");
    const extraCategory = `76000000-0000-4000-8000-0000000001${suffix}`;
    const extraChannel = `76000000-0000-4000-8000-0000000002${suffix}`;
    initial.categories[extraCategory] = {
      ...category,
      id: extraCategory,
      name: `Yard ${index}`,
      position: 1 + index,
    };
    initial.conversations[extraChannel] = {
      ...channel,
      id: extraChannel,
      name: `yard-lane-${index}`,
      category_id: extraCategory,
      position: 0,
    };
    initial.members[extraChannel] = structuredClone(
      initial.members[channel.id],
    );
    initial.high_water_seq[extraChannel] = 0;
  }
  if (options.emptyCategory) {
    const emptyCategory = "76000000-0000-4000-8000-000000000199";
    initial.categories[emptyCategory] = {
      ...category,
      id: emptyCategory,
      name: "Yard empty",
      position: 2 + (options.extraCategories ?? 0),
    };
  }
  const secondMessage = {
    ...root,
    id: "76000000-0000-4000-8000-000000000003",
    client_key: "76000000-0000-4000-8000-000000000004",
    conversation_id: second,
    seq: 1,
    body: "Planning tomorrow's deliveries",
    record_links: [],
    mention_user_ids: [userId],
  };
  initial.messages[secondMessage.id] = secondMessage;
  initial.users[userId].notifications = [
    {
      id: "76000000-0000-4000-8000-000000000005",
      org_id: owner.org_id,
      subject_type: "comms_message",
      subject_id: secondMessage.id,
      kind: "comms-mention",
      conversation_id: second,
      message_id: secondMessage.id,
      status: "unread",
      scheduled_for: null,
      created_at: secondMessage.created_at,
      read_at: null,
    },
  ];
  if (scenario === "nonmembers") {
    // Department channels whose read roles alone make readers (D44).
    for (const person of Object.values(initial.people))
      for (const department of Object.keys(person.department_levels))
        person.department_levels[department] = "read";
    for (const id of Object.keys(initial.conversations))
      initial.members[id] = {};
    const hiddenId = "76000000-0000-4000-8000-000000000090";
    initial.people[hiddenId] = {
      ...initial.people[userId],
      user_id: hiddenId,
      display_name: "Hidden person",
      group_ids: [],
      department_levels: {},
    };
  } else if (scenario === "empty") {
    initial.conversations = {};
    initial.members = {};
    initial.messages = {};
    initial.threads = {};
    initial.high_water_seq = {};
    initial.users[userId].notifications = [];
  }
  const server = await installCommsLiveApi(page, {
    userId,
    organizationId: owner.org_id,
    runtime: createMemoryCommsRuntime(
      { owner, initial },
      options.clock ? { clock: options.clock.now } : {},
    ),
    clock: options.clock?.now,
    notifications: options.notifications,
  });
  return { channel: channel.id, second, server };
}
async function rowAction(page: Page, name: string, action: string) {
  await page
    .getByRole("button", { name: `Channel actions: ${name}`, exact: true })
    .click();
  await page.getByRole("menuitem", { name: action, exact: true }).click();
}

for (const scenario of ["nonmembers", "empty"] as const) {
  test(`S06 correction starts a group with ${scenario} conversation membership`, async ({
    page,
  }) => {
    await seedSidebar(
      page,
      scenario === "empty" ? "admin" : "member",
      true,
      scenario,
    );
    await page.goto("/comms");
    await page
      .getByRole("button", { name: "Start direct message", exact: true })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Start direct message",
      exact: true,
    });
    await dialog
      .getByRole("button", { name: "Group message", exact: true })
      .click();
    const picker = dialog.getByRole("combobox", {
      name: "Add person",
      exact: true,
    });
    await expect(picker).toBeEnabled();
    for (const name of ["Noah Tan", "Sofia Garcia"]) {
      await picker.click();
      await page
        .getByRole("combobox", { name: "Search add person", exact: true })
        .fill(name);
      await expect(
        page.getByRole("option", { name: "Hidden person", exact: true }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("option", { name: "Mara Santos", exact: true }),
      ).toHaveCount(0);
      await page.getByRole("option", { name, exact: true }).click();
    }
    await dialog
      .getByRole("textbox", { name: "Group name", exact: true })
      .fill("Eligible group");
    await dialog
      .getByRole("button", { name: "Start conversation", exact: true })
      .click();
    await expect(dialog).toBeHidden();
    await expect(
      page.getByRole("heading", { name: "Eligible group", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Members", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Members 3", exact: true }),
    ).toBeVisible();
  });
}

test("S06 correction tomorrow mute uses organization midnight rather than device or personal zone", async ({
  page,
}) => {
  // The fake server reads mutes on the same fixed time as the page.
  const clock = createCommsTestClock(page, "2026-10-19T12:00:00Z");
  await seedSidebar(page, "admin", true, undefined, { clock });
  await page.clock.setFixedTime(new Date("2026-10-19T12:00:00Z"));
  await page.route("**/api/workspace", (route) =>
    route.fulfill({
      json: wireWorkspace({
        id: defaultOrganization.org_id,
        display_name: "Slate Operations",
        locale: "en-US",
        timezone: "Asia/Manila",
        currency: "USD",
        today: "2026-10-19",
        purge_enabled: true,
      }),
    }),
  );
  const preferences = profilePreferences(userId);
  await page.route(`**/api/users/${userId}/preferences`, (route) =>
    route.fulfill({
      json: {
        ...preferences,
        appearance: { ...preferences.appearance, timezone: "America/New_York" },
      },
    }),
  );
  await page.goto("/comms");
  await rowAction(page, "operations", "Mute channel until tomorrow");
  await page
    .getByRole("button", { name: "Category actions: Planning", exact: true })
    .click();
  await page
    .getByRole("menuitem", {
      name: "Mute category until tomorrow",
      exact: true,
    })
    .click();
  // Both mutes are saved and shown before any reload cuts a write short.
  for (const name of ["operations", "deliveries"])
    await expect(
      page.getByRole("button", { name: new RegExp(`^${name},`) }),
    ).toHaveAccessibleName(/muted/);
  for (const instant of ["2026-10-19T15:59:00Z", "2026-10-19T16:01:00Z"]) {
    await page.clock.setFixedTime(new Date(instant));
    clock.set(instant);
    await page.reload();
    for (const name of ["operations", "deliveries"]) {
      const row = page.getByRole("button", { name: new RegExp(`^${name},`) });
      if (instant.includes("15:59"))
        await expect(row).toHaveAccessibleName(/muted/);
      else await expect(row).not.toHaveAccessibleName(/muted/);
    }
  }
});

for (const surface of ["direct", "switcher"] as const) {
  test(`S06 correction mobile ${surface} portal controls meet 44px targets`, async ({
    page,
  }, testInfo) => {
    await seedSidebar(page);
    await page.route(`**/api/users/${userId}/preferences`, (route) =>
      route.fulfill({
        json: { ...profilePreferences(userId), theme: "system" },
      }),
    );
    await page.emulateMedia({ colorScheme: "light" });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/comms");
    await page
      .getByRole("button", {
        name:
          surface === "direct" ? "Start direct message" : /Switch conversation/,
      })
      .click();
    const dialog = page.getByRole("dialog", {
      name:
        surface === "direct" ? "Start direct message" : "Switch conversation",
      exact: true,
    });
    if (surface === "direct") {
      await dialog
        .getByRole("button", { name: "Group message", exact: true })
        .click();
      await dialog
        .getByRole("combobox", { name: "Add person", exact: true })
        .click();
      await page
        .getByRole("combobox", { name: "Search add person", exact: true })
        .fill("Noah Tan");
      await page.getByRole("option", { name: "Noah Tan", exact: true }).click();
    }
    const sizes = await dialog
      .getByRole("button")
      .or(dialog.getByRole("textbox"))
      .or(dialog.getByRole("combobox"))
      .evaluateAll((nodes) =>
        nodes.map((node) => {
          const box = node.getBoundingClientRect();
          return {
            name: node.getAttribute("aria-label") ?? node.textContent,
            width: box.width,
            height: box.height,
          };
        }),
      );
    expect(sizes.filter((size) => size.width < 44 || size.height < 44)).toEqual(
      [],
    );
    for (const theme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: theme });
      if (theme === "dark")
        await expect(page.locator("html")).toHaveClass(/\bdark\b/);
      else await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);
      const path = testInfo.outputPath(
        `s06-correction-${surface}-${theme}.png`,
      );
      await page.screenshot({ path, animations: "disabled" });
      await testInfo.attach(`${surface} ${theme}`, {
        path,
        contentType: "image/png",
      });
    }
  });
}

test("S06 correction Threads destination opens the selected thread", async ({
  page,
}) => {
  const ids = await seedSidebar(page);
  await page.goto("/comms");
  await page
    .getByRole("navigation", { name: "OpenComms views", exact: true })
    .getByRole("button", { name: "Threads", exact: true })
    .click();
  const threads = page.getByRole("region", { name: "Threads", exact: true });
  await threads.getByRole("button", { name: /Morning handover/ }).click();
  await expect(page).toHaveURL(
    (url) =>
      url.searchParams.get("conversation") === ids.channel &&
      url.searchParams.has("thread") &&
      !url.searchParams.has("view"),
  );
  await expect(
    page
      .getByRole("region", { name: "Thread conversation", exact: true })
      .getByText("Thanks. I will confirm the next update with Riverside.", {
        exact: true,
      }),
  ).toBeVisible();
});

test("Comms sidebar remains usable on desktop and phone in light and dark", async ({
  page,
}, testInfo) => {
  await seedSidebar(page);
  await page.route(`**/api/users/${userId}/preferences`, (route) =>
    route.fulfill({ json: { ...profilePreferences(userId), theme: "system" } }),
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    for (const theme of ["light", "dark"] as const) {
      await page.setViewportSize(viewport);
      await page.emulateMedia({ colorScheme: theme });
      await page.goto(viewport.width < 640 ? "/comms" : "/comms?view=inbox");
      const sidebar = page.getByRole("complementary", {
        name: "Conversations",
        exact: true,
      });
      await expect(
        sidebar.getByRole("button", { name: /^operations, 2 unread/ }),
      ).toBeVisible();
      await expect(
        sidebar.getByLabel("1 mention", { exact: true }),
      ).toBeVisible();
      if (theme === "dark")
        await expect(page.locator("html")).toHaveClass(/\bdark\b/);
      else await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);
      await expectNoHorizontalScroll(page);
      const path = testInfo.outputPath(
        `s06-sidebar-${viewport.width}-${theme}.png`,
      );
      await page.screenshot({ path, animations: "disabled" });
      await testInfo.attach(`Sidebar ${viewport.width} ${theme}`, {
        path,
        contentType: "image/png",
      });
    }
  }
  expect(errors).toEqual([]);
});

test("Comms switcher searches authorized conversations and Starred keeps a real saved preference (UF-C5.1 empty text)", async ({
  page,
}) => {
  const ids = await seedSidebar(page);
  await page.goto("/comms");
  await rowAction(page, "deliveries", "Add to favorites");
  const starred = page.getByRole("region", { name: "Starred", exact: true });
  await expect(
    starred.getByRole("button", { name: /^deliveries(,|$)/ }),
  ).toBeVisible();
  await page.keyboard.press("Control+k");
  const switcher = page.getByRole("dialog", {
    name: "Switch conversation",
    exact: true,
  });
  await switcher
    .getByRole("textbox", { name: "Find a conversation", exact: true })
    .fill("does-not-exist");
  await expect(
    switcher.getByText("No conversations or people match.", { exact: true }),
  ).toBeVisible();
  await switcher
    .getByRole("textbox", { name: "Find a conversation", exact: true })
    .fill("deliver");
  await switcher
    .getByRole("button", { name: "deliveries", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`conversation=${ids.second}`));
  await page.reload();
  await expect(
    starred.getByRole("button", { name: /^deliveries(,|$)/ }),
  ).toBeVisible();
  await page.keyboard.press("Meta+k");
  await expect(switcher).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(switcher).toBeHidden();
});

test("UF-C5.1 UF-C5.2 Find a conversation lists a person and a pick opens one direct message with the composer focused", async ({
  page,
}) => {
  await seedSidebar(page, "member");
  const starts: string[] = [];
  const reads: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/comms/directs"))
      starts.push(request.url());
    if (request.url().includes("/comms/direct-candidates?"))
      reads.push(new URL(request.url()).search);
  });
  await page.goto("/comms");
  const list = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  await expect(
    list.getByRole("button", { name: /^operations,/ }),
  ).toBeVisible();
  // The candidate read runs only after text is typed, never on a cold load.
  expect(reads).toEqual([]);
  await list
    .getByRole("textbox", { name: "Search conversations", exact: true })
    .fill("Noah");
  const people = list.getByRole("region", { name: "People", exact: true });
  const noah = people.getByRole("button", { name: "Noah Tan", exact: true });
  await expect(noah).toBeVisible();
  // One read for the typed text, at most five people, shared by both slots.
  expect(reads).toEqual(["?q=Noah&limit=5"]);
  await noah.click();
  await expect(page).toHaveURL(/conversation=/);
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeFocused();
  expect(starts).toHaveLength(1);
  // UF-C5.2: the new direct now matches the text, so Noah shows once, as it.
  await expect(list.getByRole("button", { name: /^Noah Tan/ })).toHaveCount(1);
  await expect(people).toHaveCount(0);
});

test("UF-C5.1 the switcher lists a person under People and a pick opens the direct message with the composer focused", async ({
  page,
}) => {
  await seedSidebar(page, "member");
  await page.goto("/comms");
  await expect(
    page.getByRole("button", { name: /^operations,/ }),
  ).toBeVisible();
  await page.keyboard.press("Control+k");
  const switcher = page.getByRole("dialog", {
    name: "Switch conversation",
    exact: true,
  });
  await switcher
    .getByRole("textbox", { name: "Find a conversation", exact: true })
    .fill("Sofia");
  await switcher
    .getByRole("region", { name: "People", exact: true })
    .getByRole("button", { name: "Sofia Garcia", exact: true })
    .click();
  await expect(switcher).toBeHidden();
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeFocused();
  await expect(
    page
      .getByRole("complementary", { name: "Conversations", exact: true })
      .getByRole("button", { name: /^Sofia Garcia/ }),
  ).toHaveCount(1);
});

test("UF-C5.1 a failed start keeps the person and the typed name, shows why, and a second pick opens the direct message", async ({
  page,
}) => {
  await seedSidebar(page, "member");
  let failNext = true;
  await page.route(
    (url) => url.pathname === "/api/comms/directs",
    (route) => {
      if (!failNext) return route.fallback();
      failNext = false;
      return route.fulfill({
        status: 500,
        headers: answeredHeaders,
        json: { detail: "direct insert failed on replica-7" },
      });
    },
  );
  await page.goto("/comms");
  const list = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  const search = list.getByRole("textbox", {
    name: "Search conversations",
    exact: true,
  });
  await search.fill("Noah");
  const people = list.getByRole("region", { name: "People", exact: true });
  const noah = people.getByRole("button", { name: "Noah Tan", exact: true });
  await noah.click();
  const failure = people.getByRole("alert");
  await expect(failure).toContainText(
    "The conversation did not start. Try again.",
  );
  await expect(failure).toContainText(answeredReference);
  await expect(list.getByText("replica-7")).toHaveCount(0);
  await expect(noah).toBeEnabled();
  await expect(search).toHaveValue("Noah");
  await expect(page).not.toHaveURL(/conversation=/);
  await noah.click();
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeFocused();
  await expect(page).toHaveURL(/conversation=/);
  await expect(people.getByRole("alert")).toHaveCount(0);
});

test("UF-C5.3 a refused or failed people read hides People and shows no server words", async ({
  page,
}) => {
  await seedSidebar(page, "member");
  const answers = [
    { status: 403, detail: "candidate policy refused for org-17" },
    { status: 500, detail: "candidate query timeout on replica-7" },
  ];
  await page.route(
    (url) => url.pathname === "/api/comms/direct-candidates",
    (route) => {
      const answer = answers.shift();
      if (!answer) return route.fallback();
      return route.fulfill({
        status: answer.status,
        headers: answeredHeaders,
        json: { detail: answer.detail },
      });
    },
  );
  await page.goto("/comms");
  const list = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  const search = list.getByRole("textbox", {
    name: "Search conversations",
    exact: true,
  });
  for (const [text, status] of [
    ["zz", 403],
    ["zzy", 500],
  ] as const) {
    const answered = page.waitForResponse(
      (response) =>
        response.url().includes(`/comms/direct-candidates?q=${text}&`) &&
        response.status() === status,
    );
    await search.fill(text);
    await answered;
    await expect(
      list.getByText("No conversations match.", { exact: true }),
    ).toBeVisible();
    await expect(list.getByRole("region", { name: "People" })).toHaveCount(0);
    await expect(list.getByRole("alert")).toHaveCount(0);
    await expect(list.getByText(/org-17|replica-7/)).toHaveCount(0);
  }
});

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
] as const) {
  test(`FX-D1-1 FX-D1-4 UF-C5.1 at ${viewport.width}px a typed name shows only matches with the person on the first screen, and cleared text restores the list`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await seedSidebar(page, "member", true, undefined, {
      extraCategories: 6,
      emptyCategory: true,
    });
    await page.goto("/comms");
    const list = page.getByRole("complementary", {
      name: "Conversations",
      exact: true,
    });
    const yards = [1, 2, 3, 4, 5, 6];
    // The unfiltered list, by name: every section heading, hint, category
    // menu, channel row and followed record (unread counts may change).
    const expectFullList = async () => {
      for (const name of ["Starred", "Records you follow", "Direct messages"])
        await expect(
          list.getByRole("heading", { name, exact: true }),
        ).toBeVisible();
      for (const hint of [
        "Star conversations to find them here.",
        "No channels here.",
        "Start a direct or group conversation.",
      ])
        await expect(list.getByText(hint, { exact: true })).toHaveCount(1);
      for (const name of [
        "Service delivery",
        "Planning",
        ...yards.map((index) => `Yard ${index}`),
        "Yard empty",
      ])
        await expect(
          list.getByRole("button", {
            name: `Category actions: ${name}`,
            exact: true,
          }),
        ).toBeVisible();
      for (const name of [
        "operations",
        "deliveries",
        ...yards.map((index) => `yard-lane-${index}`),
      ])
        await expect(
          list.getByRole("button", { name: new RegExp(`^${name}(,|$)`) }),
        ).toBeVisible();
      await expect(
        list
          .getByRole("list", { name: "Records you follow", exact: true })
          .getByRole("button", { name: /^Riverside service visit/ }),
      ).toBeVisible();
    };
    await expectFullList();
    const search = list.getByRole("textbox", {
      name: "Search conversations",
      exact: true,
    });
    await search.fill("Noah");
    const noah = list
      .getByRole("region", { name: "People", exact: true })
      .getByRole("button", { name: "Noah Tan", exact: true });
    await expect(noah).toBeVisible();
    const box = await noah.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
    for (const hint of [
      "No channels here.",
      "Star conversations to find them here.",
      "Start a direct or group conversation.",
    ])
      await expect(list.getByText(hint, { exact: true })).toHaveCount(0);
    await search.fill("");
    await expectFullList();
  });
}

test("FX-D1-2 FX-D1-3 a typed text opens a collapsed category's matches without saving it, and filters Records you follow by title", async ({
  page,
}) => {
  await seedSidebar(page, "member");
  const writes: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "PUT" &&
      /\/comms\/categories\/[^/]+\/preferences$/.test(request.url())
    )
      writes.push(request.url());
  });
  await page.goto("/comms");
  const list = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  const deliveries = list.getByRole("button", { name: /^deliveries(,|$)/ });
  await expect(deliveries).toBeVisible();
  await list
    .getByRole("button", { name: /^Planning/ })
    .first()
    .click();
  await expect(deliveries).toBeHidden();
  await expect.poll(() => writes.length).toBe(1);
  const search = list.getByRole("textbox", {
    name: "Search conversations",
    exact: true,
  });
  await search.fill("deliver");
  await expect(deliveries).toBeVisible();
  await expect(
    list.getByRole("button", {
      name: "Category actions: Planning",
      exact: true,
    }),
  ).toBeVisible();
  await expect(list.getByRole("button", { name: /^operations,/ })).toHaveCount(
    0,
  );
  await expect(
    list.getByRole("button", {
      name: "Category actions: Service delivery",
      exact: true,
    }),
  ).toHaveCount(0);
  await search.fill("");
  await expect(deliveries).toBeHidden();
  expect(writes).toHaveLength(1);
  const followed = list.getByRole("list", {
    name: "Records you follow",
    exact: true,
  });
  await expect(followed.getByRole("button")).toHaveCount(1);
  await search.fill("riverside");
  await expect(
    followed.getByRole("button", { name: /^Riverside service visit/ }),
  ).toBeVisible();
  await search.fill("operations");
  await expect(
    list.getByRole("button", { name: /^operations,/ }),
  ).toBeVisible();
  await expect(followed).toHaveCount(0);
});

test("FX-D1-5 with nothing matching, a member sees only the no-match words and no section", async ({
  page,
}) => {
  await seedSidebar(page, "member");
  await page.goto("/comms");
  const list = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  await expect(
    list.getByRole("button", { name: /^operations,/ }),
  ).toBeVisible();
  await list
    .getByRole("textbox", { name: "Search conversations", exact: true })
    .fill("zzqx");
  await expect(
    list.getByText("No conversations or people match.", { exact: true }),
  ).toBeVisible();
  // Only the OpenComms title (h1) stays; no section heading shows.
  await expect(list.getByRole("heading", { level: 2 })).toHaveCount(0);
  await expect(
    list.getByRole("button", { name: /^Category actions/ }),
  ).toHaveCount(0);
  await expect(
    list.getByRole("list", { name: "Records you follow" }),
  ).toHaveCount(0);
});

test("FX-D1-5 a guest's typed text shows only matching rows, no People, and the old no-match words", async ({
  page,
}) => {
  const { server } = await seedSidebar(page, "guest");
  const roleCheck = page.waitForResponse((response) =>
    response.url().includes("/api/comms/capabilities/channel-creation"),
  );
  await page.goto("/comms");
  expect((await roleCheck).ok()).toBe(true);
  const list = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  const search = list.getByRole("textbox", {
    name: "Search conversations",
    exact: true,
  });
  await search.fill("oper");
  await expect(
    list.getByRole("button", { name: /^operations,/ }),
  ).toBeVisible();
  await expect(
    list.getByRole("button", { name: /^deliveries(,|$)/ }),
  ).toHaveCount(0);
  await expect(list.getByText("Starred", { exact: true })).toHaveCount(0);
  await search.fill("zzqx");
  await expect(
    list.getByText("No conversations match.", { exact: true }),
  ).toBeVisible();
  // Only the OpenComms title (h1) stays; no section heading shows.
  await expect(list.getByRole("heading", { level: 2 })).toHaveCount(0);
  await expect(list.getByRole("region", { name: "People" })).toHaveCount(0);
  expect(server.candidateQueries).toEqual([]);
});

test("FX-N2-1 a trailing space keeps a person with a direct message once, as that conversation, not under People", async ({
  page,
}) => {
  await seedSidebar(page, "member");
  await page.goto("/comms");
  const list = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  const search = list.getByRole("textbox", {
    name: "Search conversations",
    exact: true,
  });
  await search.fill("Noah");
  await list
    .getByRole("region", { name: "People", exact: true })
    .getByRole("button", { name: "Noah Tan", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeFocused();
  const read = page.waitForResponse((response) =>
    response.url().includes("/comms/direct-candidates?q=Noah+Tan&"),
  );
  await search.fill("Noah Tan ");
  await read;
  await expect(
    list.getByRole("heading", { name: "Direct messages", exact: true }),
  ).toBeVisible();
  await expect(list.getByRole("button", { name: /^Noah Tan/ })).toHaveCount(1);
  await expect(list.getByRole("region", { name: "People" })).toHaveCount(0);
});

test("FX-N2-3 in the switcher a trailing space keeps a person with a direct message once, as that conversation, not under People", async ({
  page,
}) => {
  await seedSidebar(page, "member");
  await page.goto("/comms");
  const list = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  await list
    .getByRole("textbox", { name: "Search conversations", exact: true })
    .fill("Noah");
  await list
    .getByRole("region", { name: "People", exact: true })
    .getByRole("button", { name: "Noah Tan", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Control+k");
  const switcher = page.getByRole("dialog", {
    name: "Switch conversation",
    exact: true,
  });
  const read = page.waitForResponse((response) =>
    response.url().includes("/comms/direct-candidates?q=Noah+Tan&"),
  );
  await switcher
    .getByRole("textbox", { name: "Find a conversation", exact: true })
    .fill("Noah Tan ");
  await read;
  // The only "Noah Tan" button must be the conversation, never a People row.
  await expect(
    switcher.getByRole("button", { name: "Noah Tan", exact: true }),
  ).toBeVisible();
  await expect(switcher.getByRole("region", { name: "People" })).toHaveCount(0);
  await expect(
    switcher.getByRole("button", { name: "Noah Tan", exact: true }),
  ).toHaveCount(1);
});

test("FX-N2-2 a filter of only spaces shows the full list with its hints", async ({
  page,
}) => {
  await seedSidebar(page, "member");
  await page.goto("/comms");
  const list = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  await expect(
    list.getByRole("button", { name: /^operations,/ }),
  ).toBeVisible();
  await list
    .getByRole("textbox", { name: "Search conversations", exact: true })
    .fill("   ");
  // Every section and hint of the unfiltered list stays.
  for (const hint of [
    "Star conversations to find them here.",
    "Start a direct or group conversation.",
  ])
    await expect(list.getByText(hint, { exact: true })).toBeVisible();
  for (const name of ["Starred", "Records you follow", "Direct messages"])
    await expect(
      list.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
  for (const name of ["Service delivery", "Planning"])
    await expect(
      list.getByRole("button", { name: `Category actions: ${name}` }),
    ).toBeVisible();
  await expect(
    list.getByText("No conversations match.", { exact: true }),
  ).toHaveCount(0);
});

test("FX-D2-1 on a phone a picked person opens the direct message with the composer focused", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await seedSidebar(page, "member");
  await page.goto("/comms");
  const list = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  await list
    .getByRole("textbox", { name: "Search conversations", exact: true })
    .fill("Noah");
  await list
    .getByRole("region", { name: "People", exact: true })
    .getByRole("button", { name: "Noah Tan", exact: true })
    .click();
  await expect(page).toHaveURL(/conversation=/);
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeFocused();
});

test("UF-C5.3 a guest's Find a conversation lists no people and sends no candidate read", async ({
  page,
}) => {
  const { server } = await seedSidebar(page, "guest");
  const roleCheck = page.waitForResponse((response) =>
    response.url().includes("/api/comms/capabilities/channel-creation"),
  );
  await page.goto("/comms");
  expect((await roleCheck).ok()).toBe(true);
  const list = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  await list
    .getByRole("textbox", { name: "Search conversations", exact: true })
    .fill("Noah");
  await expect(
    list.getByText("No conversations match.", { exact: true }),
  ).toBeVisible();
  await expect(list.getByRole("region", { name: "People" })).toHaveCount(0);
  expect(server.candidateQueries).toEqual([]);
});

test("Comms Inbox groups authoritative unread counts and category mute preserves mentions until unmuted", async ({
  page,
}) => {
  await seedSidebar(page);
  await page.clock.setFixedTime(new Date("2026-10-19T12:00:00Z"));
  await page.goto("/comms?view=inbox");
  const inbox = page.getByRole("region", { name: "Inbox", exact: true });
  await expect(
    inbox.getByRole("button", { name: /^operations, 2 unread/ }),
  ).toHaveCount(1);
  await expect(
    inbox.getByRole("button", { name: /^deliveries, 1 unread, 1 mention/ }),
  ).toHaveCount(1);
  await page
    .getByRole("button", { name: "Category actions: Planning", exact: true })
    .click();
  await page
    .getByRole("menuitem", { name: "Mute category for 8 hours", exact: true })
    .click();
  const sidebar = page.getByRole("complementary", {
    name: "Conversations",
    exact: true,
  });
  await expect(
    sidebar.getByRole("button", { name: /deliveries,.*muted/ }),
  ).toBeVisible();
  await expect(sidebar.getByLabel("1 mention", { exact: true })).toBeVisible();
  await page
    .getByRole("button", {
      name: "Category actions: Service delivery",
      exact: true,
    })
    .click();
  await page
    .getByRole("menuitem", {
      name: "Mute category until turned back on",
      exact: true,
    })
    .click();
  await expect(
    sidebar.getByRole("button", { name: /operations,.*muted/ }),
  ).toBeVisible();
  await expect(sidebar.getByLabel("2 unread", { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(
    sidebar.getByRole("button", { name: /operations,.*muted/ }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Category actions: Service delivery",
      exact: true,
    })
    .click();
  await page
    .getByRole("menuitem", { name: "Unmute category", exact: true })
    .click();
  await expect(sidebar.getByLabel("2 unread", { exact: true })).toBeVisible();
  await rowAction(page, "operations", "Mark read");
  await expect(
    inbox.getByRole("button", { name: /^operations(,|$)/ }),
  ).toHaveCount(0);
  await rowAction(page, "operations", "Mark unread");
  await expect(
    inbox.getByRole("button", { name: /operations, marked unread/ }),
  ).toBeVisible();
});

test("Comms starts a group from visible people, keeps the actor, and persists category order", async ({
  page,
}) => {
  await seedSidebar(page);
  await page.goto("/comms");
  await page
    .getByRole("button", { name: "Start direct message", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Start direct message",
    exact: true,
  });
  await dialog
    .getByRole("button", { name: "Group message", exact: true })
    .click();
  await dialog
    .getByRole("textbox", { name: "Group name", exact: true })
    .fill("Dispatch planning");
  await expect(
    dialog.getByRole("button", { name: "Start conversation", exact: true }),
  ).toBeDisabled();
  const start = dialog.getByRole("button", {
    name: "Start conversation",
    exact: true,
  });
  // TASK-0061 rule 6: a blocked primary says why, as its description.
  await expect(start).toHaveAccessibleDescription(
    "Choose at least two other people.",
  );
  for (const name of ["Noah Tan", "Sofia Garcia"]) {
    await dialog
      .getByRole("combobox", { name: "Add person", exact: true })
      .click();
    await page
      .getByRole("combobox", { name: "Search add person", exact: true })
      .fill(name);
    await page.getByRole("option", { name, exact: true }).click();
  }
  await expect(start).not.toHaveAccessibleDescription(
    "Choose at least two other people.",
  );
  // TASK-0061 rule 4: while the create request runs, the button says it is
  // busy in place and keeps the keyboard focus.
  const create = heldResponse();
  await page.route(
    (url) => url.pathname.endsWith("/api/comms/groups"),
    async (route) => {
      if (route.request().method() === "POST") {
        create.enter();
        await create.released;
      }
      await route.fallback();
    },
  );
  await start.click();
  await create.entered;
  const starting = dialog.getByRole("button", {
    name: "Starting…",
    exact: true,
  });
  await expect(starting).toHaveAttribute("aria-busy", "true");
  await expect(starting).toBeDisabled();
  await expect(starting).toBeFocused();
  create.release();
  await expect(dialog).toBeHidden();
  await expect(
    page.getByRole("heading", { name: "Dispatch planning", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Members", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Members 3", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Category actions: Planning", exact: true })
    .click();
  await page
    .getByRole("menuitem", { name: "Move category up", exact: true })
    .click();
  const categories = page
    .getByRole("complementary", { name: "Conversations", exact: true })
    .getByRole("button", { name: /^(Planning|Service delivery).*Operations/ });
  // The move saves over HTTP; reload only after the saved order is shown.
  await expect(categories).toHaveText([/Planning/, /Service delivery/]);
  await page.reload();
  await expect(categories).toHaveText([/Planning/, /Service delivery/]);
  await expect(
    page.getByRole("heading", { name: "Dispatch planning", exact: true }),
  ).toBeVisible();
});

test("Comms Activity reads real stored notifications and removes a deleted source", async ({
  page,
}) => {
  await seedSidebar(page, "admin", true, undefined, { notifications: true });
  await page.goto("/comms");
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  const activity = page.getByRole("region", { name: "Activity", exact: true });
  await activity
    .getByRole("button", { name: "Mention in deliveries", exact: true })
    .click();
  const message = page
    .getByRole("article")
    .filter({ hasText: "Planning tomorrow's deliveries" });
  await expect(message).toBeInViewport();
  await message.getByRole("button", { name: /^Message actions:/ }).click();
  await page
    .getByRole("menuitem", { name: "Delete message", exact: true })
    .click();
  await expect(
    page.getByText("Message removed", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(
    activity.getByText("No activity yet.", { exact: true }),
  ).toBeVisible();
});

test("Comms keeps a refused group draft and applies a newly admitted guest role", async ({
  page,
}) => {
  const { server } = await seedSidebar(page, "admin", true, "empty");
  await page.goto("/comms");
  await page
    .getByRole("button", { name: "Start direct message", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Start direct message",
    exact: true,
  });
  await dialog
    .getByRole("button", { name: "Group message", exact: true })
    .click();
  await dialog
    .getByRole("textbox", { name: "Group name", exact: true })
    .fill("Keep this group draft");
  for (const name of ["Noah Tan", "Sofia Garcia"]) {
    await dialog
      .getByRole("combobox", { name: "Add person", exact: true })
      .click();
    await page
      .getByRole("combobox", { name: "Search add person", exact: true })
      .fill(name);
    await page.getByRole("option", { name, exact: true }).click();
  }
  // An administrator can choose these people without shared conversations.
  // Fresh member admission removes that eligibility while preserving the draft;
  // the search-first picker keeps the names it showed at selection.
  await signedInAs(page, { id: userId, role: "member" });
  server.setRole("member");
  await page.evaluate(() => window.dispatchEvent(new FocusEvent("focus")));
  await expect(
    dialog.getByRole("button", { name: /^Remove (Noah Tan|Sofia Garcia)$/ }),
  ).toHaveCount(2);
  await dialog
    .getByRole("button", { name: "Start conversation", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(
    dialog.getByRole("textbox", { name: "Group name", exact: true }),
  ).toHaveValue("Keep this group draft");
  await expect(
    dialog.getByRole("button", { name: /^Remove (Noah Tan|Sofia Garcia)$/ }),
  ).toHaveCount(2);
  await expect(
    page.getByRole("heading", { name: "Keep this group draft", exact: true }),
  ).toHaveCount(0);
  await signedInAs(page, { id: userId, role: "admin" });
  server.setRole("admin");
  await page.evaluate(() => window.dispatchEvent(new FocusEvent("focus")));
  await expect(
    dialog.getByRole("button", { name: "Remove Noah Tan", exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Remove Sofia Garcia", exact: true }),
  ).toBeVisible();
  // A guest admission while the dialog is open refuses the draft in place.
  await signedInAs(page, { id: userId, role: "guest" });
  server.setRole("guest");
  await page.evaluate(() => window.dispatchEvent(new FocusEvent("focus")));
  await expect(
    dialog.getByText("Guests cannot start conversations.", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Start conversation", exact: true }),
  ).toBeDisabled();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  // After a reload the guest is never offered the dialog again.
  await page.reload();
  await expect(
    page.getByRole("region", { name: "No conversations yet", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Start direct message", exact: true }),
  ).toHaveCount(0);
});

test("Comms guest cannot create a group and the channel browser has useful no-match state", async ({
  page,
}) => {
  await seedSidebar(page, "guest");
  // The start actions wait for the role check, so absence counts only after it.
  const roleCheck = page.waitForResponse((response) =>
    response.url().includes("/api/comms/capabilities/channel-creation"),
  );
  await page.goto("/comms");
  expect((await roleCheck).ok()).toBe(true);
  await expect(
    page.getByRole("button", { name: /^operations,/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Start direct message", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Browse channels", exact: true })
    .click();
  const browser = page.getByRole("region", {
    name: "Browse channels",
    exact: true,
  });
  await browser
    .getByRole("textbox", { name: "Find a channel", exact: true })
    .fill("does-not-exist");
  await expect(
    browser.getByText("No channels match.", { exact: true }),
  ).toBeVisible();
});
