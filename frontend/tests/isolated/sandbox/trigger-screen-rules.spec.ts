import { expect, test } from "@playwright/test";

import type { SandboxTrigger } from "../../../src/components/systems/sandbox/domain/document";
import { defaultTrigger } from "../../../src/components/systems/sandbox/domain/trigger-rules";
import { TriggerList } from "../../../src/components/systems/sandbox/components/trigger-list";
import { TriggerRail } from "../../../src/components/systems/sandbox/components/trigger-rail";
import {
  configuredSandboxDesign,
  sandboxDocumentFromDesign,
} from "../../helpers/sandbox-fixtures";
import { staticMarkup } from "./static-markup";

// Screen rules from the Product Designer's PR1 review of Triggers
// (docs/specs/sandbox-ux-redesign.md TRIG-1 to TRIG-5): a list row keeps its
// name readable beside its badges, a step's empty-part reason sits under the
// control it is about, and a saved operator that does not fit reads short.

const document = sandboxDocumentFromDesign(configuredSandboxDesign);
const design = document.design;

function rail(recordTrigger: SandboxTrigger): string {
  return staticMarkup(TriggerRail, {
    design,
    trigger: recordTrigger,
    stepErrors: new Map<string, string>(),
    pending: false,
    locked: false,
    onChange: () => undefined,
  });
}

test(
  "a list row with a badge keeps its name and shows the event as its icon only",
  { tag: "@UX-C18" },
  () => {
    const saved = document.triggers[0]!;
    const fresh = {
      ...defaultTrigger(design),
      id: "fresh",
      name: "New trigger",
    };
    const markup = staticMarkup(TriggerList, {
      listRef: null,
      status: "all",
      onStatusChange: () => undefined,
      triggers: [saved, fresh],
      selectedId: "fresh",
      unsaved: new Set(["fresh"]),
      incomplete: new Set(["fresh"]),
      phone: false,
      canCreate: true,
      onOpen: () => undefined,
      onCreate: () => undefined,
    });
    const rows = markup.split("data-trigger-row").slice(1);
    const [savedRow, freshRow] = rows;
    // The badged row keeps the event word for assistive technology only.
    expect(freshRow).toContain('<span class="sr-only">Item added</span>');
    expect(savedRow).not.toContain('<span class="sr-only">');
    // Its name keeps an 8rem floor and its full text.
    expect(freshRow).toMatch(
      /class="[^"]*\bmin-w-32\b[^"]*"[^>]*>New trigger</,
    );
  },
);

test(
  "the reason for an empty module sits directly under the Module control",
  { tag: "@UX-C19" },
  () => {
    const markup = rail(defaultTrigger(design));
    const reason = markup.indexOf("Choose a module.");
    expect(reason).toBeGreaterThan(markup.indexOf('aria-label="Event module"'));
    expect(reason).toBeLessThan(markup.indexOf(">Event</label>"));
  },
);

test(
  "a saved operator that does not fit reads as saved in its select, and why under the row",
  { tag: "@UX-C17" },
  () => {
    const requests = design.modules[0]!;
    const title = requests.fields.find((field) => field.name === "Title")!;
    const markup = rail({
      ...document.triggers[0]!,
      trigger: { kind: "record-created", moduleId: requests.id },
      conditionGroup: {
        operator: "all",
        conditions: [
          {
            id: "misfit",
            field: { moduleId: requests.id, fieldId: title.id },
            operator: ">",
            value: { kind: "literal", value: "M" },
          },
        ],
      },
    });
    expect(markup).toContain(">is more than · saved</option>");
    expect(markup).not.toContain("saved · does not fit");
    expect(markup).toContain("Does not fit Text; choose is or is not.");
  },
);
