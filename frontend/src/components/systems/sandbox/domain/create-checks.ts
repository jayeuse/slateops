import {
  DEPARTMENT_WIDTH,
  MODULE_TABLE,
  departmentPosition,
  departmentSize,
  modulePosition,
  moduleTableHeight,
  type CanvasBox,
  type CanvasPosition,
} from "@/lib/sandbox/canvas-geometry";
import { buildField } from "../components/designer-field-settings";
import type {
  Department,
  DepartmentSetup,
  Design,
  FieldTypeName,
} from "./model";
import { clashReason, relationshipNamesInUse } from "./relationship-name";
import { SANDBOX_LIMITS } from "./validation-types";

/**
 * The add-next entry's rules (docs/specs/sandbox-ux-redesign.md, "The
 * entry", N2 and N3). Several adds can join one save, and one bad element
 * would refuse the whole batch, so every add is checked here before it
 * changes the draft. An add returns the next design with the element and,
 * for a department or a module, its layout box: one change, one Undo step,
 * one queued add (`classifyDesignChange`).
 */

export type CreateKind = "department" | "module" | "field";

/** What the entry holds between adds. `type` and `choices` serve fields only. */
export type CreateDraft = {
  name: string;
  type: FieldTypeName;
  required: boolean;
  /** Comma-separated choices of a Choice list (`Select`). */
  choices: string;
};

/** The entry at open and after each add: no name, Text, not required. */
export const emptyCreateDraft: CreateDraft = {
  name: "",
  type: "Text",
  required: false,
  choices: "",
};

export type CreateAdd =
  { ok: true; design: Design } | { ok: false; reason: string };

/** The API's layout entry limit (`designs/schemas.py`, `max_length=600`). */
export const LAYOUT_ENTRIES = 600;

const count = (value: number) => value.toLocaleString("en-US");

/**
 * Why no element of this kind can be added: the design is at a document
 * limit. Closed elements count, as the save counts them.
 */
export function createLimitReason(
  design: Design,
  kind: CreateKind,
): string | null {
  const layoutEntries = Object.keys(design.layout ?? {}).length;
  const limits: Array<[number, number, string]> =
    kind === "department"
      ? [
          [
            design.departments.length,
            SANDBOX_LIMITS.departments,
            "departments",
          ],
          [layoutEntries, LAYOUT_ENTRIES, "departments and modules"],
        ]
      : kind === "module"
        ? [
            [design.modules.length, SANDBOX_LIMITS.modules, "modules"],
            [layoutEntries, LAYOUT_ENTRIES, "departments and modules"],
          ]
        : [
            [
              design.modules.reduce(
                (total, item) => total + item.fields.length,
                0,
              ),
              SANDBOX_LIMITS.fields,
              "fields",
            ],
          ];
  for (const [current, limit, noun] of limits)
    if (current >= limit)
      return `This design has ${count(limit)} ${noun}, the limit.`;
  return null;
}

/**
 * A department that Build creates: by the entry, a template merge, or
 * Duplicate (FIT-4, N13). It starts from the saved Manage default (BE-SD6,
 * SD-C20), so every create path starts from the same value. With no default
 * read yet it writes no `setup` (missing means all on, BE-SD5).
 */
export function newDepartment(
  id: string,
  name: string,
  setup?: DepartmentSetup,
): Department {
  return {
    id,
    name: name.trim(),
    closed: false,
    ...(setup ? { setup: { ...setup } } : {}),
  };
}

/** Why a department name cannot be used: blank, too long, or taken. */
export function departmentNameReason(
  design: Design,
  name: string,
): string | null {
  return (
    nameReason(name) ?? duplicateNameReason(design, "department", null, name)
  );
}

function nameReason(name: string): string | null {
  const trimmed = name.trim();
  if (!trimmed) return "Enter a name.";
  return trimmed.length > SANDBOX_LIMITS.nameCharacters
    ? `Use ${SANDBOX_LIMITS.nameCharacters} characters or fewer.`
    : null;
}

const sameName = (left: string, right: string) =>
  left.trim().toLowerCase() === right.trim().toLowerCase();

/**
 * A name publish would refuse as a duplicate, in the scope publish checks
 * (`publications/preflight.py`): open departments across the design, open
 * modules of the same department, and a module's open fields with its
 * outgoing relationships to open modules. The browser compares without
 * case, stricter than publish, as Connect does.
 */
