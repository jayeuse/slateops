"use client";

import { useId, useRef, useState, type KeyboardEvent } from "react";
import { Link2, Table2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DialogFrameFooter,
  DialogFrameHeader,
  dialogFrameContentClass,
} from "@/components/ui/dialog-frame";
import { DisabledReason } from "@/components/ui/disabled-reason";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { departmentNameReason } from "../domain/create-checks";
import { uid, type Design } from "../domain/model";
import {
  mergeTemplateDepartment,
  templateDepartmentGroups,
  templateDepartmentLimitReason,
  templateDepartmentName,
  templateDepartmentSummary,
  type TemplateDepartment,
  type TemplateDepartmentGroup,
} from "../domain/template-merge";
import {
  SandboxCommandError,
  type SandboxCommandResult,
} from "../state/commands";
import { useDepartmentSetupDefault } from "../state/use-department-setup-default";

/**
 * "Add from a template" (docs/specs/sandbox-ux-redesign.md, FAST-7,
 * "Template department"): one department of the six organization templates,
 * chosen on the left and previewed on the right, added under a name that no
 * open department has. The add goes through the page's `change` like an
 * entry add: one queued save and one Undo step.
 */

export type TemplateDepartmentDialogProps = {
  open: boolean;
  /** The current draft design, for the name and the limits. */
  design: Design;
  /** From `designAddHoldReason`: a publish, lifecycle action, or conflict holds the draft. */
  holdReason: string | null;
  /** The control that opened the entry: it gets focus back. */
  anchor: HTMLElement | null;
  /** The page's `change`, as the entry uses it; an accepted add resolves at once. */
  onAdd: (
    update: (design: Design) => Design,
  ) => SandboxCommandResult<Design> | Promise<SandboxCommandResult<Design>>;
  /** The department was added: the caller selects it and closes the dialog. */
  onAdded: (departmentId: string) => void;
  onClose: () => void;
};

const GROUPS = templateDepartmentGroups();
const DEPARTMENTS = GROUPS.flatMap((group) => group.departments);

export function TemplateDepartmentDialog({
  open,
  design,
  holdReason,
  anchor,
  onAdd,
  onAdded,
  onClose,
}: TemplateDepartmentDialogProps) {
  const formId = useId();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent
        initialFocus={() => document.getElementById(`${formId}-name`)}
        finalFocus={() => anchor ?? true}
        className={cn(
          dialogFrameContentClass,
          "max-w-4xl max-xl:[&_button]:min-h-11 max-xl:[&_button]:min-w-11",
        )}
      >
        <DialogFrameHeader
          title={<DialogTitle>Add from a template</DialogTitle>}
          closeLabel="Close add from a template"
          onClose={onClose}
        />
        {/* The body mounts with the popup, so each open starts afresh. */}
        <TemplateDepartmentBody
          formId={formId}
          design={design}
          holdReason={holdReason}
          onAdd={onAdd}
          onAdded={onAdded}
          onClose={onClose}
        />
      </DialogContent>
    </Dialog>
  );
}

function TemplateDepartmentBody({
  formId,
  design,
  holdReason,
  onAdd,
  onAdded,
  onClose,
}: {
  formId: string;
  design: Design;
  holdReason: string | null;
  onAdd: TemplateDepartmentDialogProps["onAdd"];
  onAdded: (departmentId: string) => void;
  onClose: () => void;
}) {
  const [key, setKey] = useState(DEPARTMENTS[0]!.key);
  // The new department starts from the saved Manage default (FIT-4, SD-C20).
  const setupDefault = useDepartmentSetupDefault();
  // The name follows the choice until the administrator types in it.
  const [typedName, setTypedName] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const adding = useRef(false);
  const department = DEPARTMENTS.find((item) => item.key === key)!;
  const prefill = templateDepartmentName(design, department.name);
  const name = typedName ?? prefill.name;

  async function add() {
    if (adding.current) return;
    // One id per element, fixed before the update so a rerun reuses them.
    const ids = Array.from(
      { length: 1 + department.modules.length + department.links.length },
      uid,
    );
    adding.current = true;
    let result: SandboxCommandResult<Design>;
    try {
      result = await onAdd((current) => {
        let next = 0;
        const merged = mergeTemplateDepartment(
          current,
          department.key,
          name,
          () => ids[next++]!,
          setupDefault,
        );
        if (!merged.ok) throw new SandboxCommandError(merged.reason);
        return merged.design;
      });
    } finally {
      adding.current = false;
    }
    if (!result.ok) {
      setFailure(result.error);
      return;
    }
    onAdded(ids[0]!);
  }

  return (
    <TemplateDepartmentForm
      formId={formId}
      groups={GROUPS}
      department={department}
      name={name}
      takenLine={typedName === null ? prefill.taken : null}
      nameRefusal={
        typedName === null ? null : departmentNameReason(design, name)
      }
      limitReason={templateDepartmentLimitReason(design, department)}
      holdReason={holdReason}
      failure={failure}
      onChoose={(next) => {
        setKey(next);
        setFailure(null);
      }}
      onNameChange={(next) => {
        setTypedName(next);
        setFailure(null);
      }}
      onAdd={() => void add()}
      onCancel={onClose}
    />
  );
}

