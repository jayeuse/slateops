import { expect, test } from "@playwright/test";

import {
  CreateEntryForm,
  type CreateEntryFormProps,
} from "../../../src/components/systems/sandbox/components/create-entry";
import { emptyCreateDraft } from "../../../src/components/systems/sandbox/domain/create-checks";
import { staticMarkup } from "./static-markup";

// The add-next entry as rendered (docs/specs/sandbox-ux-redesign.md, "The
// entry"; comps build-adddept-1440, build-addfield-1440 and -390).

function entry(patch: Partial<CreateEntryFormProps> = {}): string {
  return staticMarkup(CreateEntryForm, {
    kind: "field",
    parentName: "Orders",
    departmentIndex: 0,
    draft: emptyCreateDraft,
    refusal: null,
    blockedReason: null,
    sheet: false,
    entryId: "entry",
    onDraftChange: () => undefined,
    onTypePick: () => undefined,
    onEnter: () => undefined,
    onAdd: () => undefined,
    onDone: () => undefined,
    ...patch,
  });
}

function radios(html: string): Array<[string, string]> {
  return [
    ...html.matchAll(/role="radio" aria-checked="(true|false)"[^>]*>([^<]+)</g),
  ].map((match) => [match[2]!, match[1]!]);
}

// UX-C8 (FAST-2)
test("the field entry offers the 11 types in model order with Text chosen", () => {
  const html = entry();
  expect(html).toContain(">Add field to Orders</h2>");
  expect(html).toContain('role="radiogroup" aria-label="Field type"');
  expect(radios(html)).toEqual([
    ["Text", "true"],
    ["Long text", "false"],
    ["Number", "false"],
    ["Whole number", "false"],
    ["Date", "false"],
    ["Date and time", "false"],
    ["Checkbox", "false"],
    ["Choice list", "false"],
    ["User", "false"],
    ["Email", "false"],
    ["Web link", "false"],
  ]);
  // One Tab stop for the group: only the chosen type is tabbable.
  expect(html.match(/role="radio"[^>]*tabindex="0"/g)).toHaveLength(1);
  expect(html).toContain(">Required<");
  expect(html).not.toContain('aria-label="Choices"');
  expect(html).toContain(">Done</button>");
  expect(html).toContain(">Add field</button>");

  // A Choice list asks for its choices.
  expect(entry({ draft: { ...emptyCreateDraft, type: "Select" } })).toContain(
    ">Choices</label>",
  );
});

// UX-C6 (FAST-1)
test("the department and module entries name only what they add", () => {
  const department = entry({
    kind: "department",
    parentName: null,
    departmentIndex: null,
  });
  expect(department).toContain(">Add department</h2>");
  expect(department).toContain(">Add department</button>");
  expect(department).not.toContain('role="radiogroup"');
  expect(department).not.toContain(">Required<");

  const moduleEntry = entry({ kind: "module", parentName: "Sales" });
  expect(moduleEntry).toContain(">Add module to Sales</h2>");
  expect(moduleEntry).toContain('aria-label="Module name"');
  expect(moduleEntry).toContain(">Add module</button>");
});

// N2: refused in place, under the name, and the name stays.
test("a refused add shows its reason under the name and keeps the name", () => {
  const html = entry({
    draft: { ...emptyCreateDraft, name: "Status", type: "Select" },
    refusal: "Orders already has a field named Status.",
  });
  expect(html).toMatch(
    /aria-label="Field name"[^>]*aria-invalid="true"|aria-invalid="true"[^>]*aria-label="Field name"/,
  );
  expect(html).toContain('value="Status"');
  expect(html).toMatch(
    /role="alert"[^>]*>Orders already has a field named Status\.</,
  );
});

// B5d (Product Designer review): a choice problem shows under Choices,
// which is invalid; the name is not.
test("a refused Choice list shows its choice problem under Choices", () => {
  const html = entry({
    draft: { ...emptyCreateDraft, name: "Status", type: "Select" },
    refusal: "Add at least one choice.",
    refusalOn: "choices",
  });
  expect(html).toMatch(
    /id="entry-choices"[^>]*aria-invalid="true"[^>]*\/>(?:(?!<input)[\s\S])*role="alert"[^>]*>Add at least one choice\.</,
  );
  expect(html).not.toMatch(
    /aria-label="Field name"[^>]*aria-invalid="true"|aria-invalid="true"[^>]*aria-label="Field name"/,
  );
});

// N1 rule 6 and the N2 limits: the add says why it cannot act.
test("a held draft or a reached limit disables the add with its reason", () => {
  for (const reason of [
    "Wait for the current Sandbox action to finish.",
    "This design has 5,000 fields, the limit.",
  ]) {
    const html = entry({ blockedReason: reason });
    expect(html, reason).toContain(`>${reason}<`);
    expect(html, reason).toMatch(/aria-disabled="true"[^>]*>Add field</);
  }
  expect(entry()).not.toContain('aria-disabled="true"');
});
