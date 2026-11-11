"use client";

import {
  createContext,
  useContext,
  useId,
  useState,
  type ReactNode,
} from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { DepartmentSetup } from "../domain/model";
import type { SandboxPublicationChange } from "../state/api";

type Change = SandboxPublicationChange;
/**
 * The part of the draft needed to place changes: field changes under their
 * module, setup changes under their department, and the sidebar note.
 */
export type PublishReviewDesign = {
  departments: ReadonlyArray<{
    id: string;
    name: string;
    closed: boolean;
    /** The draft setup choice (BE-SD5); absent means every item is on. */
    setup?: DepartmentSetup;
  }>;
  modules: ReadonlyArray<{
    id: string;
    departmentId: string;
    name: string;
    closed: boolean;
    fields: ReadonlyArray<{ id: string }>;
  }>;
};
type Kind = Change["kind"];
type SetupKind = Extract<
  Kind,
  "group" | "dashboard" | "board" | "category" | "channel"
>;

const KIND_NOUNS: Record<Kind, readonly [string, string]> = {
  department: ["department", "departments"],
  group: ["group", "groups"],
  dashboard: ["dashboard", "dashboards"],
  board: ["Board", "Boards"],
  category: ["category", "categories"],
  channel: ["channel", "channels"],
  module: ["module", "modules"],
  field: ["field", "fields"],
  relationship: ["relationship", "relationships"],
  trigger: ["trigger", "triggers"],
};
const KIND_ORDER: readonly Kind[] = [
  "department",
  "group",
  "dashboard",
  "board",
  "category",
  "channel",
  "module",
  "field",
  "relationship",
  "trigger",
];
const SETUP_KIND_WORDS: Record<SetupKind, string> = {
  group: "Group",
  dashboard: "Dashboard",
  board: "Board",
  category: "Category",
  channel: "Channel",
};
// The setup of one department, in R2 order. A setup change's `sandboxId` is
// `<department sandboxId>#<role>` (BE-SD2).
const SETUP_ROLE_ORDER = [
  "managers",
  "members",
  "viewers",
  "dashboard",
  "board",
  "category",
  "channel",
];
const ACTION_LABELS: Record<Change["action"], string> = {
  create: "New",
  update: "Changed",
  close: "Closed",
  reopen: "Reopened",
};

function isSetupKind(kind: Kind): kind is SetupKind {
  return kind in SETUP_KIND_WORDS;
}

/** OpenComms archives and restores a channel; it never closes one. */
function chipWord(change: Change): string {
  if (change.kind === "channel" && change.action === "close") return "Archived";
  if (change.kind === "channel" && change.action === "reopen")
    return "Restored";
  return ACTION_LABELS[change.action];
}

/** The department and role of a setup change; the role follows the last "#". */
function setupParent(change: Change) {
  const split = change.sandboxId.lastIndexOf("#");
  if (split <= 0) return null;
  return {
    departmentId: change.sandboxId.slice(0, split),
    role: change.sandboxId.slice(split + 1),
  };
}

function setupRank(change: Change): number {
  const rank = SETUP_ROLE_ORDER.indexOf(setupParent(change)?.role ?? "");
  return rank < 0 ? SETUP_ROLE_ORDER.length : rank;
}
// Groups longer than this show a "Show all" control.
const VISIBLE_ROWS = 5;

function counted(count: number, [one, many]: readonly [string, string]) {
  return `${count} ${count === 1 ? one : many}`;
}

const SHARED_ACTION_WORDS: Partial<Record<Change["action"], string>> = {
  create: "new",
  close: "closed",
  reopen: "reopened",
};

/**
 * The review's plain summary (F11): a count per kind, such as "7 trigger
 * changes" or "3 module changes · 7 trigger changes". When every change
 * shares one action that says more than "changes" (a first publish), the
 * rows drop their chips and the summary says it once: "2 new modules".
 */
export function publicationChangeSummary(changes: readonly Change[]): string {
  const action = sharedAction(changes);
  const shared = action ? SHARED_ACTION_WORDS[action] : undefined;
  return KIND_ORDER.flatMap((kind) => {
    const count = changes.filter((change) => change.kind === kind).length;
    if (!count) return [];
    const [one, many] = KIND_NOUNS[kind];
    return shared
      ? [`${count} ${shared} ${count === 1 ? one : many}`]
      : [`${count} ${one} ${count === 1 ? "change" : "changes"}`];
  }).join(" · ");
}