export type TemplateDepartmentFormProps = {
  /** Prefix of the name (`-name`) and option (`-option-<n>`) ids. */
  formId: string;
  groups: readonly TemplateDepartmentGroup[];
  department: TemplateDepartment;
  name: string;
  /** "Sales is taken in this design." while the prefill moved past it. */
  takenLine: string | null;
  /** Why a typed name cannot be used. */
  nameRefusal: string | null;
  /** Why the merge would pass a document limit. */
  limitReason: string | null;
  /** A publish, lifecycle action, or conflict holds the draft. */
  holdReason: string | null;
  /** Why the last add failed. */
  failure: string | null;
  onChoose: (key: string) => void;
  onNameChange: (name: string) => void;
  onAdd: () => void;
  onCancel: () => void;
};

/**
 * The dialog's choice, preview, and footer, under its pinned header:
 * controlled by the dialog.
 */
export function TemplateDepartmentForm({
  formId,
  groups,
  department,
  name,
  takenLine,
  nameRefusal,
  limitReason,
  holdReason,
  failure,
  onChoose,
  onNameChange,
  onAdd,
  onCancel,
}: TemplateDepartmentFormProps) {
  const id = useId();
  const nameLineId = `${id}-name-line`;
  const footerReasonId = `${id}-footer-reason`;
  const footerReason = holdReason ?? limitReason;
  const blocked = footerReason ?? nameRefusal;
  const options = groups.flatMap((group) => group.departments);
  const optionId = (key: string) =>
    `${formId}-option-${options.findIndex((item) => item.key === key)}`;

  function onListKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const at = options.findIndex((item) => item.key === department.key);
    const target =
      event.key === "ArrowDown"
        ? Math.min(at + 1, options.length - 1)
        : event.key === "ArrowUp"
          ? Math.max(at - 1, 0)
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? options.length - 1
              : null;
    if (target === null) return;
    event.preventDefault();
    const next = options[target]!;
    onChoose(next.key);
    document.getElementById(optionId(next.key))?.focus();
  }

  return (
    <>
      <div className="grid gap-4 md:min-h-0 md:flex-1 md:grid-cols-[17rem_minmax(0,1fr)] md:overflow-hidden">
        <div
          role="listbox"
          aria-label="Template departments"
          className="grid content-start gap-0.5 md:-ml-2 md:overflow-y-auto md:pr-1 md:pl-2"
          onKeyDown={onListKeyDown}
        >
          {groups.map((group) => {
            const headingId = `${formId}-group-${group.templateId}`;
            return (
              <div
                key={group.templateId}
                role="group"
                aria-labelledby={headingId}
                className="grid gap-0.5 pt-2 first:pt-0"
              >
                <div
                  id={headingId}
                  role="presentation"
                  className="text-muted-foreground px-2.5 pb-1 text-xs font-medium"
                >
                  {group.templateName}
                </div>
                {group.departments.map((item) => {
                  const selected = item.key === department.key;
                  const count = `${item.modules.length} ${item.modules.length === 1 ? "module" : "modules"}`;
                  return (
                    <div
                      key={item.key}
                      id={optionId(item.key)}
                      role="option"
                      aria-label={`${item.name}, ${count}`}
                      aria-selected={selected}
                      tabIndex={selected ? 0 : -1}
                      className={cn(
                        "focus-visible:outline-ring flex min-h-11 cursor-default items-center justify-between gap-3 rounded-md px-2.5 text-sm outline-none select-none focus-visible:outline-2 focus-visible:outline-offset-[-2px] xl:min-h-9",
                        selected
                          ? "bg-[var(--action-tint)] font-medium text-[var(--action-text)]"
                          : "hover:bg-muted",
                      )}
                      onClick={() => onChoose(item.key)}
                    >
                      <span className="min-w-0 truncate">{item.name}</span>
                      <span
                        className={cn(
                          "shrink-0 text-xs tabular-nums",
                          selected ? "" : "text-muted-foreground",
                        )}
                      >
                        {count}
                      </span>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
        <div className="grid min-w-0 content-start gap-4 md:overflow-y-auto">
          <div className="grid gap-1 sm:grid-cols-[6rem_minmax(0,1fr)] sm:items-center sm:gap-x-3">
            <label
              htmlFor={`${formId}-name`}
              className="text-muted-foreground text-xs font-medium"
            >
              Name
            </label>
            <Input
              id={`${formId}-name`}
              autoComplete="off"
              maxLength={80}
              value={name}
              aria-invalid={nameRefusal ? true : undefined}
              aria-describedby={
                nameRefusal || takenLine ? nameLineId : undefined
              }
              className="h-11 xl:h-8"
              onChange={(event) => onNameChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key !== "Enter" || event.nativeEvent.isComposing)
                  return;
                event.preventDefault();
                if (!blocked) onAdd();
              }}
            />
            {nameRefusal || takenLine ? (
              <p
                id={nameLineId}
                className={cn(
                  "text-[13px] sm:col-start-2",
                  nameRefusal ? "text-destructive" : "text-muted-foreground",
                )}
              >
                {nameRefusal ?? takenLine}
              </p>
            ) : null}
          </div>
          <ul
            aria-label={`${department.name} modules`}
            className="grid gap-3 sm:grid-cols-2"
          >
            {department.modules.map((item) => {
              const more = item.fieldCount - item.firstFields.length;
              return (
                <li
                  key={item.id}
                  className="grid content-start rounded-md bg-[var(--surface-sunken)] pb-2"
                >
                  <p className="flex items-center gap-2 px-2.5 pt-2 pb-1 text-sm font-semibold">
                    <Table2
                      aria-hidden="true"
                      className="text-muted-foreground size-4 shrink-0"
                    />
                    <span className="min-w-0 truncate">{item.name}</span>
                  </p>
                  {item.firstFields.map((field) => (
                    <p
                      key={field.name}
                      className="flex items-baseline justify-between gap-3 px-2.5 py-0.5 text-[13px]"
                    >
                      <span className="min-w-0 truncate">{field.name}</span>
                      <span className="text-muted-foreground shrink-0 font-[family-name:var(--font-code)] text-xs">
                        {field.type}
                      </span>
                    </p>
                  ))}
                  {more > 0 ? (
                    <p className="text-muted-foreground px-2.5 pt-1 text-xs">
                      + {more} more {more === 1 ? "field" : "fields"}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {department.links.length ? (
            <ul
              aria-label={`${department.name} links`}
              className="grid gap-1.5 text-sm"
            >
              {department.links.map((link) => (
                <li key={link.id} className="flex items-center gap-2">
                  <Link2
                    aria-hidden="true"
                    className="size-4 shrink-0 text-[var(--action-text)]"
                  />
                  {link.name}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
      <DialogFrameFooter>
        {failure ? (
          <Alert role="alert" variant="destructive">
            {failure}
          </Alert>
        ) : null}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="grid gap-0.5 text-[13px]">
            <p className="text-muted-foreground">
              {templateDepartmentSummary(department)}
            </p>
            {footerReason ? (
              <p id={footerReasonId} className="text-warn-text">
                {footerReason}
              </p>
            ) : null}
          </div>
          <DialogFooter className="mt-0 sm:ml-auto">
            <Button variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <DisabledReason
              stable
              reason={blocked}
              reasonId={
                footerReason
                  ? footerReasonId
                  : nameRefusal
                    ? nameLineId
                    : undefined
              }
            >
              <Button onClick={onAdd}>Add department</Button>
            </DisabledReason>
          </DialogFooter>
        </div>
      </DialogFrameFooter>
    </>
  );
}
