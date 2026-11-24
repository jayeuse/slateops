"use client";

import {
  cloneElement,
  lazy,
  Suspense,
  useId,
  useMemo,
  useState,
  type ReactElement,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOptGroup,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { PopoverTitle } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { apiErrorReference } from "@/lib/api-errors";
import { ApiError } from "@/lib/api";

import {
  catalogFirstPageOptions,
  fieldsFirstPageOptions,
} from "../adapters/openview-queries";
import { worksheetKeys } from "../adapters/worksheet-queries";
import {
  editableColumn,
  saveWorksheetStructure,
  type WorksheetColumnInput,
  type WorksheetDetail,
  type WorksheetHiddenSourceColumn,
} from "../adapters/worksheets-api";
import {
  columnRefusal,
  placeColumn,
  removeGroup,
  renameGroup,
  withoutColumn,
  type GroupChoice,
} from "../domain/sheet-columns";
import type { SheetPreviewRow } from "./sheet-computed-field";
import type { FromSheetDraft } from "./sheet-from-sheet-field";

// Add column and Column settings (docs/specs/sheets.md K1, K2, K3 to K9,
// Screens 2): the Sandbox's type names, then Link to records, Lookup, From
// another sheet and Computed; the column group; the total; and Delete
// column. The whole column list is saved at the sheet's version (route 6).
// The expression editor and the sheet picker load on first use.

const SheetComputedField = lazy(() => import("./sheet-computed-field"));
const SheetFromSheetField = lazy(() => import("./sheet-from-sheet-field"));

type Kind =
  | "text"
  | "long_text"
  | "decimal"
  | "int"
  | "boolean"
  | "date"
  | "datetime"
  | "select"
  | "user"
  | "email"
  | "url"
  | "link"
  | "lookup"
  | "sheet_lookup"
  | "computed";

const KINDS: { kind: Kind; label: string }[] = [
  { kind: "text", label: "Text" },
  { kind: "long_text", label: "Long text" },
  { kind: "decimal", label: "Number" },
  { kind: "int", label: "Whole number" },
  { kind: "boolean", label: "Checkbox" },
  { kind: "date", label: "Date" },
  { kind: "datetime", label: "Date and time" },
  { kind: "select", label: "Choice list" },
  { kind: "user", label: "User" },
  { kind: "email", label: "Email" },
  { kind: "url", label: "Web link" },
  { kind: "link", label: "Link to records" },
  { kind: "lookup", label: "Lookup" },
  { kind: "sheet_lookup", label: "From another sheet" },
  { kind: "computed", label: "Computed" },
];
const NUMERIC: ReadonlySet<string> = new Set([
  "decimal",
  "int",
  "number",
  "computed",
]);
const TOTALS = [
  ["count", "Count"],
  ["sum", "Sum"],
  ["average", "Average"],
  ["min", "Min"],
  ["max", "Max"],
] as const;

type Column = WorksheetColumnInput;
type Stored = Column | WorksheetHiddenSourceColumn;

type Draft = {
  name: string;
  kind: Kind | "other";
  places: string;
  currency: boolean;
  choices: string;
  linkModule: string;
  lookupFrom: string;
  lookupField: string;
  /** The typed expression; null keeps the stored one unchanged. */
  expression: string | null;
  expressionOk: boolean;
  computedPlaces: string;
  from: FromSheetDraft;
  /** "" for none, "g<index>" for a group, "new" for a new group. */
  group: string;
  groupName: string;
  /** A group to remove on save, by its place. */
  removedGroup: number | null;
  total: string;
};

function draftOf(column: Column | null, sheet: WorksheetDetail): Draft {
  const groupIndex = column
    ? sheet.structure.groups.findIndex((item) => item.keys.includes(column.key))
    : -1;
  return {
    name: column?.name ?? "",
    kind: column
      ? KINDS.some((item) => item.kind === column.type)
        ? (column.type as Kind)
        : "other"
      : "text",
    places: column?.type === "decimal" ? String(column.decimal.places) : "2",
    currency: column?.type === "decimal" ? column.decimal.currency : false,
    choices:
      column?.type === "select"
        ? column.select.options.map((option) => option.label).join("\n")
        : "",
    linkModule: column?.type === "link" ? column.link.moduleId : "",
    lookupFrom: column?.type === "lookup" ? column.lookup.linkKey : "",
    lookupField: column?.type === "lookup" ? column.lookup.fieldId : "",
    expression: null,
    expressionOk: column?.type === "computed",
    computedPlaces:
      column?.type === "computed"
        ? column.computed.places === null ||
          column.computed.places === undefined
          ? ""
          : String(column.computed.places)
        : "2",
    from:
      column?.type === "sheet_lookup"
        ? {
            sourceSheet: column.sheet_lookup.sourceWorksheetId,
            match: `${column.sheet_lookup.linkKey}|${column.sheet_lookup.sourceLinkKey}`,
            sourceColumn: column.sheet_lookup.sourceColumnKey,
          }
        : { sourceSheet: "", match: "", sourceColumn: "" },
    group: groupIndex >= 0 ? `g${groupIndex}` : "",
    groupName: groupIndex >= 0 ? sheet.structure.groups[groupIndex].name : "",
    removedGroup: null,
    total: column ? (sheet.structure.totals[column.key] ?? "") : "",
  };
}

/** The column a draft describes, keeping a choice's id when its label stays. */
function columnOf(
  key: string,
  draft: Draft,
  previous: Column | null,
): Column | string {
  const name = draft.name.trim();
  if (!name) return "Enter a name.";
  if (draft.kind === "other") return previous ?? "Choose a type.";
  if (draft.kind === "decimal")
    return {
      key,
      name,
      type: "decimal",
      decimal: {
        places: Math.min(18, Math.max(0, Number(draft.places) || 0)),
        currency: draft.currency,
      },
    };
  if (draft.kind === "select") {
    const labels = draft.choices
      .split("\n")
      .map((label) => label.trim())
      .filter(Boolean);
    if (labels.length === 0) return "Enter at least one choice.";
    const kept = previous?.type === "select" ? previous.select.options : [];
    let next = kept.reduce(
      (high, option) => Math.max(high, Number(option.id.slice(1)) || 0),
      0,
    );
    return {
      key,
      name,
      type: "select",
      select: {
        options: labels.map((label) => {
          const same = kept.find((option) => option.label === label);
          if (same) return same;
          next += 1;
          return { id: `o${next}`, label };
        }),
      },
    };
  }
  if (draft.kind === "link") {
    if (!draft.linkModule) return "Choose what it links to.";
    return { key, name, type: "link", link: { moduleId: draft.linkModule } };
  }
  if (draft.kind === "lookup") {
    if (!draft.lookupFrom || !draft.lookupField)
      return "Choose a link column and a field.";
    return {
      key,
      name,
      type: "lookup",
      lookup: { linkKey: draft.lookupFrom, fieldId: draft.lookupField },
    };
  }
  if (draft.kind === "computed") {
    // An untouched expression goes back exactly as stored, so the server
    // reads it in its stored form (D7.1).
    const expression =
      draft.expression ??
      (previous?.type === "computed" ? previous.computed.expression : "");
    if (!expression.trim()) return "Enter an expression.";
    const places =
      draft.computedPlaces.trim() === ""
        ? null
        : Math.min(18, Math.max(0, Number(draft.computedPlaces) || 0));
    return { key, name, type: "computed", computed: { expression, places } };
  }
  if (draft.kind === "sheet_lookup") {
    const [linkKey, sourceLinkKey] = draft.from.match.split("|");
    if (!draft.from.sourceSheet || !linkKey || !sourceLinkKey)
      return "Choose a sheet and how its rows match.";
    if (!draft.from.sourceColumn) return "Choose the column to show.";
    return {
      key,
      name,
      type: "sheet_lookup",
      sheet_lookup: {
        sourceWorksheetId: draft.from.sourceSheet,
        sourceColumnKey: draft.from.sourceColumn,
        linkKey,
        sourceLinkKey,
      },
    };
  }
  return { key, name, type: draft.kind };
}

function sameName(a: string, b: string) {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

export default function ColumnForm({
  sheet,
  column,
  locale,
  preview,
  onDone,
  onDeleted,
}: {
  sheet: WorksheetDetail;
  column: Stored | null;
  locale: string;
  preview: SheetPreviewRow | null;
  onDone: () => void;
  /** After a column is deleted, before the popover closes. */
  onDeleted: (key: string) => void;
}) {
  const client = useQueryClient();
  const hidden = column && "state" in column ? column : null;
  const editable = column && !("state" in column) ? column : null;
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const names = Object.fromEntries(
    sheet.structure.columns.map((item) => [item.key, item.name]),
  );

  const save = async (
    structure: Parameters<typeof saveWorksheetStructure>[2],
  ): Promise<boolean> => {
    setFailure(null);
    setSaving(true);
    try {
      const saved = await saveWorksheetStructure(
        sheet.id,
        sheet.etag,
        structure,
      );
      client.setQueryData(worksheetKeys.detail(sheet.id), saved);
      return true;
    } catch (error) {
      setFailure(error);
      return false;
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!column || saving) return;
    const kept = sheet.structure.columns.map(editableColumn);
    const next = withoutColumn(
      {
        columns: kept,
        groups: sheet.structure.groups,
        totals: sheet.structure.totals,
      },
      column.key,
    );
    if (
      await save({
        columns: next.columns.map(editableColumn),
        groups: next.groups,
        totals: next.totals,
      })
    ) {
      onDeleted(column.key);
      onDone();
    }
  };

  if (confirming && column)
    return (
      <div className="flex flex-col gap-3">
        <PopoverTitle className="text-sm font-semibold">
          Delete {column.name}?
        </PopoverTitle>
        <p className="text-sm">
          It disappears for everyone who can see this sheet. You cannot undo
          this.
        </p>
        {failure ? (
          <Alert variant="destructive" reference={apiErrorReference(failure)}>
            <p>
              {columnRefusal(failure, {
                editedKey: column.key,
                names,
                removedName: column.name,
              })}
            </p>
          </Alert>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            autoFocus
            className="min-h-11 xl:h-8 xl:min-h-8"
            onClick={() => {
              setFailure(null);
              setConfirming(false);
            }}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            className="min-h-11 xl:h-8 xl:min-h-8"
            pending={saving}
            pendingLabel="Deleting…"
            onClick={() => void remove()}
          >
            Delete column
          </Button>
        </div>
      </div>
    );

  if (hidden)
    return (
      <div className="flex flex-col gap-3">
        <PopoverTitle className="text-sm font-semibold">
          Column settings
        </PopoverTitle>
        <p className="text-sm font-medium">{hidden.name}</p>
        <p className="text-muted-foreground text-sm">
          From another sheet that you cannot see. Its settings stay as the owner
          of this sheet set them.
        </p>
        <div className="flex justify-between gap-2">
          <Button
            type="button"
            variant="ghost"
            className="text-danger-text min-h-11 xl:h-8 xl:min-h-8"
            onClick={() => setConfirming(true)}
          >
            Delete column
          </Button>
          <Button
            type="button"
            variant="ghost"
            className="min-h-11 xl:h-8 xl:min-h-8"
            onClick={onDone}
          >
            Close
          </Button>
        </div>
      </div>
    );

  return (
    <ColumnSettings
      sheet={sheet}
      column={editable}
      locale={locale}
      preview={preview}
      saving={saving}
      failure={failure}
      names={names}
      onSave={save}
      onDelete={() => {
        setFailure(null);
        setConfirming(true);
      }}
      onDone={onDone}
    />
  );
}

function ColumnSettings({
  sheet,
  column,
  locale,
  preview,
  saving,
  failure,
  names,
  onSave,
  onDelete,
  onDone,
}: {
  sheet: WorksheetDetail;
  column: Column | null;
  locale: string;
  preview: SheetPreviewRow | null;
  saving: boolean;
  failure: unknown;
  names: Record<string, string>;
  onSave: (
    structure: Parameters<typeof saveWorksheetStructure>[2],
  ) => Promise<boolean>;
  onDelete: () => void;
  onDone: () => void;
}) {
  const id = useId();
  // The draft is this form's own: a refetched sheet does not reset it.
  const [draft, setDraft] = useState(() => draftOf(column, sheet));
  const [problem, setProblem] = useState<string | null>(null);
  const modules = useQuery(catalogFirstPageOptions());
  const key = column?.key ?? `c${sheet.structure.nextColumnSeq}`;
  const linkColumns = sheet.structure.columns.filter(
    (item) => item.type === "link" && item.key !== column?.key,
  );
  const fromColumn = linkColumns.find((item) => item.key === draft.lookupFrom);
  const fromModule =
    fromColumn?.type === "link" ? fromColumn.link.moduleId : "";
  const fields = useQuery({
    ...fieldsFirstPageOptions(fromModule),
    enabled: draft.kind === "lookup" && Boolean(fromModule),
  });
  const numeric = NUMERIC.has(draft.kind);
  const groups = sheet.structure.groups;
  const update = (patch: Partial<Draft>) =>
    setDraft((current) => ({ ...current, ...patch }));
  const moduleChoices = useMemo(
    () => modules.data?.items ?? [],
    [modules.data],
  );
  // A refusal about this column's expression shows under the expression.
  const details =
    failure instanceof ApiError && typeof failure.details === "object"
      ? (failure.details as { code?: unknown; key?: unknown; reason?: unknown })
      : null;
  const expressionRefusal =
    draft.kind === "computed" &&
    details?.code === "expression_invalid" &&
    details.key === key
      ? {
          words: columnRefusal(failure, { editedKey: key, names }),
          reason: String(details.reason ?? ""),
        }
      : null;

  const groupChoice = (): GroupChoice | string => {
    if (draft.group === "new") {
      const name = draft.groupName.trim();
      if (!name) return "Enter a name for the new group.";
      if (groups.some((group) => sameName(group.name, name)))
        return "Another group has this name.";
      return { newGroup: name };
    }
    if (draft.group.startsWith("g"))
      return { group: Number(draft.group.slice(1)) };
    return { group: null };
  };

  const submit = async () => {
    if (saving) return;
    const built = columnOf(key, draft, column);
    if (typeof built === "string") {
      setProblem(built);
      return;
    }
    // Add column says why it waits (DisabledReason); a submit by Enter
    // stops here too.
    if (
      draft.kind === "computed" &&
      !draft.expressionOk &&
      draft.expression !== null
    )
      return;
    const choice = groupChoice();
    if (typeof choice === "string") {
      setProblem(choice);
      return;
    }
    let nextGroups = groups;
    if (draft.removedGroup !== null)
      nextGroups = removeGroup(nextGroups, draft.removedGroup);
    else if ("group" in choice && choice.group !== null) {
      const current = groups[choice.group];
      const name = draft.groupName.trim();
      if (!name) {
        setProblem("Enter the group's name.");
        return;
      }
      if (
        current &&
        name !== current.name &&
        groups.some(
          (group, index) =>
            index !== choice.group && sameName(group.name, name),
        )
      ) {
        setProblem("Another group has this name.");
        return;
      }
      if (current && name !== current.name)
        nextGroups = renameGroup(nextGroups, choice.group, name);
    }
    setProblem(null);
    const stored = sheet.structure.columns.map(editableColumn);
    const columns = column
      ? stored.map((item) => (item.key === key ? built : item))
      : stored;
    const totals = { ...sheet.structure.totals };
    delete totals[key];
    if (draft.total && (draft.total === "count" || numeric))
      totals[key] =
        draft.total as WorksheetDetail["structure"]["totals"][string];
    const placed = placeColumn(
      // A removed group's columns stay, without a group.
      { columns, groups: nextGroups, totals },
      column ? key : built,
      draft.removedGroup !== null ? { group: null } : choice,
    );
    if (
      await onSave({
        columns: placed.columns.map(editableColumn),
        groups: placed.groups,
        totals: placed.totals,
      })
    )
      onDone();
  };

  const field = (label: string, control: ReactElement, hint?: string) => {
    const hintId = `${id}-hint-${label.replace(/\W+/g, "-")}`;
    return (
      <div className="flex flex-col gap-1">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium">{label}</span>
          {hint
            ? cloneElement(
                control as ReactElement<{ "aria-describedby"?: string }>,
                { "aria-describedby": hintId },
              )
            : control}
        </label>
        {hint ? (
          <span id={hintId} className="text-muted-foreground text-xs">
            {hint}
          </span>
        ) : null}
      </div>
    );
  };
  const select = "w-full [&_select]:h-11 xl:[&_select]:h-8";
  const loading = (
    <p className="text-muted-foreground text-xs" role="status">
      Loading…
    </p>
  );
  const computedSaveBlocked =
    draft.kind === "computed" &&
    draft.expression !== null &&
    !draft.expressionOk;
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <PopoverTitle className="text-sm font-semibold">
        {column ? "Column settings" : "Add column"}
      </PopoverTitle>
      {field(
        "Name",
        <Input
          id={`${id}-name`}
          maxLength={150}
          className="min-h-11 xl:h-8 xl:min-h-8"
          value={draft.name}
          onChange={(event) => update({ name: event.target.value })}
        />,
      )}
      {field(
        "Type",
        <NativeSelect
          className={select}
          value={draft.kind}
          disabled={draft.kind === "other"}
          onChange={(event) =>
            update({
              kind: event.target.value as Kind,
              // A new expression starts empty and must be checked.
              expressionOk:
                event.target.value === "computed" &&
                column?.type === "computed",
              expression: null,
            })
          }
        >
          {draft.kind === "other" ? (
            <NativeSelectOption value="other">
              {column?.type}
            </NativeSelectOption>
          ) : null}
          <NativeSelectOptGroup label="Values">
            {KINDS.slice(0, 11).map((item) => (
              <NativeSelectOption key={item.kind} value={item.kind}>
                {item.label}
              </NativeSelectOption>
            ))}
          </NativeSelectOptGroup>
          <NativeSelectOptGroup label="From other data">
            {KINDS.slice(11).map((item) => (
              <NativeSelectOption key={item.kind} value={item.kind}>
                {item.label}
              </NativeSelectOption>
            ))}
          </NativeSelectOptGroup>
        </NativeSelect>,
      )}
      {draft.kind === "decimal" ? (
        <>
          {field(
            "Decimal places",
            <Input
              type="number"
              min={0}
              max={18}
              className="min-h-11 xl:h-8 xl:min-h-8"
              value={draft.places}
              onChange={(event) => update({ places: event.target.value })}
            />,
          )}
          <label className="flex min-h-11 items-center gap-2 text-sm xl:min-h-8">
            <input
              type="checkbox"
              className="size-4"
              checked={draft.currency}
              onChange={(event) => update({ currency: event.target.checked })}
            />
            Show the organization&apos;s currency
          </label>
        </>
      ) : null}
      {draft.kind === "select"
        ? field(
            "Choices",
            <Textarea
              rows={4}
              value={draft.choices}
              onChange={(event) => update({ choices: event.target.value })}
            />,
            "One choice per line.",
          )
        : null}
      {draft.kind === "link"
        ? field(
            "Links to",
            <NativeSelect
              className={select}
              value={draft.linkModule}
              onChange={(event) => update({ linkModule: event.target.value })}
            >
              <NativeSelectOption value="">Choose a module</NativeSelectOption>
              {moduleChoices.map((module) => (
                <NativeSelectOption key={module.id} value={module.id}>
                  {module.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>,
            "Each cell links to one record that you can read.",
          )
        : null}
      {draft.kind === "lookup" ? (
        <>
          {field(
            "From",
            <NativeSelect
              className={select}
              value={draft.lookupFrom}
              onChange={(event) =>
                update({ lookupFrom: event.target.value, lookupField: "" })
              }
            >
              <NativeSelectOption value="">
                Choose a link column
              </NativeSelectOption>
              {linkColumns.map((item) => (
                <NativeSelectOption key={item.key} value={item.key}>
                  {item.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>,
          )}
          {field(
            "Shows",
            <NativeSelect
              className={select}
              value={draft.lookupField}
              disabled={!fromModule}
              onChange={(event) => update({ lookupField: event.target.value })}
            >
              <NativeSelectOption value="">Choose a field</NativeSelectOption>
              {(fields.data?.items ?? []).map((item) => (
                <NativeSelectOption key={item.id} value={item.id}>
                  {item.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>,
            "Read-only. It shows the record's current value.",
          )}
        </>
      ) : null}
      {draft.kind === "sheet_lookup" ? (
        <Suspense fallback={loading}>
          <SheetFromSheetField
            sheet={sheet}
            value={draft.from}
            onChange={(patch) =>
              setDraft((current) => ({
                ...current,
                from: { ...current.from, ...patch },
              }))
            }
            field={field}
            selectClass={select}
          />
        </Suspense>
      ) : null}
      {draft.kind === "computed" ? (
        <>
          <Suspense fallback={loading}>
            <SheetComputedField
              sheet={sheet}
              self={key}
              stored={
                column?.type === "computed" ? column.computed.expression : null
              }
              value={draft.expression}
              onChange={(text, ok) =>
                update({ expression: text, expressionOk: ok })
              }
              places={
                draft.computedPlaces.trim() === ""
                  ? null
                  : Number(draft.computedPlaces)
              }
              locale={locale}
              preview={preview}
              refusal={expressionRefusal}
            />
          </Suspense>
          {field(
            "Decimal places",
            <Input
              type="number"
              min={0}
              max={18}
              className="min-h-11 xl:h-8 xl:min-h-8"
              value={draft.computedPlaces}
              onChange={(event) =>
                update({ computedPlaces: event.target.value })
              }
            />,
          )}
        </>
      ) : null}
      {field(
        "Column group",
        <NativeSelect
          className={select}
          value={draft.group}
          onChange={(event) => {
            const value = event.target.value;
            const index = value.startsWith("g") ? Number(value.slice(1)) : -1;
            update({
              group: value,
              groupName: index >= 0 ? (groups[index]?.name ?? "") : "",
              removedGroup: null,
            });
          }}
        >
          <NativeSelectOption value="">No group</NativeSelectOption>
          {groups.map((group, index) => (
            <NativeSelectOption
              key={`${group.name}-${index}`}
              value={`g${index}`}
            >
              {group.name}
            </NativeSelectOption>
          ))}
          <NativeSelectOption value="new">New group…</NativeSelectOption>
        </NativeSelect>,
        draft.removedGroup !== null
          ? `${groups[draft.removedGroup]?.name ?? "The group"} is removed when you save. Its columns stay, without a group.`
          : undefined,
      )}
      {draft.group ? (
        <div className="flex items-end gap-2">
          <div className="min-w-0 flex-1">
            {field(
              draft.group === "new" ? "New group's name" : "Group name",
              <Input
                maxLength={150}
                className="min-h-11 xl:h-8 xl:min-h-8"
                value={draft.groupName}
                onChange={(event) => update({ groupName: event.target.value })}
              />,
              draft.group === "new"
                ? undefined
                : "Renames the group for all its columns.",
            )}
          </div>
          {draft.group.startsWith("g") ? (
            <Button
              type="button"
              variant="ghost"
              className="min-h-11 xl:h-8 xl:min-h-8"
              onClick={() =>
                update({
                  removedGroup: Number(draft.group.slice(1)),
                  group: "",
                  groupName: "",
                })
              }
            >
              Remove group
            </Button>
          ) : null}
        </div>
      ) : null}
      {field(
        "Total",
        <NativeSelect
          className={select}
          value={draft.total}
          onChange={(event) => update({ total: event.target.value })}
        >
          <NativeSelectOption value="">None</NativeSelectOption>
          {TOTALS.filter(([fn]) => fn === "count" || numeric).map(
            ([fn, label]) => (
              <NativeSelectOption key={fn} value={fn}>
                {label}
              </NativeSelectOption>
            ),
          )}
        </NativeSelect>,
      )}
      {problem ? (
        <p role="alert" className="text-destructive text-sm">
          {problem}
        </p>
      ) : null}
      {failure && !expressionRefusal ? (
        <Alert variant="destructive" reference={apiErrorReference(failure)}>
          <p>{columnRefusal(failure, { editedKey: key, names })}</p>
        </Alert>
      ) : null}
      <div className="flex items-center gap-2">
        {column ? (
          <Button
            type="button"
            variant="ghost"
            className="text-danger-text mr-auto min-h-11 xl:h-8 xl:min-h-8"
            onClick={onDelete}
          >
            Delete column
          </Button>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          className="ml-auto min-h-11 xl:h-8 xl:min-h-8"
          onClick={onDone}
        >
          Cancel
        </Button>
        <DisabledReason
          stable
          reason={computedSaveBlocked ? "Fix the expression first." : null}
        >
          <Button
            type="submit"
            className="min-h-11 xl:h-8 xl:min-h-8"
            pending={saving}
            pendingLabel="Saving…"
          >
            {column ? "Save column" : "Add column"}
          </Button>
        </DisabledReason>
      </div>
    </form>
  );
}