/** The one action every change shares, such as a first publish. */
function sharedAction(changes: readonly Change[]): Change["action"] | null {
  const first = changes[0]?.action;
  return first && changes.every((change) => change.action === first)
    ? first
    : null;
}

// When every change shares one action, the summary says it once and rows
// drop their action chips.
const ShowActions = createContext(true);

/**
 * The publication planner names a field change by its module and field
 * (backend `publications/rules.py` `_field_key`). Keys over 1,000 characters
 * are hashed there, so those fields stay in "Other". IDs are ASCII, so
 * `length` matches the planner's character count.
 */
export function publicationFieldKey(moduleId: string, fieldId: string) {
  return `field:raw:${moduleId.length}:${moduleId}:${fieldId}`;
}

type ModuleEntry = {
  id: string;
  name: string;
  change?: Change;
  fields: Change[];
};

type DepartmentEntry = {
  id: string;
  name: string;
  change?: Change;
  setup: Change[];
};

/**
 * Sort changes into reading order. Setup changes nest under their department
 * (SD23), in R2 order. Field changes nest under their module when the draft
 * design still holds the field; the rest go to "Other".
 */
export function groupPublicationChanges(
  changes: readonly Change[],
  design: PublishReviewDesign,
) {
  const moduleOfField = new Map(
    design.modules.flatMap((item) =>
      item.fields.map(
        (field) => [publicationFieldKey(item.id, field.id), item] as const,
      ),
    ),
  );
  const draftDepartments = new Map(
    design.departments.map((item) => [item.id, item.name] as const),
  );
  const departments = new Map<string, DepartmentEntry>();
  const modules = new Map<string, ModuleEntry>();
  const other: Change[] = [];
  for (const change of changes) {
    if (change.kind === "department") {
      const entry = departments.get(change.sandboxId);
      if (entry) Object.assign(entry, { name: change.label, change });
      else
        departments.set(change.sandboxId, {
          id: change.sandboxId,
          name: change.label,
          change,
          setup: [],
        });
      continue;
    }
    if (isSetupKind(change.kind)) {
      const parent = setupParent(change);
      if (!parent) {
        other.push(change);
        continue;
      }
      const entry = departments.get(parent.departmentId) ?? {
        id: parent.departmentId,
        name: draftDepartments.get(parent.departmentId) ?? "",
        setup: [],
      };
      entry.setup.push(change);
      departments.set(parent.departmentId, entry);
      continue;
    }
    if (change.kind === "module") {
      const entry = modules.get(change.sandboxId);
      if (entry) entry.change = change;
      else
        modules.set(change.sandboxId, {
          id: change.sandboxId,
          name: change.label,
          change,
          fields: [],
        });
    }
    if (change.kind !== "field") continue;
    const owner = moduleOfField.get(change.sandboxId);
    if (!owner) {
      other.push(change);
      continue;
    }
    const entry = modules.get(owner.id) ?? {
      id: owner.id,
      name: owner.name,
      fields: [],
    };
    entry.fields.push(change);
    modules.set(owner.id, entry);
  }
  for (const entry of departments.values()) {
    entry.setup.sort((left, right) => setupRank(left) - setupRank(right));
    // A department missing from the draft takes its Board's name (R2).
    if (!entry.name)
      entry.name = (
        entry.setup.find((change) => change.kind === "board") ?? entry.setup[0]
      ).label;
  }
  return {
    departments: [...departments.values()],
    modules: [...modules.values()],
    relationships: changes.filter((change) => change.kind === "relationship"),
    triggers: changes.filter((change) => change.kind === "trigger"),
    other,
  };
}

function ActionChip({ change }: { change: Change }) {
  return (
    <Badge
      variant={change.action === "close" ? "warning" : "outline"}
      className="w-20 shrink-0 justify-center"
    >
      {chipWord(change)}
    </Badge>
  );
}

function ChangeRow({ change }: { change: Change }) {
  if (!useContext(ShowActions))
    return <span className="min-w-0 wrap-anywhere">{change.label}</span>;
  return (
    <>
      <ActionChip change={change} />
      <span className="min-w-0 wrap-anywhere">{change.label}</span>
    </>
  );
}