function duplicateNameReason(
  design: Design,
  kind: CreateKind,
  parentId: string | null,
  name: string,
): string | null {
  if (kind === "department") {
    const taken = design.departments.find(
      (item) => !item.closed && sameName(item.name, name),
    );
    return taken ? `A department named ${taken.name} already exists.` : null;
  }
  if (kind === "module") {
    const department = design.departments.find((item) => item.id === parentId);
    const taken = design.modules.find(
      (item) =>
        item.department === parentId &&
        !item.closed &&
        sameName(item.name, name),
    );
    return taken && department
      ? `${department.name} already has a module named ${taken.name}.`
      : null;
  }
  const parent = design.modules.find((item) => item.id === parentId);
  if (!parent || !parentId) return null;
  return clashReason(
    name,
    relationshipNamesInUse(design, parentId),
    parent.name,
  );
}

/** A box inside the document's coordinate limit (±100,000). */
export function insideCanvas(box: CanvasBox): boolean {
  return (
    Math.abs(box.x) <= SANDBOX_LIMITS.layoutCoordinate &&
    Math.abs(box.y) <= SANDBOX_LIMITS.layoutCoordinate
  );
}

function overlaps(a: CanvasBox, b: CanvasBox): boolean {
  return (
    a.x < b.x + b.width &&
    b.x < a.x + a.width &&
    a.y < b.y + b.height &&
    b.y < a.y + a.height
  );
}

/** Space between two department frames, as the canvas places them. */
const DEPARTMENT_GAP =
  departmentPosition(1).x - departmentPosition(0).x - DEPARTMENT_WIDTH;

/** The next free slot right of the existing department frames. */
function nextDepartmentBox(design: Design): CanvasBox {
  return { ...nextDepartmentSlot(design), ...departmentSize([]) };
}

/** Where the next department frame starts: right of the existing frames. */
export function nextDepartmentSlot(design: Design): CanvasPosition {
  const layout = design.layout ?? {};
  const frames = design.departments.map(
    (item, index) =>
      layout[item.id] ?? {
        ...departmentPosition(index),
        width: DEPARTMENT_WIDTH,
        height: 0,
      },
  );
  return frames.length === 0
    ? departmentPosition(0)
    : {
        x: Math.max(...frames.map((box) => box.x + box.width)) + DEPARTMENT_GAP,
        y: Math.min(...frames.map((box) => box.y)),
      };
}

/** The first slot of the frame, in reading order, that no module covers. */
function nextModuleBox(design: Design, departmentId: string): CanvasBox {
  const layout = design.layout ?? {};
  const index = design.departments.findIndex(
    (item) => item.id === departmentId,
  );
  const siblings = design.modules.filter(
    (item) => item.department === departmentId,
  );
  // The canvas draws a module as tall as its fields, whatever is stored.
  const heights = siblings.map((item) => moduleTableHeight(item.fields.length));
  const frame = layout[departmentId] ?? {
    ...departmentPosition(index),
    ...departmentSize(heights),
  };
  const taken = siblings.flatMap((item, at) => {
    const box = layout[item.id];
    return box ? [{ ...box, height: heights[at]! }] : [];
  });
  const height = moduleTableHeight(0);
  let box: CanvasBox | null = null;
  // Each existing module covers a few slots at most.
  for (let slot = siblings.length; slot <= siblings.length * 4; slot += 1) {
    const slotHeights = [
      ...heights,
      ...Array.from({ length: slot - siblings.length + 1 }, () => height),
    ];
    box = {
      ...modulePosition(frame, slot, slotHeights),
      width: MODULE_TABLE.width,
      height,
    };
    if (!taken.some((other) => overlaps(box!, other))) break;
  }
  return box!;
}

function addDepartment(
  design: Design,
  id: string,
  name: string,
  setup: DepartmentSetup | undefined,
): CreateAdd {
  const box = nextDepartmentBox(design);
  if (!insideCanvas(box))
    return {
      ok: false,
      reason: "The canvas has no room for another department.",
    };
  return {
    ok: true,
    design: {
      ...design,
      departments: [...design.departments, newDepartment(id, name, setup)],
      layout: { ...design.layout, [id]: box },
    },
  };
}

