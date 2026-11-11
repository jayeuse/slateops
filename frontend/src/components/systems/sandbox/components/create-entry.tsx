"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
} from "react";

import { FileStack } from "lucide-react";

import { DepartmentMark } from "@/components/sandbox/department-mark";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { DisabledReason } from "@/components/ui/disabled-reason";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import {
  addElement,
  createEntryKey,
  createRefusalPlace,
  createLimitReason,
  emptyCreateDraft,
  typePickFocus,
  type CreateDraft,
  type CreateKind,
} from "../domain/create-checks";
import {
  FIELD_TYPES,
  fieldTypeLabel,
  uid,
  type Design,
  type FieldTypeName,
} from "../domain/model";
import {
  SandboxCommandError,
  type SandboxCommandResult,
} from "../state/commands";
import { useDepartmentSetupDefault } from "../state/use-department-setup-default";

/**
 * The add-next entry (docs/specs/sandbox-ux-redesign.md, "The entry", FAST-1,
 * FAST-2, FAST-6). One popover for departments, modules, and fields, anchored
 * to the control that opened it; a bottom sheet below 768px. Enter adds and
 * keeps the entry open for the next name; Enter on a blank name, Escape, or
 * Done ends the flow. The entry checks each add before it changes the draft
 * (N2) and never waits for the server: the page accepts an add at once and
 * queues its save.
 */

export type CreateEntryParent = {
  id: string;
  name: string;
  /** The department whose mark the title shows. */
  departmentId: string;
};

export type CreateEntryProps = {
  kind: CreateKind;
  /** The department of a module, the module of a field; null for a department. */
  parent: CreateEntryParent | null;
  /** The current draft design, for the checks, the limits, and the parent's mark. */
  design: Design;
  open: boolean;
  /** The control that opened the entry: it anchors the popover and gets focus back. */
  anchor: HTMLElement | null;
  /** The flow ended. The caller selects `lastCreatedId` and closes the entry. */
  onRequestClose: (lastCreatedId: string | null) => void;
  /** The page's `change`; an accepted add resolves at once. */
  onAdd: (
    update: (design: Design) => Design,
  ) => SandboxCommandResult<Design> | Promise<SandboxCommandResult<Design>>;
  /** From `designAddHoldReason`: a publish, lifecycle action, or conflict holds the draft. */
  holdReason: string | null;
  /**
   * The department entry's "From a template" (FAST-7): the flow ends, with
   * the last element it created, and the caller opens "Add from a template".
   */
  onFromTemplate?: (lastCreatedId: string | null) => void;
};

const WIDE_QUERY = "(min-width: 48rem)";

