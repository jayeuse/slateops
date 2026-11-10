import { expect, test } from "@playwright/test";
import {
  clearKeptTriggerDrafts,
  readKeptTriggerDraft,
  triggerDraftStorageKey,
  triggerSaveFailure,
  writeKeptTriggerDraft,
} from "../../../src/components/systems/sandbox/components/use-trigger-draft";
import { SandboxCommandError } from "../../../src/components/systems/sandbox/state/commands";
import {
  defaultTrigger,
  triggerStepErrors,
} from "../../../src/components/systems/sandbox/domain/trigger-rules";
import {
  checkTriggerDrafts,
  parseKeptTriggerDrafts,
  triggerDraftGaps,
} from "../../../src/components/systems/sandbox/domain/trigger-draft";
import { triggerEditsHoldMove } from "../../../src/components/systems/sandbox/helpers/work-in-progress";
import {
  configuredSandboxDesign,
  sandboxDocumentFromDesign,
} from "../../helpers/sandbox-fixtures";

// Phase 1 of the Sandbox follow-up pass (docs/specs/sandbox-followup-pass.md):
// unsaved trigger edits survive moves and reloads.

/** An in-memory Storage with the parts the draft code uses. */
function memoryStorage(entries: Record<string, string> = {}) {
  const values = new Map(Object.entries(entries));
  return {
    get length() {
      return values.size;
    },
    key: (index: number) => [...values.keys()][index] ?? null,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
    removeItem: (key: string) => void values.delete(key),
    keys: () => [...values.keys()],
  };
}

test("unsaved triggers hold a move only when it leaves Triggers or the Sandbox", () => {
  const rows: Array<[string, string | null, boolean]> = [
    ["Triggers", "Build", true],
    ["Triggers", null, true],
    ["Build", null, true],
    ["Build", "Test", false],
    ["Build", "Triggers", false],
    ["History", "Triggers", false],
  ];
  for (const [from, to, held] of rows)
    expect(triggerEditsHoldMove(from, to), `${from} → ${to}`).toBe(held);
});

test("kept trigger edits read back only when they still parse against the draft", () => {
  const document = sandboxDocumentFromDesign(configuredSandboxDesign);
  const key = triggerDraftStorageKey("user-1", "org-1");
  const edited = [{ ...document.triggers[0]!, name: "Kept name" }];
  const storage = memoryStorage();

  writeKeptTriggerDraft(storage, key, { base: "[]", triggers: edited });
  expect(readKeptTriggerDraft(storage, key, document)?.triggers[0]?.name).toBe(
    "Kept name",
  );

  for (const damaged of [
    "not json",
    JSON.stringify({ version: 3, base: "[]", triggers: edited }),
    JSON.stringify({ version: 1, base: "[]", triggers: [{ id: 7 }] }),
  ]) {
    storage.setItem(key, damaged);
    expect(readKeptTriggerDraft(storage, key, document)).toBeNull();
  }

  writeKeptTriggerDraft(storage, key, null);
  expect(storage.getItem(key)).toBeNull();
});

test("sign-out clears one account's kept trigger edits and no other's", () => {
  const mine = triggerDraftStorageKey("a", "org-1");
  const mineOtherOrg = triggerDraftStorageKey("a", null);
  // "a.b" must not match the prefix of "a".
  const other = triggerDraftStorageKey("a.b", "org-1");
  const storage = memoryStorage({
    [mine]: "{}",
    [mineOtherOrg]: "{}",
    [other]: "{}",
    unrelated: "{}",
  });
  clearKeptTriggerDrafts("a", storage);
  expect(storage.keys().sort()).toEqual([other, "unrelated"].sort());
});

test("a fixed value that does not fit its field is reported on its step", () => {
  const document = sandboxDocumentFromDesign(configuredSandboxDesign);
  const recordTrigger = document.triggers[0]!;
  const condition = recordTrigger.conditionGroup.conditions[0]!;
  const requestNumber = document.design.modules
    .flatMap((module) => module.fields.map((field) => ({ module, field })))
    .find(({ field }) => field.name === "Request number")!;
  const incomplete = {
    ...recordTrigger,
    conditionGroup: {
      ...recordTrigger.conditionGroup,
      conditions: [
        {
          ...condition,
          field: {
            moduleId: requestNumber.module.id,
            fieldId: requestNumber.field.id,
          },
          value: { kind: "literal" as const, value: "" },
        },
      ],
    },
  };
  expect([...triggerStepErrors(incomplete, document.design)]).toEqual([
    [`condition:${condition.id}`, "Request number is required."],
  ]);
  expect([...triggerStepErrors(recordTrigger, document.design)]).toEqual([]);
});

