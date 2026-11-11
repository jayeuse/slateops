import { expect, test } from "@playwright/test";
import { dashboardSetup } from "../../../src/components/systems/openview/domain/dashboard-setup";

const home = { id: "home", isHome: true, widgets: [] };
const loaded = {
  listLoaded: true,
  editing: false,
  dashboardRequested: false,
  homeId: "home",
};

// QA-1 (BD3 with the setup spec): a new department's home exists from the
// publish, so an empty home must still offer its managers the presets, and
// a preset fills that home instead of creating another.
test("an empty home offers its managers the presets, and readers keep the dashboard", () => {
  expect(dashboardSetup({ ...loaded, shown: home, canManage: true })).toBe(
    "fill",
  );
  // A home the list marks only by id is the same home.
  expect(
    dashboardSetup({
      ...loaded,
      shown: { ...home, isHome: false },
      canManage: true,
    }),
  ).toBe("fill");
  expect(dashboardSetup({ ...loaded, shown: home, canManage: false })).toBe(
    null,
  );
});

test("a dashboard with widgets, another empty dashboard, or an open edit shows the dashboard", () => {
  expect(
    dashboardSetup({
      ...loaded,
      shown: { ...home, widgets: [{}] },
      canManage: true,
    }),
  ).toBe(null);
  expect(
    dashboardSetup({
      ...loaded,
      shown: { id: "other", isHome: false, widgets: [] },
      canManage: true,
    }),
  ).toBe(null);
  expect(
    dashboardSetup({ ...loaded, editing: true, shown: home, canManage: true }),
  ).toBe(null);
  expect(
    dashboardSetup({
      ...loaded,
      listLoaded: false,
      shown: home,
      canManage: true,
    }),
  ).toBe(null);
});

test("a department with no dashboard keeps the create setup for everyone", () => {
  for (const canManage of [true, false])
    expect(dashboardSetup({ ...loaded, shown: null, canManage })).toBe(
      "create",
    );
  expect(
    dashboardSetup({
      ...loaded,
      dashboardRequested: true,
      shown: null,
      canManage: true,
    }),
  ).toBe(null);
});