function subscribeWide(onChange: () => void) {
  const query = window.matchMedia(WIDE_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** True at the md breakpoint and wider; the first render assumes wide. */
function useWideScreen(): boolean {
  return useSyncExternalStore(
    subscribeWide,
    () => window.matchMedia(WIDE_QUERY).matches,
    () => true,
  );
}

const KIND_WORD: Record<CreateKind, string> = {
  department: "department",
  module: "module",
  field: "field",
};

export function CreateEntry({
  kind,
  parent,
  design,
  open,
  anchor,
  onRequestClose,
  onAdd,
  holdReason,
  onFromTemplate,
}: CreateEntryProps) {
  const wide = useWideScreen();
  const entryId = useId();
  const focusName = () => document.getElementById(`${entryId}-name`);
  // One close per flow, with the last element this flow created.
  const lastCreated = useRef<string | null>(null);
  const closed = useRef(false);
  useEffect(() => {
    if (!open) return;
    lastCreated.current = null;
    closed.current = false;
  }, [open]);
  const close = () => {
    if (closed.current) return;
    closed.current = true;
    onRequestClose(lastCreated.current);
  };
  const onOpenChange = (next: boolean) => {
    if (!next) close();
  };
  const finalFocus = () => anchor ?? true;
  // The portal mounts the body with the popup and unmounts it after the
  // exit, so each flow starts from an empty entry and never closes empty.
  const body = (
    <CreateEntryBody
      kind={kind}
      parent={parent}
      design={design}
      holdReason={holdReason}
      onAdd={onAdd}
      onCreated={(id) => {
        lastCreated.current = id;
      }}
      onClose={close}
      onFromTemplate={
        kind === "department" && onFromTemplate
          ? () => {
              if (closed.current) return;
              closed.current = true;
              onFromTemplate(lastCreated.current);
            }
          : undefined
      }
      sheet={!wide}
      entryId={entryId}
    />
  );
  return wide ? (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverContent
        anchor={anchor}
        side="bottom"
        align="start"
        collisionPadding={16}
        initialFocus={focusName}
        finalFocus={finalFocus}
        aria-labelledby={`${entryId}-title`}
        className={cn(
          "slim-ui max-w-[calc(100vw-2rem)] gap-0 p-0",
          // The department entry's footer also holds "From a template".
          kind === "module" ? "w-85" : "w-96",
        )}
      >
        {body}
      </PopoverContent>
    </Popover>
  ) : (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        initialFocus={focusName}
        finalFocus={finalFocus}
        aria-labelledby={`${entryId}-title`}
        className="slim-ui -mx-4 -mb-4 w-[calc(100%+2rem)] max-w-none self-end rounded-b-none p-0"
      >
        {body}
      </DialogContent>
    </Dialog>
  );
}

/** The entry's state for one open flow; it mounts with the popup. */
function CreateEntryBody({
  kind,
  parent,
  design,
  holdReason,
  onAdd,
  onCreated,
  onClose,
  onFromTemplate,
  sheet,
  entryId,
}: {
  kind: CreateKind;
  parent: CreateEntryParent | null;
  design: Design;
  holdReason: string | null;
  onAdd: CreateEntryProps["onAdd"];
  onCreated: (id: string) => void;
  onClose: () => void;
  onFromTemplate: (() => void) | undefined;
  sheet: boolean;
  entryId: string;
}) {
  const [draft, setDraft] = useState<CreateDraft>(emptyCreateDraft);
  // A new department starts from the saved Manage default (FIT-4, SD-C20).
  const setupDefault = useDepartmentSetupDefault();
  const [refusal, setRefusal] = useState<{
    reason: string;
    on: "name" | "choices";
  } | null>(null);
  // A refusal shows where its problem is (B5d), and focus goes there.
  const refuse = (submitted: CreateDraft, reason: string) => {
    const on = createRefusalPlace(submitted, reason);
    setRefusal({ reason, on });
    focus(on);
  };
  const focus = (target: "name" | "choices") =>
    document.getElementById(`${entryId}-${target}`)?.focus();
  const adding = useRef(false);
  // Focus asked for by a type click; the Choices input mounts first.
  const pendingFocus = useRef<"name" | "choices" | null>(null);
  useEffect(() => {
    const target = pendingFocus.current;
    if (!target) return;
    pendingFocus.current = null;
    focus(target);
  });
  const blockedReason = holdReason ?? createLimitReason(design, kind);
  const departmentIndex = parent
    ? design.departments.findIndex((item) => item.id === parent.departmentId)
    : -1;

  async function add() {
    if (blockedReason || adding.current) return;
    const id = uid();
    const parentId = parent?.id ?? null;
    const submitted = draft;
    // Checked before the draft changes, so the update itself never refuses
    // under a hold (N2).
    const check = addElement(
      design,
      kind,
      id,
      parentId,
      submitted,
      setupDefault,
    );
    if (!check.ok) {
      refuse(submitted, check.reason);
      return;
    }
    adding.current = true;
    let result: SandboxCommandResult<Design>;
    try {
      result = await onAdd((current) => {
        // Placed from the latest design, so fast adds take separate slots.
        const next = addElement(
          current,
          kind,
          id,
          parentId,
          submitted,
          setupDefault,
        );
        if (!next.ok) throw new SandboxCommandError(next.reason);
        return next.design;
      });
    } finally {
      adding.current = false;
    }
    if (!result.ok) {
      refuse(submitted, result.error);
      return;
    }
    // The parent stays the parent; nothing is reselected until the end.
    onCreated(id);
    setDraft(emptyCreateDraft);
    setRefusal(null);
    focus("name");
  }

  return (
    <CreateEntryForm
      kind={kind}
      parentName={parent?.name ?? null}
      departmentIndex={departmentIndex >= 0 ? departmentIndex : null}
      draft={draft}
      refusal={refusal?.reason ?? null}
      refusalOn={refusal?.on ?? "name"}
      blockedReason={blockedReason}
      sheet={sheet}
      entryId={entryId}
      onDraftChange={(patch) => {
        setDraft((current) => ({ ...current, ...patch }));
        setRefusal(null);
      }}
      onTypePick={(type, by) => {
        setDraft((current) => ({ ...current, type }));
        setRefusal(null);
        if (by === "pointer") pendingFocus.current = typePickFocus(type);
      }}
      onEnter={() => {
        if (createEntryKey(draft, "Enter") === "close") onClose();
        else void add();
      }}
      onAdd={() => void add()}
      onDone={onClose}
      onFromTemplate={onFromTemplate}
    />
  );
}

export type CreateEntryFormProps = {
  kind: CreateKind;
  parentName: string | null;
  /** The parent's department position, for its mark; null for a department. */
  departmentIndex: number | null;
  draft: CreateDraft;
  /** Why the last add was refused. */
  refusal: string | null;
  /** Where the refusal shows: under the name (default) or under Choices. */
  refusalOn?: "name" | "choices";
  /** Why no add can happen now: a hold or a document limit. */
  blockedReason: string | null;
  /** The bottom sheet below 768px. */
  sheet: boolean;
  /** Prefix of the title (`-title`), name (`-name`), and Choices (`-choices`) ids. */
  entryId: string;
  onDraftChange: (patch: Partial<CreateDraft>) => void;
  onTypePick: (type: FieldTypeName, by: "pointer" | "keyboard") => void;
  /** Enter in the name, the type group, Choices, or Required. */
  onEnter: () => void;
  onAdd: () => void;
  onDone: () => void;
  /** The department entry's "From a template"; absent for other kinds. */
  onFromTemplate?: () => void;
};

/** The entry's controls, without the popover: controlled by `CreateEntry`. */
export function CreateEntryForm({
  kind,
  parentName,
  departmentIndex,
  draft,
  refusal,
  refusalOn = "name",
  blockedReason,
  sheet,
  entryId,
  onDraftChange,
  onTypePick,
  onEnter,
  onAdd,
  onDone,
  onFromTemplate,
}: CreateEntryFormProps) {
  const id = useId();
  const refusalId = `${id}-refusal`;
  // A choice problem shows under Choices while Choices shows (B5d).
  const choicesRefusal =
    refusal !== null &&
    refusalOn === "choices" &&
    kind === "field" &&
    draft.type === "Select";
  const nameRefusal = refusal !== null && !choicesRefusal;
  const blockedId = `${id}-blocked`;
  const choicesId = `${entryId}-choices`;
  const requiredId = `${id}-required`;
  const word = KIND_WORD[kind];
  const title =
    kind === "department" ? "Add department" : `Add ${word} to ${parentName}`;
  const control = "h-11 xl:h-8";
  return (
    <form
      noValidate
      className="flex flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        onAdd();
      }}
      onKeyDown={(event: KeyboardEvent<HTMLFormElement>) => {
        // Footer buttons keep their own Enter; every other control adds.
        if (event.key !== "Enter" || event.nativeEvent.isComposing) return;
        if ((event.target as HTMLElement).closest("[data-entry-footer]"))
          return;
        event.preventDefault();
        onEnter();
      }}
    >
      {sheet ? (
        <div
          aria-hidden="true"
          className="mx-auto mt-2 mb-1 h-1 w-9 rounded-full bg-[var(--rule-strong)]"
        />
      ) : null}
      <h2
        id={`${entryId}-title`}
        className={cn(
          "flex items-center gap-2 font-semibold",
          sheet ? "px-4 pt-1.5 text-base" : "px-3.5 pt-3 text-sm",
        )}
      >
        {departmentIndex !== null ? (
          <DepartmentMark departmentIndex={departmentIndex} />
        ) : null}
        {title}
      </h2>
      <div
        className={cn(
          "grid",
          sheet ? "gap-3 px-4 py-3" : "gap-2.5 px-3.5 pt-2.5 pb-3",
        )}
      >
        <div className="grid gap-1">
          <Input
            id={`${entryId}-name`}
            aria-label={`${word[0]!.toUpperCase()}${word.slice(1)} name`}
            autoComplete="off"
            maxLength={80}
            value={draft.name}
            aria-invalid={nameRefusal ? true : undefined}
            aria-describedby={
              [nameRefusal ? refusalId : null, blockedReason ? blockedId : null]
                .filter(Boolean)
                .join(" ") || undefined
            }
            className={control}
            onChange={(event) => onDraftChange({ name: event.target.value })}
          />
          {nameRefusal ? (
            <p
              id={refusalId}
              role="alert"
              className="text-destructive text-[13px]"
            >
              {refusal}
            </p>
          ) : null}
          {blockedReason ? (
            <p id={blockedId} className="text-muted-foreground text-[13px]">
              {blockedReason}
            </p>
          ) : null}
        </div>
        {kind === "field" ? (
          <>
            <TypeGroup value={draft.type} sheet={sheet} onPick={onTypePick} />
            {draft.type === "Select" ? (
              <div className="grid gap-1">
                <label
                  htmlFor={choicesId}
                  className="text-muted-foreground text-xs font-medium"
                >
                  Choices
                </label>
                <Input
                  id={choicesId}
                  autoComplete="off"
                  placeholder="Comma-separated"
                  value={draft.choices}
                  aria-invalid={choicesRefusal ? true : undefined}
                  aria-describedby={choicesRefusal ? refusalId : undefined}
                  className={control}
                  onChange={(event) =>
                    onDraftChange({ choices: event.target.value })
                  }
                />
                {choicesRefusal ? (
                  <p
                    id={refusalId}
                    role="alert"
                    className="text-destructive text-[13px]"
                  >
                    {refusal}
                  </p>
                ) : null}
              </div>
            ) : null}
            <div className="flex min-h-11 items-center gap-2 xl:min-h-8">
              <Checkbox
                id={requiredId}
                checked={draft.required}
                onCheckedChange={(checked) =>
                  onDraftChange({ required: checked === true })
                }
              />
              <label htmlFor={requiredId} className="text-sm">
                Required
              </label>
            </div>
          </>
        ) : null}
      </div>
      <div
        data-entry-footer=""
        className={cn(
          "flex items-center gap-2 border-t",
          sheet ? "flex-wrap px-4 pt-2.5 pb-4" : "px-3.5 py-2.5",
        )}
      >
        {kind === "department" && onFromTemplate ? (
          <Button
            type="button"
            variant="ghost"
            className={cn(
              control,
              "gap-1.5 px-2 whitespace-nowrap text-[var(--action-text)]",
              sheet ? "w-full justify-start" : "-ml-2",
            )}
            onClick={onFromTemplate}
          >
            <FileStack aria-hidden="true" />
            From a template
          </Button>
        ) : null}
        <div className={cn("flex gap-1.5", sheet ? "flex-1" : "ml-auto")}>
          <Button
            type="button"
            variant="ghost"
            className={cn(control, sheet && "flex-1")}
            onClick={onDone}
          >
            Done
          </Button>
          <DisabledReason reason={blockedReason} reasonId={blockedId} stable>
            <Button type="submit" className={cn(control, sheet && "flex-1")}>
              {`Add ${word}`}
            </Button>
          </DisabledReason>
        </div>
      </div>
    </form>
  );
}