test("a refused trigger save keeps the request's reference with the draft's words", () => {
  // S1-C4, D1.6 (docs/specs/system-health.md): the page's save failure keeps
  // the failed request's reference; a local failure has none (S1-C5).
  const reference = "019a4c2e-7b1d-7c3e-9f00-4f9c2e1a0b2c";
  const words =
    "The trigger change could not be saved. Your draft is still available.";
  expect(
    triggerSaveFailure(
      new SandboxCommandError(
        "This Sandbox change could not be saved.",
        reference,
      ),
    ),
  ).toEqual({ message: words, reference });
  expect(triggerSaveFailure(new Error("Sandbox is still loading."))).toEqual({
    message: words,
    reference: undefined,
  });
});

// Trigger drafts (docs/specs/sandbox-ux-redesign.md B1): a trigger may have
// empty parts while it is edited; kept edits use format 2, and Save checks
// in the browser before any request.

test(
  "kept edits are written as format 2 and keep a draft with empty parts",
  { tag: "@UX-C18" },
  () => {
    const document = sandboxDocumentFromDesign(configuredSandboxDesign);
    const key = triggerDraftStorageKey("user-1", "org-1");
    const storage = memoryStorage();
    const draft = defaultTrigger(document.design);
    const edits = [...document.triggers, draft];
    const base = JSON.stringify(document.triggers);

    writeKeptTriggerDraft(storage, key, { base, triggers: edits });
    expect(JSON.parse(storage.getItem(key)!)).toEqual({
      version: 2,
      base,
      triggers: edits,
    });
    // The incomplete trigger is not dropped: it reads back exactly.
    expect(readKeptTriggerDraft(storage, key, document)).toEqual({
      base,
      triggers: edits,
    });
  },
);

test(
  "the format 2 parser drops only a damaged record",
  { tag: "@UX-C18" },
  () => {
    const draft = defaultTrigger(
      sandboxDocumentFromDesign(configuredSandboxDesign).design,
    );
    const record = { version: 2, base: "[]", triggers: [draft] };
    expect(parseKeptTriggerDrafts(record)).toEqual({
      base: "[]",
      triggers: [draft],
    });
    const rows: Array<[string, unknown]> = [
      ["base is not a string", { ...record, base: 1 }],
      ["triggers is not a list", { ...record, triggers: {} }],
      ["a trigger has no id", { ...record, triggers: [{ ...draft, id: "" }] }],
      [
        "two triggers share an id",
        { ...record, triggers: [draft, { ...draft }] },
      ],
      [
        "an unknown event",
        { ...record, triggers: [{ ...draft, trigger: { kind: "boom" } }] },
      ],
      [
        "a condition without a field",
        {
          ...record,
          triggers: [
            {
              ...draft,
              conditionGroup: {
                operator: "all",
                conditions: [{ id: "c", operator: "=", value: null }],
              },
            },
          ],
        },
      ],
      [
        "an action list that is not a list",
        { ...record, triggers: [{ ...draft, actions: "none" }] },
      ],
      ["not an object", "text"],
    ];
    for (const [label, value] of rows)
      expect(parseKeptTriggerDrafts(value), label).toBeNull();
  },
);

test(
  "a kept part that no longer exists reads empty with its reason",
  { tag: "@UX-C18" },
  () => {
    const document = sandboxDocumentFromDesign(configuredSandboxDesign);
    const draft = {
      ...defaultTrigger(document.design),
      trigger: { kind: "record-created" as const, moduleId: "gone-module" },
    };
    const parsed = parseKeptTriggerDrafts({
      version: 2,
      base: "[]",
      triggers: [draft],
    });
    expect(triggerDraftGaps(parsed!.triggers[0]!, document.design)).toEqual([
      { step: "trigger", part: "module", reason: "No longer in the design." },
      { step: "actions", part: "actions", reason: "Add an action." },
    ]);
  },
);

test(
  "Save checks changed triggers first and names the first missing part",
  { tag: "@UX-C18" },
  () => {
    const document = sandboxDocumentFromDesign(configuredSandboxDesign);
    const saved = document.triggers[0]!;
    const first = defaultTrigger(document.design);
    const second = { ...defaultTrigger(document.design), name: "Second" };
    const drafts = [saved, first, second];

    expect(
      checkTriggerDrafts(
        drafts,
        document.design,
        new Set([first.id, second.id]),
      ),
    ).toEqual({
      ok: false,
      incomplete: {
        count: 2,
        triggerId: first.id,
        step: "trigger",
        part: "module",
        message: "2 triggers are incomplete; choose a module.",
      },
    });
    expect(
      checkTriggerDrafts([saved, first], document.design, new Set([first.id])),
    ).toMatchObject({
      ok: false,
      incomplete: {
        count: 1,
        message: "1 trigger is incomplete; choose a module.",
      },
    });
    // Complete drafts go out exactly as they are; an unchanged saved
    // trigger is not checked.
    expect(
      checkTriggerDrafts([saved], document.design, new Set<string>()),
    ).toEqual({ ok: true, triggers: [saved] });
  },
);
