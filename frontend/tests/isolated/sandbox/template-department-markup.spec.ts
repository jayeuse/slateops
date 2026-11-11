import { expect, test } from "@playwright/test";

import {
  TemplateDepartmentForm,
  type TemplateDepartmentFormProps,
} from "../../../src/components/systems/sandbox/components/template-department-dialog";
import { templateDepartmentGroups } from "../../../src/components/systems/sandbox/domain/template-merge";
import { staticMarkup } from "./static-markup";

// "Add from a template" as rendered (docs/specs/sandbox-ux-redesign.md,
// FAST-7, "Template department"; comp build-template-1440).

const groups = templateDepartmentGroups();
const sales = groups
  .flatMap((group) => group.departments)
  .find((item) => item.name === "Sales")!;

function dialog(patch: Partial<TemplateDepartmentFormProps> = {}): string {
  return staticMarkup(TemplateDepartmentForm, {
    formId: "template",
    groups,
    department: sales,
    name: "Sales 2",
    takenLine: "Sales is taken in this design.",
    nameRefusal: null,
    limitReason: null,
    holdReason: null,
    failure: null,
    onChoose: () => undefined,
    onNameChange: () => undefined,
    onAdd: () => undefined,
    onCancel: () => undefined,
    ...patch,
  });
}

/** The text of the element whose id the name input's description names. */
function nameDescription(html: string): string | null {
  const ids = /id="template-name"[^>]*aria-describedby="([^"]+)"/.exec(html);
  if (!ids) return null;
  return new RegExp(`id="${ids[1]}"[^>]*>([^<]*)<`).exec(html)?.[1] ?? null;
}

// FAST-7: one grouped choice on the left, the chosen department on the right.
test("the dialog lists the template departments as one grouped choice and previews the chosen one", () => {
  const html = dialog();
  expect(html).toContain('role="listbox" aria-label="Template departments"');
  expect(html.match(/role="group"/g)).toHaveLength(6);
  expect(html.match(/role="option"/g)).toHaveLength(23);
  // One Tab stop: only the chosen department is tabbable.
  expect(html.match(/role="option"[^>]*aria-selected="true"/g)).toHaveLength(1);
  expect(html.match(/role="option"[^>]*tabindex="0"/g)).toHaveLength(1);
  expect(html).toMatch(
    /role="option" aria-label="Sales, 3 modules" aria-selected="true"/,
  );
  // The name, prefilled past the taken one, with the line that says so.
  expect(html).toMatch(/<input[^>]*id="template-name"[^>]*value="Sales 2"/);
  expect(nameDescription(html)).toBe("Sales is taken in this design.");
  // Modules with their first fields, then the department's own links.
  expect(html).toContain('aria-label="Sales modules"');
  expect(html).toContain(">Customers</span>");
  expect(html).toContain(">Choice list</span>");
  expect(html).toContain(">+ 4 more fields</p>");
  expect(html).toContain('aria-label="Sales links"');
  expect(html).toContain("Opportunity sales orders</li>");
  expect(html).toContain(">Adds 3 modules and 3 links, without triggers.</p>");
  expect(html).toContain(">Cancel</button>");
  expect(html).not.toContain('aria-disabled="true"');
});

// FAST-7, N2, N1 rule 6: Add department says why it cannot add.
test("a taken name, a passed limit, or a held draft disables Add department with its reason", () => {
  const taken = dialog({
    name: "Sales",
    takenLine: null,
    nameRefusal: "A department named Sales already exists.",
  });
  expect(taken).toMatch(/id="template-name"[^>]*aria-invalid="true"/);
  expect(nameDescription(taken)).toBe(
    "A department named Sales already exists.",
  );
  expect(taken).toMatch(/aria-disabled="true"[^>]*>Add department</);

  for (const [patch, reason] of [
    [
      { limitReason: "Adds 3 modules; this design has room for 2." },
      "Adds 3 modules; this design has room for 2.",
    ],
    [
      { holdReason: "Wait for the current Sandbox action to finish." },
      "Wait for the current Sandbox action to finish.",
    ],
  ] as const) {
    const html = dialog(patch);
    // Add department is disabled and described by the visible reason.
    const button = /<button([^>]*)>Add department<\/button>/.exec(html)![1]!;
    expect(button, reason).toContain('aria-disabled="true"');
    const reasonId = /aria-describedby="([^"]+)"/.exec(button)![1];
    expect(
      new RegExp(`id="${reasonId}"[^>]*>([^<]*)<`).exec(html)?.[1],
      reason,
    ).toBe(reason);
  }
});
