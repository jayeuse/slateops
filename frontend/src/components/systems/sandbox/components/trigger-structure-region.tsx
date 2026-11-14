"use client";

import { useId, useState } from "react";
import { ArrowLeft, ArrowRight, Table2 } from "lucide-react";
import { DepartmentMark } from "@/components/sandbox/department-mark";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import type { SandboxDocumentDesign } from "../domain/document";
import { fieldTypeLabel } from "../domain/model";
import {
  draftModuleId,
  type SandboxTriggerDraft,
} from "../domain/trigger-draft";

// The structure region of Triggers (docs/specs/sandbox-ux-redesign.md
// TRIG-1): while a trigger is edited, its module's department, fields with
// their types, and links, so nobody leaves for Build to remember them.
// Read-only. From 1280px it is a pane beside the editor; narrower, the
// "<Module> fields" button opens it as a sheet. It belongs to the page, so
// it never touches unsaved trigger edits.

export type StructureLink = {
  id: string;
  direction: "out" | "in";
  moduleName: string;
  departmentName: string;
  departmentIndex: number;
};

export type StructureRegionModel =
  | {
      kind: "module";
      moduleName: string;
      departmentName: string;
      departmentIndex: number;
      fields: { id: string; name: string; type: string; required: boolean }[];
      links: StructureLink[];
    }
  | {
      kind: "design";
      departments: {
        id: string;
        name: string;
        index: number;
        modules: { id: string; name: string }[];
      }[];
    };

/**
 * What the region shows: the chosen module's head, open fields and links
 * (out, then in); with no module chosen, every department and its modules.
 */
export function structureRegionModel(
  design: SandboxDocumentDesign,
  moduleId: string,
): StructureRegionModel {
  const departmentOf = (id: string) => {
    const index = design.departments.findIndex((item) => item.id === id);
    return { name: design.departments[index]?.name ?? "", index };
  };
  const sandboxModule = moduleId
    ? design.modules.find((item) => item.id === moduleId)
    : undefined;
  if (!sandboxModule)
    return {
      kind: "design",
      departments: design.departments
        .map((department, index) => ({
          id: department.id,
          name: department.name,
          index,
          modules: design.modules
            .filter(
              (item) => item.departmentId === department.id && !item.closed,
            )
            .map((item) => ({ id: item.id, name: item.name })),
        }))
        .filter((department) => department.modules.length),
    };
  const department = departmentOf(sandboxModule.departmentId);
  const link = (
    id: string,
    direction: "out" | "in",
    otherId: string,
  ): StructureLink | null => {
    const other = design.modules.find((item) => item.id === otherId);
    if (!other) return null;
    const otherDepartment = departmentOf(other.departmentId);
    return {
      id,
      direction,
      moduleName: other.name,
      departmentName: otherDepartment.name,
      departmentIndex: otherDepartment.index,
    };
  };
  return {
    kind: "module",
    moduleName: sandboxModule.name,
    departmentName: department.name,
    departmentIndex: department.index,
    fields: sandboxModule.fields
      .filter((item) => !item.closed)
      .map((item) => ({
        id: item.id,
        name: item.name,
        type: fieldTypeLabel(item.type),
        required: item.required,
      })),
    links: [
      ...design.relationships
        .filter((item) => item.sourceModuleId === sandboxModule.id)
        .map((item) => link(item.id, "out", item.targetModuleId)),
      ...design.relationships
        .filter((item) => item.targetModuleId === sandboxModule.id)
        .map((item) => link(item.id, "in", item.sourceModuleId)),
    ].filter((item) => item !== null),
  };
}

/**
 * The fields of the trigger's module that a step uses ("trigger",
 * "condition:<id>", "action:<id>"), or with no step, that the whole trigger
 * uses. The region tints them.
 */
export function triggerFieldsInUse(
  draft: SandboxTriggerDraft,
  step: string | null,
): Set<string> {
  const moduleId = draftModuleId(draft);
  const used = new Set<string>();
  const add = (
    owner: string,
    reference: { moduleId: string; fieldId: string },
  ) => {
    if (
      (step === null || step === owner) &&
      reference.moduleId === moduleId &&
      reference.fieldId
    )
      used.add(reference.fieldId);
  };
  const trigger = draft.trigger;
  if (trigger.kind === "field-changed" || trigger.kind === "threshold-crossed")
    add("trigger", trigger);
  for (const condition of draft.conditionGroup.conditions)
    add(`condition:${condition.id}`, condition.field);
  for (const action of draft.actions)
    if (action.kind === "set-field") add(`action:${action.id}`, action.target);
  return used;
}

/** The name of the button that opens the region below 1280px. */
export function structureButtonLabel(
  design: SandboxDocumentDesign,
  moduleId: string,
): string {
  const sandboxModule = moduleId
    ? design.modules.find((item) => item.id === moduleId)
    : undefined;
  return sandboxModule ? `${sandboxModule.name} fields` : "Structure";
}

const rowTint = "bg-tint-selected text-foreground";

function SectionHeading({ label, count }: { label: string; count: number }) {
  return (
    <h3 className="text-muted-foreground px-2 pt-3 pb-1 text-xs font-medium">
      {label} <span className="tabular-nums">{count}</span>
    </h3>
  );
}