/**
 * A titled list of review rows; more than five rows show five and a
 * "Show all" control. An optional note sits directly under the title.
 */
export function ChangeGroup<T>({
  title,
  note,
  noun,
  items,
  render,
  itemKey,
}: {
  title: string;
  note?: string;
  noun: readonly [string, string];
  items: readonly T[];
  render: (item: T) => ReactNode;
  itemKey: (item: T) => string;
}) {
  const headingId = useId();
  const [expanded, setExpanded] = useState(false);
  if (!items.length) return null;
  const shown = expanded ? items : items.slice(0, VISIBLE_ROWS);
  return (
    <section aria-labelledby={headingId} className="grid gap-2">
      <h4 id={headingId} className="text-sm font-medium">
        {title}
      </h4>
      {note ? (
        <p className="text-muted-foreground -mt-1 text-sm">{note}</p>
      ) : null}
      <ul className="grid gap-1.5 text-sm">
        {shown.map((item) => (
          <li key={itemKey(item)} className="grid gap-1.5">
            {render(item)}
          </li>
        ))}
      </ul>
      {items.length > VISIBLE_ROWS ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          // Aligned with the list text, not inset by the button padding.
          className="-ml-3 justify-self-start"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Show fewer" : `Show all ${counted(items.length, noun)}`}
        </Button>
      ) : null}
    </section>
  );
}

/**
 * One module row. Its field changes start collapsed, so "Show all" on the
 * Modules group shortens the review as much as it does in other groups.
 */
