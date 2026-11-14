"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { skipToken, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  Building2,
  ChevronRight,
  FileText,
  FolderKanban,
  Settings,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  accessNavigationFor,
  auditDepartmentsFor,
  installationOwnerFor,
  getWorkspaceNavigation,
  getWorkspaceTools,
  isWorkspaceNavigationGroupActive,
  isWorkspaceNavigationItemActive,
} from "@/components/workspace-navigation";
import { useWorkspaceNavigationRequest } from "@/components/workspace-navigation-guard";
import {
  useVerifiedWorkspaceUserId,
  useWorkspaceInteractionSuspended,
} from "@/components/systems/shared/runtime/workspace-identity";
import {
  authMeOptions,
  prefetchOpenViewSection,
} from "@/components/systems/openview/adapters/openview-queries";
import {
  prefetchManageJobs,
  prefetchManageWorkspace,
} from "@/components/systems/manage/adapters/manage-queries";
import { prefetchPlatformSection } from "@/components/systems/platform/adapters/platform-queries";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import { DepartmentMark } from "@/components/sandbox/department-mark";
import { useDepartmentNavigation } from "@/components/department-navigation";
import {
  currentDashboardDepartmentId,
  currentModuleId,
  dashboardHref,
  isRefusal,
  moduleHref,
} from "@/components/department-navigation-model";
import {
  announcementsHref,
  boardsGroupRows,
  boardsNavigationKey,
  boardsPlace,
  type NavigationBoard,
} from "@/components/boards-navigation-model";

// Reads the board list when the Boards group opens away from /boards, where
// the page reads it; only this loader ships with the shell (BR2).
const BoardsNavigationReader = dynamic(() =>
  import("@/components/boards-navigation-reader").then(
    (module) => module.BoardsNavigationReader,
  ),
);

const groupIcons = {
  sandbox: Workflow,
  boards: FolderKanban,
  access: ShieldCheck,
  openview: BarChart3,
  manage: Settings,
  platform: FileText,
} as const;

// Icons of the Tools' top-level rows (Files, and Manage's two rows when they
// are all of Manage a person sees).
const rowIcons = {
  files: FileText,
  organization: Building2,
  health: Activity,
} as const;

const PREFETCH_INTENT_DELAY_MS = 120;
const MAX_PREFETCHED_ROUTES = 12;

/**
 * Where the navigation renders. The sidebar shows one-line rows that carry
 * their description as a title and `aria-description`; the phone drawer
 * shows the description as a visible second line.
 */
export type NavigationSurface = "sidebar" | "drawer";

// Row sizes and the active ink live on the rows themselves, not on an
// `.app-shell` rule, so they also apply inside the drawer's portal.
// Sidebar rows keep the 44px floor and become 32px from 1280px; in the
// collapsed rail they are square targets of the same sizes.
const sidebarRowSize =
  "min-h-11 xl:min-h-8 group-data-[collapsible=icon]:size-11! xl:group-data-[collapsible=icon]:size-8!";
const drawerRowSize = "min-h-11";

/** The size classes of a sidebar or drawer row (workspace, OpenComms, account). */
export function navigationRowSize(surface: NavigationSurface) {
  return surface === "drawer" ? drawerRowSize : sidebarRowSize;
}

/** The current place: `--action-text` at weight 600, in the sidebar and the drawer. */
export const navigationActiveInk =
  "data-active:text-action-text data-active:font-semibold";

/** Line icons in the shell's rows. */
export const navigationIconStroke = "[&_svg]:stroke-[1.65]";

// The current place is its label in `--action-text` at weight 600, never a
// fill or a bar (Human Owner, 2026-11-13). The collapsed rail shows icons
// only, so it keeps its fill.
const noActiveFill =
  "data-active:bg-transparent group-data-[collapsible=icon]:data-active:bg-sidebar-accent";

/** A top-level row (workspace rows, OpenComms, the account row): no fill when current. */
export const navigationNoActiveFill = noActiveFill;

/** A group row takes the current place's ink only while closed; open, its page carries it. */
const groupActiveInk = `${noActiveFill} data-active:not-data-panel-open:text-action-text data-active:not-data-panel-open:font-semibold`;