function RegionBody({
  model,
  highlighted,
}: {
  model: StructureRegionModel;
  highlighted: ReadonlySet<string>;
}) {
  if (model.kind === "design")
    return model.departments.length ? (
      <ul className="grid">
        {model.departments.map((department) => (
          <li key={department.id}>
            <p className="flex min-h-8 items-center gap-2 px-2 pt-2 text-xs font-medium">
              <DepartmentMark departmentIndex={department.index} />
              {department.name}
            </p>
            <ul>
              {department.modules.map((item) => (
                <li
                  key={item.id}
                  className="flex min-h-8 items-center gap-2 px-2 pl-4 text-sm"
                >
                  <Table2
                    aria-hidden="true"
                    className="text-muted-foreground size-3.5 shrink-0"
                  />
                  <span className="min-w-0 truncate">{item.name}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    ) : (
      <p className="text-muted-foreground p-2 text-sm">
        No modules yet. Add one in Build.
      </p>
    );
  return (
    <>
      <SectionHeading label="Fields" count={model.fields.length} />
      <ul className="grid">
        {model.fields.map((item) => (
          <li
            key={item.id}
            data-used={highlighted.has(item.id) || undefined}
            className={cn(
              "flex min-h-8 items-center gap-2 rounded-sm px-2 text-sm",
              highlighted.has(item.id) && rowTint,
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                "size-1.5 shrink-0 rounded-full",
                item.required
                  ? "bg-[var(--ink-muted)]"
                  : "shadow-[inset_0_0_0_1px_var(--ink-muted)]",
              )}
            />
            <span className="min-w-0 flex-1 truncate" title={item.name}>
              {item.name}
              {item.required ? (
                <span className="sr-only">, required</span>
              ) : null}
            </span>
            <span className="sr-only">, </span>
            <span className="text-muted-foreground shrink-0 font-mono text-xs">
              {item.type}
            </span>
          </li>
        ))}
      </ul>
      {model.links.length ? (
        <>
          <SectionHeading label="Links" count={model.links.length} />
          <ul className="grid">
            {model.links.map((item) => {
              const Arrow = item.direction === "out" ? ArrowRight : ArrowLeft;
              return (
                <li
                  key={`${item.direction}-${item.id}`}
                  className="flex min-h-8 items-center gap-2 px-2 text-sm"
                >
                  <Arrow
                    aria-hidden="true"
                    className="text-action-text size-3.5 shrink-0"
                  />
                  <span className="sr-only">
                    {item.direction === "out" ? "Links to " : "Linked from "}
                  </span>
                  <span className="min-w-0 flex-1 truncate">
                    {item.moduleName}
                  </span>
                  <span className="sr-only">, </span>
                  <span className="text-muted-foreground inline-flex shrink-0 items-center gap-1.5 text-xs">
                    <DepartmentMark departmentIndex={item.departmentIndex} />
                    {item.departmentName}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
    </>
  );
}

function RegionHead({
  model,
  titleId,
  Title = "h2",
}: {
  model: StructureRegionModel;
  titleId: string;
  Title?: "h2" | typeof SheetTitle;
}) {
  return model.kind === "module" ? (
    <div className="flex min-w-0 items-baseline gap-2">
      <DepartmentMark
        departmentIndex={model.departmentIndex}
        className="self-center"
      />
      <Title id={titleId} className="min-w-0 truncate font-semibold">
        {model.moduleName}
      </Title>
      <span className="text-muted-foreground shrink-0 text-sm">
        {model.departmentName}
      </span>
    </div>
  ) : (
    <div className="flex min-w-0 items-baseline gap-2">
      <Title id={titleId} className="font-semibold">
        Structure
      </Title>
      <span className="text-muted-foreground text-sm">
        {model.departments.length}{" "}
        {model.departments.length === 1 ? "department" : "departments"}
      </span>
    </div>
  );
}

/** The region as a pane beside the editor (1280px and wider). */
export function TriggerStructureRegion({
  design,
  moduleId,
  highlighted,
  className,
}: {
  design: SandboxDocumentDesign;
  moduleId: string;
  /** Fields the focused step uses (or the whole trigger), tinted. */
  highlighted: ReadonlySet<string>;
  className?: string;
}) {
  const titleId = useId();
  const model = structureRegionModel(design, moduleId);
  return (
    <aside
      aria-label="Structure"
      className={cn(
        "bg-card border-border flex min-h-0 min-w-0 flex-col overflow-clip rounded-xl border",
        className,
      )}
    >
      <div className="border-border flex min-h-14 items-center border-b px-4 py-2">
        <RegionHead model={model} titleId={titleId} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        <RegionBody model={model} highlighted={highlighted} />
      </div>
    </aside>
  );
}

/**
 * Below 1280px: the "<Module> fields" button, opening the region as a side
 * sheet, or a bottom sheet on a phone. Close returns focus to the button,
 * and the page keeps its scroll point (the sheet floats over it).
 */
export function TriggerStructureSheet({
  design,
  moduleId,
  highlighted,
  bottom,
  className,
}: {
  design: SandboxDocumentDesign;
  moduleId: string;
  highlighted: ReadonlySet<string>;
  /** A bottom sheet (phones) instead of a side sheet. */
  bottom: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const model = structureRegionModel(design, moduleId);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        render={
          <Button variant="ghost" className={cn("min-h-11", className)} />
        }
      >
        <Table2 aria-hidden="true" />
        {structureButtonLabel(design, moduleId)}
      </SheetTrigger>
      <SheetContent
        className={cn(
          "gap-0 p-0",
          bottom &&
            "inset-x-0 top-auto bottom-0 max-h-[min(70dvh,36rem)] w-full rounded-t-xl border-t border-l-0 pb-[env(safe-area-inset-bottom)] data-ending-style:translate-x-0 data-ending-style:translate-y-full data-starting-style:translate-x-0 data-starting-style:translate-y-full",
        )}
      >
        <div className="border-border flex min-h-14 items-center gap-2 border-b px-4 py-2">
          <RegionHead model={model} titleId={titleId} Title={SheetTitle} />
          <SheetClose
            render={<Button variant="ghost" className="ml-auto min-h-11" />}
          >
            Close
          </SheetClose>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          <RegionBody model={model} highlighted={highlighted} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