function ModuleChanges({ entry }: { entry: ModuleEntry }) {
  const showActions = useContext(ShowActions);
  const [fieldsOpen, setFieldsOpen] = useState(false);
  const fieldCount = counted(entry.fields.length, KIND_NOUNS.field);
  return (
    <>
      <div className="flex items-center gap-2">
        {entry.change ? (
          <ChangeRow change={entry.change} />
        ) : (
          <>
            {showActions ? (
              <span className="text-muted-foreground w-20 shrink-0 text-center text-xs leading-5">
                Unchanged
              </span>
            ) : null}
            <span className="min-w-0 flex-1 break-words">{entry.name}</span>
          </>
        )}
        {entry.fields.length ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-muted-foreground ml-auto h-6 shrink-0 px-2 text-xs"
            data-inline-toggle
            aria-expanded={fieldsOpen}
            aria-label={`${fieldsOpen ? "Hide" : "Show"} ${fieldCount} in ${entry.name}`}
            onClick={() => setFieldsOpen((value) => !value)}
          >
            {fieldCount}
          </Button>
        ) : null}
      </div>
      {entry.fields.length && fieldsOpen ? (
        <ul
          aria-label={`Fields in ${entry.name}`}
          className={`border-border grid gap-1.5 border-l pl-3 ${showActions ? "ml-10" : "ml-1"}`}
        >
          {entry.fields.map((field) => (
            <li key={changeKey(field)} className="flex items-start gap-2">
              <ChangeRow change={field} />
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

/** A new open department with no open module is not in the sidebar (SD15). */
function waitsForModule(entry: DepartmentEntry, design: PublishReviewDesign) {
  return (
    entry.change?.action === "create" &&
    design.departments.some((item) => item.id === entry.id && !item.closed) &&
    !design.modules.some(
      (item) => item.departmentId === entry.id && !item.closed,
    )
  );
}

/**
 * The control at the end of a new department's row (plan 11.3, FIT-3); the
 * review gives it, and the row decides where it shows.
 */
export type DepartmentRowControl = (department: {
  id: string;
  name: string;
  /** The department's position in the draft, for its mark. */
  index: number;
  setup: DepartmentSetup | undefined;
}) => ReactNode;

/**
 * One department row with its setup always open: this list is the only place
 * the owner sees what a publish creates (SD6). A nested row shows its chip
 * only when the chip's word differs from its department's.
 */
function DepartmentChanges({
  entry,
  design,
  control,
}: {
  entry: DepartmentEntry;
  design: PublishReviewDesign;
  control?: DepartmentRowControl;
}) {
  const showActions = useContext(ShowActions);
  const parentWord = entry.change ? chipWord(entry.change) : "Unchanged";
  // Setup shows only for a department this publish creates open; a closed
  // new department gets its Board only (plan 11.3).
  const draftIndex = design.departments.findIndex(
    (item) => item.id === entry.id,
  );
  const draft = design.departments[draftIndex];
  const setupControl =
    control && entry.change?.action === "create" && draft && !draft.closed
      ? control({
          id: draft.id,
          name: draft.name,
          index: draftIndex,
          setup: draft.setup,
        })
      : null;
  return (
    <>
      <div className="flex flex-wrap items-start gap-x-2">
        {entry.change ? (
          <ChangeRow change={entry.change} />
        ) : (
          <>
            {showActions ? (
              <span className="text-muted-foreground w-20 shrink-0 text-center text-xs leading-5">
                Unchanged
              </span>
            ) : null}
            <span className="min-w-0 flex-1 wrap-anywhere">{entry.name}</span>
          </>
        )}
        {setupControl ? (
          // At the end of the row; under the name on a phone.
          <span
            className={cn(
              "-my-1 shrink-0 max-sm:basis-full sm:ml-auto",
              showActions && "max-sm:pl-20",
            )}
          >
            {setupControl}
          </span>
        ) : null}
      </div>
      {waitsForModule(entry, design) ? (
        <p
          className={`text-muted-foreground -mt-1 text-xs ${showActions ? "ml-22" : ""}`}
        >
          Not in the sidebar until it has a module.
        </p>
      ) : null}
      {entry.setup.length ? (
        <ul
          aria-label={`Setup for ${entry.name}`}
          className={`border-border grid gap-1.5 border-l pl-3 ${showActions ? "ml-10" : "ml-1"}`}
        >
          {entry.setup.map((change) => (
            <li
              key={changeKey(change)}
              className="flex flex-wrap items-start gap-x-2 gap-y-0.5 sm:flex-nowrap"
            >
              {showActions ? (
                chipWord(change) === parentWord ? (
                  // Keeps the kind words in one column.
                  <span aria-hidden="true" className="w-20 shrink-0" />
                ) : (
                  <ActionChip change={change} />
                )
              ) : null}
              <span className="text-muted-foreground w-20 shrink-0 text-xs leading-5">
                {isSetupKind(change.kind) ? SETUP_KIND_WORDS[change.kind] : ""}
              </span>
              <span className="min-w-0 flex-[1_1_10rem] wrap-anywhere">
                {change.label}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

const changeKey = (change: Change) => `${change.kind}-${change.sandboxId}`;
const flatRow = (change: Change) => (
  <div className="flex items-start gap-2">
    <ChangeRow change={change} />
  </div>
);

export function PublishChangeGroups({
  changes,
  design,
  departmentControl,
}: {
  changes: readonly Change[];
  design: PublishReviewDesign;
  /** The Setup control of each new open department (FIT-3). */
  departmentControl?: DepartmentRowControl;
}) {
  const groups = groupPublicationChanges(changes, design);
  return (
    <ShowActions.Provider value={sharedAction(changes) === null}>
      <div className="grid gap-4">
        <p className="text-muted-foreground text-sm">
          {publicationChangeSummary(changes)}
        </p>
        <ChangeGroup
          title="Departments"
          noun={KIND_NOUNS.department}
          items={groups.departments}
          itemKey={(entry) => entry.id}
          render={(entry) => (
            <DepartmentChanges
              entry={entry}
              design={design}
              control={departmentControl}
            />
          )}
        />
        <ChangeGroup
          title="Modules"
          noun={KIND_NOUNS.module}
          items={groups.modules}
          itemKey={(entry) => entry.id}
          render={(entry) => <ModuleChanges entry={entry} />}
        />
        <ChangeGroup
          title="Relationships"
          noun={KIND_NOUNS.relationship}
          items={groups.relationships}
          itemKey={changeKey}
          render={flatRow}
        />
        <ChangeGroup
          title="Triggers"
          noun={KIND_NOUNS.trigger}
          items={groups.triggers}
          itemKey={changeKey}
          render={flatRow}
        />
        <ChangeGroup
          title="Other"
          noun={["change", "changes"]}
          items={groups.other}
          itemKey={changeKey}
          render={flatRow}
        />
      </div>
    </ShowActions.Provider>
  );
}
