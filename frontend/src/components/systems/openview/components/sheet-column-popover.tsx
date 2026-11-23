"use client";

import {
  useId,
  useMemo,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { apiErrorReference } from "@/lib/api-errors";

import {
  catalogFirstPageOptions,
  fieldsFirstPageOptions,
} from "../adapters/openview-queries";
import { worksheetKeys } from "../adapters/worksheet-queries";
import {
  saveWorksheetStructure,
  type WorksheetColumnInput,
  type WorksheetDetail,
} from "../adapters/worksheets-api";

// Add column and Column settings (docs/specs/sheets.md K1, K2, Screens 2):
// the Sandbox's type names, then Link to records and Lookup. Computed and
// From another sheet columns arrive with their own unit. The whole column
// list is saved at the sheet's version (route 6).

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
  | "lookup";

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
];
const NUMERIC: ReadonlySet<string> = new Set(["decimal", "int", "number"]);
const TOTALS = [
  ["count", "Count"],
  ["sum", "Sum"],
  ["average", "Average"],
  ["min", "Min"],
  ["max", "Max"],
] as const;

type Column = WorksheetColumnInput;

function refusal(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 412)
      return "Someone changed this sheet's columns. Close this and try again.";
    if (error.status === 409 || error.status === 422) return error.message;
  }
  return "The column could not be saved. Try again.";
}

type Draft = {
  name: string;
  kind: Kind | "other";
  places: string;
  currency: boolean;
  choices: string;
  linkModule: string;
  lookupFrom: string;
  lookupField: string;
  group: string;
  total: string;
};

function draftOf(column: Column | null, sheet: WorksheetDetail): Draft {
  const group =
    column &&
    sheet.structure.groups.find((item) => item.keys.includes(column.key));
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
    group: group?.name ?? "",
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
  return { key, name, type: draft.kind };
}

export function SheetColumnPopover({
  sheet,
  column,
  trigger,
  children,
}: {
  sheet: WorksheetDetail;
  /** The column to change; none adds a column. */
  column: Column | null;
  trigger: ReactElement;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={trigger}>{children}</PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        {open ? (
          <ColumnForm
            sheet={sheet}
            column={column}
            onDone={() => setOpen(false)}
          />
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

function ColumnForm({
  sheet,
  column,
  onDone,
}: {
  sheet: WorksheetDetail;
  column: Column | null;
  onDone: () => void;
}) {
  const id = useId();
  const client = useQueryClient();
  // The draft is this form's own: a refetched sheet does not reset it.
  const [draft, setDraft] = useState(() => draftOf(column, sheet));
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const modules = useQuery(catalogFirstPageOptions());
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

  const save = async () => {
    if (saving) return;
    const key = column?.key ?? `c${sheet.structure.nextColumnSeq}`;
    const built = columnOf(key, draft, column);
    if (typeof built === "string") {
      setProblem(built);
      return;
    }
    setProblem(null);
    setFailure(null);
    const stored = sheet.structure.columns as Column[];
    const columns = column
      ? stored.map((item) => (item.key === key ? built : item))
      : [...stored, built];
    const groupsOut = groups
      .map((group) => ({
        ...group,
        keys: group.keys.filter((item) => item !== key),
      }))
      .map((group) =>
        group.name === draft.group
          ? { ...group, keys: [...group.keys, key] }
          : group,
      )
      .filter((group) => group.keys.length > 0);
    const totals = { ...sheet.structure.totals };
    delete totals[key];
    if (draft.total && (draft.total === "count" || numeric))
      totals[key] =
        draft.total as WorksheetDetail["structure"]["totals"][string];
    setSaving(true);
    try {
      const saved = await saveWorksheetStructure(sheet.id, sheet.etag, {
        columns,
        groups: groupsOut,
        totals,
      });
      client.setQueryData(worksheetKeys.detail(sheet.id), saved);
      onDone();
    } catch (error) {
      setFailure(error);
    } finally {
      setSaving(false);
    }
  };

  const field = (label: string, control: ReactElement, hint?: string) => (
    <div className="flex flex-col gap-1">
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium">{label}</span>
        {control}
      </label>
      {hint ? (
        <span className="text-muted-foreground text-xs">{hint}</span>
      ) : null}
    </div>
  );
  const select =
    "border-input bg-background h-11 rounded-md border px-2 text-sm xl:h-8";
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
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
        <select
          className={select}
          value={draft.kind}
          disabled={draft.kind === "other"}
          onChange={(event) => update({ kind: event.target.value as Kind })}
        >
          {draft.kind === "other" ? (
            <option value="other">{column?.type}</option>
          ) : null}
          <optgroup label="Values">
            {KINDS.slice(0, 11).map((item) => (
              <option key={item.kind} value={item.kind}>
                {item.label}
              </option>
            ))}
          </optgroup>
          <optgroup label="From other data">
            {KINDS.slice(11).map((item) => (
              <option key={item.kind} value={item.kind}>
                {item.label}
              </option>
            ))}
          </optgroup>
        </select>,
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
            <select
              className={select}
              value={draft.linkModule}
              onChange={(event) => update({ linkModule: event.target.value })}
            >
              <option value="">Choose a module</option>
              {moduleChoices.map((module) => (
                <option key={module.id} value={module.id}>
                  {module.name}
                </option>
              ))}
            </select>,
            "Each cell links to one record that you can read.",
          )
        : null}
      {draft.kind === "lookup" ? (
        <>
          {field(
            "From",
            <select
              className={select}
              value={draft.lookupFrom}
              onChange={(event) =>
                update({ lookupFrom: event.target.value, lookupField: "" })
              }
            >
              <option value="">Choose a link column</option>
              {linkColumns.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.name}
                </option>
              ))}
            </select>,
          )}
          {field(
            "Shows",
            <select
              className={select}
              value={draft.lookupField}
              disabled={!fromModule}
              onChange={(event) => update({ lookupField: event.target.value })}
            >
              <option value="">Choose a field</option>
              {(fields.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>,
            "Read-only. It shows the record's current value.",
          )}
        </>
      ) : null}
      {groups.length > 0
        ? field(
            "Column group",
            <select
              className={select}
              value={draft.group}
              onChange={(event) => update({ group: event.target.value })}
            >
              <option value="">None</option>
              {groups.map((group) => (
                <option key={group.name} value={group.name}>
                  {group.name}
                </option>
              ))}
            </select>,
          )
        : null}
      {field(
        "Total",
        <select
          className={select}
          value={draft.total}
          onChange={(event) => update({ total: event.target.value })}
        >
          <option value="">None</option>
          {TOTALS.filter(([fn]) => fn === "count" || numeric).map(
            ([fn, label]) => (
              <option key={fn} value={fn}>
                {label}
              </option>
            ),
          )}
        </select>,
      )}
      {problem ? (
        <p role="alert" className="text-destructive text-sm">
          {problem}
        </p>
      ) : null}
      {failure ? (
        <Alert variant="destructive" reference={apiErrorReference(failure)}>
          <p>{refusal(failure)}</p>
        </Alert>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          className="min-h-11 xl:h-8 xl:min-h-8"
          onClick={onDone}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          className="min-h-11 xl:h-8 xl:min-h-8"
          pending={saving}
          pendingLabel="Saving…"
        >
          {column ? "Save column" : "Add column"}
        </Button>
      </div>
    </form>
  );
}
