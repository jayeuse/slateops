/**
 * BD3: when the dashboard page shows the set-up state with presets.
 *
 * - `create`: the department has no dashboard. Managers get the presets, and
 *   a preset creates the home; readers see that none exists.
 * - `fill`: the shown dashboard is the department's home and has no widgets,
 *   and the viewer can manage it. A preset fills that home.
 * - `null`: show the dashboard (an empty home stays an empty grid for readers).
 */
export type DashboardSetup = "create" | "fill" | null;

export function dashboardSetup(input: {
  listLoaded: boolean;
  editing: boolean;
  /** The address names one dashboard, which is not the setup state. */
  dashboardRequested: boolean;
  shown: { id: string; isHome: boolean; widgets: readonly unknown[] } | null;
  homeId: string | null;
  canManage: boolean;
}): DashboardSetup {
  if (!input.listLoaded || input.editing) return null;
  const { shown } = input;
  if (!shown) return input.dashboardRequested ? null : "create";
  const isHome = shown.isHome || shown.id === input.homeId;
  return isHome && shown.widgets.length === 0 && input.canManage
    ? "fill"
    : null;
}