/**
 * The guide line of a group's pages: 1px down the left, turning into the last
 * page, as a tree line does. The gap between pages (2px) is bridged.
 */
const guideLine =
  "before:pointer-events-none before:absolute before:top-0 before:-bottom-0.5 before:-left-2.5 before:w-px before:bg-(--sidebar-border) last:before:bottom-auto last:before:h-[calc(50%+0.5px)] last:before:w-2 last:before:rounded-bl-md last:before:border-b last:before:border-l last:before:border-(--sidebar-border) last:before:bg-transparent";

interface AppNavigationProps {
  pathname: string;
  searchParams: URLSearchParams;
  surface?: NavigationSurface;
  collapsed?: boolean;
  onExpandSidebar?: () => void;
}

export function AppNavigation({
  pathname,
  searchParams,
  surface = "sidebar",
  collapsed = false,
  onExpandSidebar,
}: AppNavigationProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const requestNavigation = useWorkspaceNavigationRequest();
  const descriptionIdPrefix = useId();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [hash, setHash] = useState("");
  const prefetchTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(
    new Map(),
  );
  const prefetchedRoutes = useRef(new Set<string>());
  // Access shows only what the signed-in role and manage access allow; it
  // stays hidden until the identity is known.
  const identity = useQuery(authMeOptions());
  const userId = useVerifiedWorkspaceUserId();
  const suspended = useWorkspaceInteractionSuspended();
  const [jobsAwaitingRole, setJobsAwaitingRole] = useState(false);
  const jobsCycle = useRef(0);
  const jobsAdmission = useRef(false);
  const jobsAdmitted =
    !suspended &&
    !jobsAwaitingRole &&
    identity.isSuccess &&
    !identity.isError &&
    identity.data.id === userId &&
    identity.data.currentOrganization?.role === "admin";
  useLayoutEffect(() => {
    jobsAdmission.current = jobsAdmitted;
    if (suspended) {
      jobsCycle.current += 1;
      setJobsAwaitingRole(true);
    }
  }, [suspended, jobsAdmitted]);
  useEffect(() => {
    if (suspended || !jobsAwaitingRole) return;
    const cycle = jobsCycle.current;
    let cancelled = false;
    void queryClient
      .cancelQueries({ queryKey: authMeOptions().queryKey, exact: true })
      .then(() =>
        !cancelled && cycle === jobsCycle.current
          ? queryClient.fetchQuery({ ...authMeOptions(), staleTime: 0 })
          : undefined,
      )
      .then((result) => {
        if (result && !cancelled && cycle === jobsCycle.current)
          setJobsAwaitingRole(false);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [suspended, jobsAwaitingRole, queryClient]);
  // Roles belong to memberships: the current organization's role decides.
  const access = accessNavigationFor(identity.data);
  const groups = getWorkspaceNavigation(
    pathname,
    searchParams,
    access,
    jobsAdmitted,
    installationOwnerFor(identity.data),
    (auditDepartmentsFor(identity.data)?.length ?? 0) > 0,
  );
  const tools = getWorkspaceTools(groups, access);
  const departments = useDepartmentNavigation(pathname, searchParams);
  const moduleId = currentModuleId(pathname, searchParams);
  const dashboardDepartmentId = currentDashboardDepartmentId(
    pathname,
    searchParams,
  );
  const place = boardsPlace(pathname, searchParams);
  const announcementsDepartmentId =
    place?.kind === "department" ? place.departmentId : null;
  // The board list the Boards page or the reader caches; never read here.
  const boardList = useQuery<{ items: NavigationBoard[] }>({
    queryKey: boardsNavigationKey(),
    queryFn: skipToken,
  });
  // A refused read keeps its last data in the cache; the rows drop it.
  const boardItems = isRefusal(boardList.error)
    ? undefined
    : boardList.data?.items;
  const boardRows = boardsGroupRows(place, boardItems);
  // A Board id may name a department's board, which its department group
  // holds (BR1), so the Boards group waits for the list to know it.
  const boardsActive =
    place !== null &&
    place.kind !== "department" &&
    (place.kind !== "board" ||
      (boardItems !== undefined &&
        !boardItems.some(
          (board) => board.id === place.boardId && board.scope === "department",
        )));
  const groupActive = (group: (typeof groups)[number]) =>
    group.id === "boards"
      ? boardsActive
      : isWorkspaceNavigationGroupActive(group, pathname);
  const search = searchParams.toString();
  const activeGroupId = groups.find(groupActive)?.id;
  const boardsOpen =
    !collapsed &&
    (expanded.boards ?? activeGroupId === "boards") &&
    groups.some((group) => group.id === "boards");
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const syncHash = () => setHash(window.location.hash);
    syncHash();
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, [pathname]);

  useEffect(() => {
    if (!activeGroupId) return;
    setExpanded((current) =>
      current[activeGroupId] ? current : { ...current, [activeGroupId]: true },
    );
  }, [activeGroupId, search]);

  useEffect(() => {
    const timers = prefetchTimers.current;
    return () => {
      for (const timer of timers.values()) clearTimeout(timer);
      timers.clear();
    };
  }, []);

  function schedulePrefetch(href: string) {
    if (prefetchTimers.current.has(href)) return;
    const timer = setTimeout(() => {
      prefetchTimers.current.delete(href);
      // Data can go stale between visits, so each intent may refresh it;
      // the cache skips reads that are still fresh.
      prefetchOpenViewSection(queryClient, href);
      prefetchPlatformSection(queryClient, href, identity.data?.id);
      if (href === "/manage?view=jobs" && jobsAdmission.current)
        void prefetchManageJobs(queryClient);
      if (
        identity.data?.currentOrganization?.role === "admin" &&
        href === "/manage?view=organization"
      )
        void prefetchManageWorkspace(queryClient);
      if (prefetchedRoutes.current.has(href)) return;
      prefetchedRoutes.current.add(href);
      if (prefetchedRoutes.current.size > MAX_PREFETCHED_ROUTES) {
        const oldest = prefetchedRoutes.current.values().next().value;
        if (oldest) prefetchedRoutes.current.delete(oldest);
      }
      router.prefetch(href as Route);
    }, PREFETCH_INTENT_DELAY_MS);
    prefetchTimers.current.set(href, timer);
  }

  function cancelPrefetch(href: string) {
    const timer = prefetchTimers.current.get(href);
    if (timer === undefined) return;
    clearTimeout(timer);
    prefetchTimers.current.delete(href);
  }

  function navigate(href: string, event: { preventDefault: () => void }) {
    const accepted = requestNavigation(href, () => router.push(href as Route));
    if (!accepted) event.preventDefault();
  }

  function renderGroup(group: {
    key: string;
    label: string;
    description?: string;
    icon: ReactNode;
    active: boolean;
    /** Open before the person toggles it; the active group by default. */
    defaultOpen?: boolean;
    listLabel?: string;
    items: { id: string; label: string; href: string; active: boolean }[];
  }) {
    const open =
      !collapsed && (expanded[group.key] ?? group.defaultOpen ?? group.active);
    const showDescription = Boolean(
      surface === "drawer" && group.description && !open,
    );
    const descriptionId = `${descriptionIdPrefix}-${group.key}-description`;
    return (
      <Collapsible
        key={group.key}
        render={<SidebarMenuItem />}
        open={open}
        onOpenChange={(nextOpen) =>
          setExpanded((current) => ({ ...current, [group.key]: nextOpen }))
        }
      >
        <CollapsibleTrigger
          render={
            <SidebarMenuButton
              isActive={group.active}
              aria-label={group.label}
              aria-describedby={showDescription ? descriptionId : undefined}
              // The sidebar row is one line; its description is the
              // tooltip and the accessible description.
              aria-description={
                surface === "sidebar"
                  ? group.description || undefined
                  : undefined
              }
              title={
                surface === "drawer"
                  ? undefined
                  : collapsed
                    ? group.description
                      ? `${group.label} — ${group.description}`
                      : group.label
                    : group.description || undefined
              }
              className={cn(
                navigationRowSize(surface),
                navigationIconStroke,
                groupActiveInk,
                showDescription && "h-auto py-1.5",
              )}
            />
          }
          onClick={() => {
            if (collapsed) onExpandSidebar?.();
          }}
        >
          {group.icon}
          <span className="flex min-w-0 flex-col">
            <span className="truncate">{group.label}</span>
            {showDescription ? (
              <span
                id={descriptionId}
                className="text-sidebar-muted truncate text-xs font-normal"
              >
                {group.description}
              </span>
            ) : null}
          </span>
          <ChevronRight
            aria-hidden="true"
            className={cn(
              "ml-auto size-4 transition-transform duration-(--motion-base) ease-(--ease-out) motion-reduce:transition-none",
              open && "rotate-90",
            )}
          />
        </CollapsibleTrigger>
        <CollapsibleContent className="h-(--collapsible-panel-height) overflow-clip transition-[height] duration-(--motion-base) ease-(--ease-out) data-ending-style:h-0 data-starting-style:h-0 motion-reduce:transition-none">
          <SidebarMenuSub
            className="mr-0 gap-0.5 border-l-0 pr-0"
            aria-label={group.listLabel}
          >
            {group.items.map((item) => (
              <SidebarMenuSubItem key={item.id} className={guideLine}>
                <SidebarMenuSubButton
                  render={
                    <Link
                      href={item.href as Route}
                      prefetch={false}
                      onNavigate={(event) => navigate(item.href, event)}
                      onPointerEnter={() => schedulePrefetch(item.href)}
                      onPointerLeave={() => cancelPrefetch(item.href)}
                      onFocus={() => schedulePrefetch(item.href)}
                      onBlur={() => cancelPrefetch(item.href)}
                    />
                  }
                  isActive={item.active}
                  aria-current={item.active ? "page" : undefined}
                  // The nav's one bar marks this page on the guide line, so
                  // it can glide from page to page.
                  className={cn(
                    surface === "drawer" ? "min-h-11" : "min-h-11 xl:min-h-8",
                    navigationActiveInk,
                    "data-active:bg-transparent",
                  )}
                >
                  <span className="truncate">{item.label}</span>
                </SidebarMenuSubButton>
              </SidebarMenuSubItem>
            ))}
          </SidebarMenuSub>
        </CollapsibleContent>
      </Collapsible>
    );
  }

  // A top-level Tools row opens one section, as the OpenComms row does: it
  // carries its own active fill, and its description like a group's.
  function renderRow(row: {
    key: string;
    label: string;
    description?: string;
    icon: ReactNode;
    href: string;
    active: boolean;
  }) {
    const showDescription = Boolean(surface === "drawer" && row.description);
    const descriptionId = `${descriptionIdPrefix}-${row.key}-description`;
    return (
      <SidebarMenuItem key={row.key}>
        <SidebarMenuButton
          render={
            <Link
              href={row.href as Route}
              prefetch={false}
              onNavigate={(event) => navigate(row.href, event)}
              onPointerEnter={() => schedulePrefetch(row.href)}
              onPointerLeave={() => cancelPrefetch(row.href)}
              onFocus={() => schedulePrefetch(row.href)}
              onBlur={() => cancelPrefetch(row.href)}
            />
          }
          isActive={row.active}
          aria-current={row.active ? "page" : undefined}
          aria-label={row.label}
          aria-describedby={showDescription ? descriptionId : undefined}
          aria-description={
            surface === "sidebar" ? row.description || undefined : undefined
          }
          title={
            surface === "drawer"
              ? undefined
              : collapsed
                ? row.description
                  ? `${row.label} — ${row.description}`
                  : row.label
                : row.description || undefined
          }
          className={cn(
            navigationRowSize(surface),
            navigationActiveInk,
            navigationIconStroke,
            navigationNoActiveFill,
            showDescription && "h-auto py-1.5",
          )}
        >
          {row.icon}
          <span className="flex min-w-0 flex-col">
            <span className="truncate">{row.label}</span>
            {showDescription ? (
              <span
                id={descriptionId}
                className="text-sidebar-muted truncate text-xs font-normal"
              >
                {row.description}
              </span>
            ) : null}
          </span>
        </SidebarMenuButton>
      </SidebarMenuItem>
    );
  }

  return (
    <SidebarGroup className="p-0">
      <nav
        ref={navRef}
        aria-label="Main navigation"
        className="relative isolate"
      >
        {departments.length > 0 && collapsed ? (
          // One rail button for every department (DA6); it opens the sidebar.
          <SidebarMenu className="gap-0.5">
            <SidebarMenuItem>
              <SidebarMenuButton
                aria-label="Departments"
                title="Departments"
                isActive={moduleId !== null || dashboardDepartmentId !== null}
                className={cn(navigationRowSize(surface), navigationIconStroke)}
                onClick={() => {
                  onExpandSidebar?.();
                  // This button leaves with the rail; focus moves to the
                  // current department, or the first one.
                  requestAnimationFrame(() => {
                    const list = navRef.current?.querySelector(
                      `[aria-labelledby="${descriptionIdPrefix}-departments"]`,
                    );
                    list
                      ?.querySelector<HTMLElement>(
                        'button[data-active="true"], button',
                      )
                      ?.focus();
                  });
                }}
              >
                <BarChart3 aria-hidden="true" />
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        ) : departments.length > 0 ? (
          <>
            <div
              id={`${descriptionIdPrefix}-departments`}
              className="text-sidebar-muted px-2 pb-1 text-xs font-medium"
            >
              Departments
            </div>
            <SidebarMenu
              className="gap-0.5"
              aria-labelledby={`${descriptionIdPrefix}-departments`}
            >
              {departments.map((department) =>
                renderGroup({
                  key: `department:${department.id}`,
                  label: department.name,
                  icon: (
                    <span className="grid size-4 place-items-center">
                      <DepartmentMark departmentIndex={department.index} />
                    </span>
                  ),
                  active:
                    department.id === dashboardDepartmentId ||
                    department.id === announcementsDepartmentId ||
                    department.modules.some((module) => module.id === moduleId),
                  listLabel: `${department.name} pages`,
                  // The department's home dashboard comes first (BD1), then
                  // its board, Announcements (BR1, BR47).
                  items: [
                    {
                      id: "dashboard",
                      label: "Dashboard",
                      href: dashboardHref(department.id),
                      active: department.id === dashboardDepartmentId,
                    },
                    {
                      id: "announcements",
                      label: "Announcements",
                      href: announcementsHref(department.id),
                      active: department.id === announcementsDepartmentId,
                    },
                    ...department.modules.map((module) => ({
                      id: module.id,
                      label: module.name,
                      href: moduleHref(module.id),
                      active: module.id === moduleId,
                    })),
                  ],
                }),
              )}
            </SidebarMenu>
            <div className="text-sidebar-muted px-2 pt-3 pb-1 text-xs font-medium">
              Tools
            </div>
          </>
        ) : null}
        <SidebarMenu className="gap-0.5">
          {tools.map((tool) => {
            if (tool.kind === "row") {
              const Icon = rowIcons[tool.itemId as keyof typeof rowIcons];
              return renderRow({
                key: `${tool.groupId}:${tool.id}`,
                label: tool.label,
                description: tool.description,
                icon: <Icon aria-hidden="true" />,
                href: tool.href,
                active: isWorkspaceNavigationItemActive(
                  tool.groupId,
                  tool.itemId,
                  pathname,
                  searchParams,
                  hash,
                ),
              });
            }
            const group = tool.group;
            const Icon = groupIcons[group.id as keyof typeof groupIcons];
            const items =
              group.id === "boards"
                ? boardRows
                : group.items.map((item) => ({
                    id: item.id,
                    label: item.label,
                    href: item.href,
                    active: isWorkspaceNavigationItemActive(
                      group.id,
                      item.id,
                      pathname,
                      searchParams,
                      hash,
                    ),
                  }));
            return renderGroup({
              key: group.id,
              label: group.label,
              description: group.description,
              icon: <Icon aria-hidden="true" />,
              // Search and Notifications share /platform but have no row
              // here, so Files is current only on its own sections (DR-7.6);
              // it still opens on every /platform page.
              ...(group.id === "platform"
                ? {
                    active: items.some((item) => item.active),
                    defaultOpen: groupActive(group),
                  }
                : { active: groupActive(group) }),
              ...(group.id === "boards" ? { listLabel: "Boards" } : {}),
              items,
            });
          })}
        </SidebarMenu>
        {boardsOpen && pathname !== "/boards" ? (
          <BoardsNavigationReader />
        ) : null}
      </nav>
    </SidebarGroup>
  );
}