/**
 * The 11 field types as one radio group (one Tab stop): arrows and
 * type-ahead choose and keep focus in the group; a click chooses and hands
 * focus back (`typePickFocus`).
 */
function TypeGroup({
  value,
  sheet,
  onPick,
}: {
  value: FieldTypeName;
  sheet: boolean;
  onPick: (type: FieldTypeName, by: "pointer" | "keyboard") => void;
}) {
  const chips = useRef(new Map<FieldTypeName, HTMLButtonElement>());
  const names = FIELD_TYPES.map((entry) => entry.name);
  const choose = (type: FieldTypeName) => {
    onPick(type, "keyboard");
    chips.current.get(type)?.focus();
  };
  return (
    <div
      role="radiogroup"
      aria-label="Field type"
      className="flex flex-wrap gap-1"
      onKeyDown={(event) => {
        const at = names.indexOf(value);
        const step =
          event.key === "ArrowRight" || event.key === "ArrowDown"
            ? 1
            : event.key === "ArrowLeft" || event.key === "ArrowUp"
              ? -1
              : 0;
        if (step !== 0) {
          event.preventDefault();
          choose(names[(at + step + names.length) % names.length]!);
          return;
        }
        if (event.key === "Home" || event.key === "End") {
          event.preventDefault();
          choose(names[event.key === "Home" ? 0 : names.length - 1]!);
          return;
        }
        // Type-ahead: the next type whose screen word starts with the key.
        if (
          event.key.length === 1 &&
          event.key !== " " &&
          !event.altKey &&
          !event.ctrlKey &&
          !event.metaKey
        ) {
          const key = event.key.toLowerCase();
          const match = [
            ...names.slice(at + 1),
            ...names.slice(0, at + 1),
          ].find((name) => fieldTypeLabel(name).toLowerCase().startsWith(key));
          if (match) {
            event.preventDefault();
            choose(match);
          }
        }
      }}
    >
      {names.map((name) => (
        <button
          key={name}
          ref={(element) => {
            if (element) chips.current.set(name, element);
            else chips.current.delete(name);
          }}
          type="button"
          role="radio"
          aria-checked={name === value}
          tabIndex={name === value ? 0 : -1}
          className={cn(
            "text-foreground focus-visible:outline-ring inline-flex items-center rounded-sm bg-[var(--surface-sunken)] outline-none focus-visible:outline-2 focus-visible:outline-offset-1 aria-checked:bg-[var(--action-tint)] aria-checked:font-semibold aria-checked:text-[var(--action-text)] aria-checked:shadow-[inset_0_0_0_1px_var(--action)]",
            sheet
              ? "h-11 px-3 text-sm"
              : "h-11 px-3 text-sm xl:h-7 xl:px-2.5 xl:text-[13px]",
          )}
          // A pointer click (detail > 0) hands focus back; Space keeps it.
          onClick={(event) =>
            onPick(name, event.detail > 0 ? "pointer" : "keyboard")
          }
        >
          {fieldTypeLabel(name)}
        </button>
      ))}
    </div>
  );
}