function addModule(
  design: Design,
  id: string,
  departmentId: string,
  name: string,
): CreateAdd {
  if (!design.departments.some((item) => item.id === departmentId))
    return {
      ok: false,
      reason:
        "This department was deleted. Refresh the designer and try again.",
    };
  const box = nextModuleBox(design, departmentId);
  if (!insideCanvas(box))
    return {
      ok: false,
      reason: "The canvas has no room for another module here.",
    };
  return {
    ok: true,
    design: {
      ...design,
      modules: [
        ...design.modules,
        {
          id,
          department: departmentId,
          name: name.trim(),
          closed: false,
          fields: [],
          // A parsed document takes the module position from its box.
          x: box.x,
          y: box.y,
        },
      ],
      layout: { ...design.layout, [id]: box },
    },
  };
}

function addField(
  design: Design,
  id: string,
  moduleId: string,
  draft: CreateDraft,
): CreateAdd {
  if (!design.modules.some((item) => item.id === moduleId))
    return {
      ok: false,
      reason: "This module was deleted. Refresh the designer and try again.",
    };
  const choices = choicesReason(draft);
  if (choices) return { ok: false, reason: choices };
  // Today's create rules (`buildField`), with every setting the entry does
  // not show left at its default.
  const field = buildField(
    {
      id,
      name: "",
      type: "Text",
      required: false,
      value: "",
      options: "",
      closed: false,
    },
    {
      name: draft.name,
      description: "",
      type: draft.type,
      required: draft.required,
      defaultValue: "",
      options: draft.choices,
      maxLength: "",
      min: "",
      max: "",
      step: "",
      earliest: "",
      latest: "",
      checked: false,
    },
  );
  if (typeof field === "string") return { ok: false, reason: field };
  // A field has no layout box: the canvas grows its card by one row.
  return {
    ok: true,
    design: {
      ...design,
      modules: design.modules.map((item) =>
        item.id === moduleId
          ? { ...item, fields: [...item.fields, field] }
          : item,
      ),
    },
  };
}

/**
 * The entry's add: the next design, or why the save would refuse it.
 * `parentId` is the department of a module and the module of a field.
 * `setup` is the new-department default (FIT-4); other kinds ignore it.
 */
export function addElement(
  design: Design,
  kind: CreateKind,
  id: string,
  parentId: string | null,
  draft: CreateDraft,
  setup?: DepartmentSetup,
): CreateAdd {
  const limit = createLimitReason(design, kind);
  if (limit) return { ok: false, reason: limit };
  const name =
    nameReason(draft.name) ??
    duplicateNameReason(design, kind, parentId, draft.name);
  if (name) return { ok: false, reason: name };
  if (kind === "department")
    return addDepartment(design, id, draft.name, setup);
  if (kind === "module")
    return addModule(design, id, parentId ?? "", draft.name);
  return addField(design, id, parentId ?? "", draft);
}

/**
 * What a key does in the entry. Enter adds; Enter on a blank name and
 * Escape end the flow, and the empty entry creates nothing.
 */
export function createEntryKey(
  draft: CreateDraft,
  key: "Enter" | "Escape",
): "add" | "close" {
  return key === "Enter" && draft.name.trim() ? "add" : "close";
}

/**
 * Where focus goes after a type is clicked: back to the name, so the next
 * key types the name; a Choice list needs its choices first.
 */
export function typePickFocus(type: FieldTypeName): "name" | "choices" {
  return type === "Select" ? "choices" : "name";
}

/**
 * Why a Choice list's choices cannot be saved, or null: none given, or a
 * choice rule of the save (`buildField`), such as a repeated choice.
 */
function choicesReason(draft: CreateDraft): string | null {
  if (draft.type !== "Select") return null;
  if (!draft.choices.split(",").some((choice) => choice.trim()))
    return "Add at least one choice.";
  const probe = buildField(
    {
      id: "choices",
      name: "",
      type: "Text",
      required: false,
      value: "",
      options: "",
      closed: false,
    },
    {
      name: "Choices",
      description: "",
      type: "Select",
      required: false,
      defaultValue: "",
      options: draft.choices,
      maxLength: "",
      min: "",
      max: "",
      step: "",
      earliest: "",
      latest: "",
      checked: false,
    },
  );
  return typeof probe === "string" ? probe : null;
}

/**
 * Where a refused add shows its reason (spec B5d): a choice problem under
 * Choices, every other reason under the name.
 */
export function createRefusalPlace(
  draft: CreateDraft,
  reason: string,
): "name" | "choices" {
  return reason === choicesReason(draft) ? "choices" : "name";
}
