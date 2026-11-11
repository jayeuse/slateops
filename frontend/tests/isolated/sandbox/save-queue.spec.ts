import { expect, test } from "@playwright/test";
import {
  addedElementIds,
  classifyDesignChange,
  confirmQueuedSave,
  designAddHoldReason,
  idleSaveQueue,
  reduceSaveQueue,
  refusedDesignUpdate,
  saveQueueActive,
  saveQueueConflictDocument,
  saveQueueNeedsSend,
  saveQueueRequest,
  savingElementIds,
  type SandboxSaveQueue,
  type SandboxSaveQueueEvent,
} from "../../../src/components/systems/sandbox/state/save-queue";
import {
  openSandboxDocumentSession,
  proposedSandboxDocument,
  updateSandboxDocumentSession,
  type SandboxDocumentSession,
} from "../../../src/components/systems/sandbox/state/document-session";
import {
  redoSandboxCommand,
  undoSandboxCommand,
} from "../../../src/components/systems/sandbox/state/controller";
import type { SandboxDocumentResponse } from "../../../src/components/systems/sandbox/state/api";
import { SandboxCommandError } from "../../../src/components/systems/sandbox/state/commands";
import type { SandboxDocumentV4 } from "../../../src/components/systems/sandbox/domain/document";
import type { Design } from "../../../src/components/systems/sandbox/domain/model";
import { documentTextField } from "../../helpers/sandbox-fixtures";

// N1 save queue (docs/specs/sandbox-ux-redesign.md, rules 1 to 7): only
// Build adds are accepted while a save is in flight; everything else waits.

function run(
  events: SandboxSaveQueueEvent[],
  from: SandboxSaveQueue = idleSaveQueue,
): SandboxSaveQueue {
  return events.reduce(reduceSaveQueue, from);
}

function draft(): SandboxDocumentV4 {
  return {
    kind: "slateops-sandbox",
    schemaVersion: 4,
    design: {
      departments: [{ id: "operations", name: "Operations", closed: false }],
      modules: [
        {
          id: "requests",
          departmentId: "operations",
          name: "Requests",
          closed: false,
          titleFieldId: "title",
          fields: [documentTextField({ id: "title", name: "Title" })],
        },
      ],
      relationships: [],
      layout: {
        operations: { x: 0, y: 0, width: 360, height: 240 },
        requests: { x: 24, y: 48, width: 280, height: 160 },
      },
    },
    triggers: [
      {
        id: "notify",
        name: "Notify",
        enabled: true,
        priority: 0,
        trigger: { kind: "record-created", moduleId: "requests" },
        conditionGroup: { operator: "all", conditions: [] },
        actions: [
          { id: "notify-action", kind: "notification", message: "Created" },
        ],
      },
    ],
    scenarios: [],
  };
}

function response(
  revision: number,
  document: SandboxDocumentV4 = draft(),
): SandboxDocumentResponse {
  return {
    revision,
    contentHash: "a".repeat(64),
    byteCount: 256,
    issues: [],
    latestPublishedVersion: null,
    publishedHash: null,
    document,
  };
}

function withDepartment(design: Design, id: string, name: string): Design {
  return {
    ...design,
    departments: [...design.departments, { id, name, closed: false }],
  };
}

function addDepartment(
  session: SandboxDocumentSession,
  id: string,
  name: string,
): SandboxDocumentSession {
  return updateSandboxDocumentSession(
    session,
    withDepartment(session.history.present, id, name),
  );
}

// Q-1 (plan criterion)
test("an add during a save is accepted, queued and listed as saving", () => {
  const sending = run([{ type: "accept", ids: ["finance"] }, { type: "send" }]);
  expect(saveQueueNeedsSend(sending)).toBe(false);

  const queued = reduceSaveQueue(sending, { type: "accept", ids: ["legal"] });

  expect(saveQueueActive(queued)).toBe(true);
  // One request at a time: the queued add waits for the one in flight.
  expect(saveQueueNeedsSend(queued)).toBe(false);
  expect(savingElementIds(queued)).toEqual(["finance", "legal"]);
});

// Q-1 (plan criterion; D-Q1 add or edit split)
test("only appended Build elements count as an add", () => {
  const before = openSandboxDocumentSession(response(1)).history.present;
  const newField = {
    id: "due",
    name: "Due",
    type: "Date",
    required: false,
    value: "",
    options: "",
    closed: false,
  };
  const rows: Array<[string, Design, ReturnType<typeof classifyDesignChange>]> =
    [
      ["unchanged", before, { kind: "none" }],
      [
        "new department with its layout slot",
        {
          ...withDepartment(before, "finance", "Finance"),
          layout: {
            ...before.layout,
            finance: { x: 400, y: 0, width: 360, height: 240 },
          },
        },
        { kind: "add", ids: ["finance"] },
      ],
      [
        "new module",
        {
          ...before,
          modules: [
            ...before.modules,
            {
              id: "orders",
              department: "operations",
              name: "Orders",
              closed: false,
              fields: [],
              x: 0,
              y: 0,
            },
          ],
        },
        { kind: "add", ids: ["orders"] },
      ],
      [
        "new field in an existing module",
        {
          ...before,
          modules: before.modules.map((item) => ({
            ...item,
            fields: [...item.fields, newField],
          })),
        },
        { kind: "add", ids: ["due"] },
      ],
      [
        "new relationship",
        {
          ...before,
          relationships: [
            {
              id: "link",
              name: "Link",
              source: "requests",
              target: "requests",
              cardinality: "one-to-many",
              fieldMappings: [],
            },
          ],
        },
        { kind: "add", ids: ["link"] },
      ],
      [
        "rename",
        {
          ...before,
          departments: [{ id: "operations", name: "Ops", closed: false }],
        },
        { kind: "edit" },
      ],
      ["delete", { ...before, modules: [] }, { kind: "edit" }],
      [
        "existing element moved on the canvas",
        {
          ...before,
          layout: {
            ...before.layout,
            requests: { x: 99, y: 48, width: 280, height: 160 },
          },
        },
        { kind: "edit" },
      ],
      [
        "an add together with a rename",
        {
          ...withDepartment(before, "finance", "Finance"),
          departments: [
            { id: "operations", name: "Ops", closed: false },
            { id: "finance", name: "Finance", closed: false },
          ],
        },
        { kind: "edit" },
      ],
      [
        "trigger change",
        {
          ...before,
          rules: before.rules.map((rule) => ({ ...rule, enabled: false })),
        },
        { kind: "edit" },
      ],
    ];

  for (const [label, next, expected] of rows)
    expect(classifyDesignChange(before, next), label).toEqual(expected);
});

// Q-2 (plan criterion)
test("adds queued during one save leave together in the next request", () => {
  const confirmed = run([
    { type: "accept", ids: ["finance"] },
    { type: "send" },
    { type: "accept", ids: ["legal"] },
    { type: "accept", ids: ["audit"] },
    { type: "confirm" },
  ]);
  expect(saveQueueNeedsSend(confirmed)).toBe(true);
  expect(savingElementIds(confirmed)).toEqual(["legal", "audit"]);

  const second = reduceSaveQueue(confirmed, { type: "send" });
  expect(saveQueueNeedsSend(second)).toBe(false);
  expect(saveQueueActive(second)).toBe(true);

  const drained = reduceSaveQueue(second, { type: "confirm" });
  expect(saveQueueActive(drained)).toBe(false);
  expect(savingElementIds(drained)).toEqual([]);
});

// Q-2 (plan criterion)
test("the next request merges local adds onto the confirmed document and revision", () => {
  const opened = openSandboxDocumentSession(response(1));
  const sent = addDepartment(opened, "finance", "Finance");
  const local = addDepartment(sent, "legal", "Legal");
  // The server confirmed the first save and also normalized the trigger.
  const stored = proposedSandboxDocument(sent);
  stored.triggers = stored.triggers.map((item) => ({
    ...item,
    name: "Notify on create",
  }));

  const rebased = confirmQueuedSave(local, response(2, stored), true);
  const request = saveQueueRequest(rebased);

  expect(request.expectedRevision).toBe(2);
  expect(request.document.design.departments.map((item) => item.name)).toEqual([
    "Operations",
    "Finance",
    "Legal",
  ]);
  // The confirmed trigger is kept as stored, not rebuilt from the local rule.
  expect(request.document.triggers).toEqual(stored.triggers);
  // Each add stays its own Undo step.
  expect(rebased.history.past).toHaveLength(2);
});

// Q-2 (plan criterion)
test("with nothing queued the confirmed design replaces the local one", () => {
  const sent = addDepartment(
    openSandboxDocumentSession(response(1)),
    "finance",
    "Finance",
  );
  const stored = proposedSandboxDocument(sent);
  stored.design.departments[1] = {
    ...stored.design.departments[1]!,
    name: "Finance team",
  };

  const confirmed = confirmQueuedSave(sent, response(2, stored), false);

  expect(confirmed.revision).toBe(2);
  expect(confirmed.history.present.departments[1]?.name).toBe("Finance team");
  expect(confirmed.history.past).toHaveLength(1);
});

// Q-3 (plan criterion)
test("a failed save closes the queue and sends nothing more", () => {
  const failed = run([
    { type: "accept", ids: ["finance"] },
    { type: "send" },
    { type: "accept", ids: ["legal"] },
    { type: "fail" },
  ]);

  expect(saveQueueActive(failed)).toBe(false);
  expect(saveQueueNeedsSend(failed)).toBe(false);
  expect(savingElementIds(failed)).toEqual([]);
});

// Q-3 (plan criterion)
test("the conflict keeps the local design with its queued adds", () => {
  const sent = addDepartment(
    openSandboxDocumentSession(response(1)),
    "finance",
    "Finance",
  );
  const requestDocument = proposedSandboxDocument(sent);
  const local = addDepartment(sent, "legal", "Legal");

  const queued = saveQueueConflictDocument(local, requestDocument, true);
  expect(queued.design.departments.map((item) => item.name)).toEqual([
    "Operations",
    "Finance",
    "Legal",
  ]);
  expect(queued.triggers).toEqual(draft().triggers);
  // Nothing queued: the request body is the local design.
  expect(saveQueueConflictDocument(sent, requestDocument, false)).toBe(
    requestDocument,
  );
});

// Q-4 (plan criterion)
test("Undo and Redo during a save join the queue", () => {
  const opened = openSandboxDocumentSession(response(1));
  const added = addDepartment(opened, "finance", "Finance");
  const undone = undoSandboxCommand(added.history);
  const redone = redoSandboxCommand(undone);
  expect(addedElementIds(added.history.present, undone.present)).toEqual([]);
  expect(addedElementIds(undone.present, redone.present)).toEqual(["finance"]);

  const queue = run([
    { type: "accept", ids: ["finance"] },
    { type: "send" },
    { type: "accept", ids: [] },
    { type: "accept", ids: ["finance"] },
    { type: "confirm" },
  ]);
  expect(saveQueueNeedsSend(queue)).toBe(true);
});

// Q-5 (plan criterion)
test("the queue stays pending until the last queued change is confirmed", () => {
  const states = [
    { type: "accept", ids: ["finance"] },
    { type: "send" },
    { type: "accept", ids: ["legal"] },
    { type: "confirm" },
    { type: "send" },
    { type: "confirm" },
  ].reduce<boolean[]>(
    (seen, _event, index, events) => [
      ...seen,
      saveQueueActive(
        run(events.slice(0, index + 1) as SandboxSaveQueueEvent[]),
      ),
    ],
    [],
  );

  expect(states).toEqual([true, true, true, true, true, false]);
  expect(saveQueueActive(idleSaveQueue)).toBe(false);
});

// Q-6 (plan criterion)
test("a publish, lifecycle action or conflict refuses an add with today's words", () => {
  const hold = "Wait for the current Sandbox action to finish.";
  const none = {
    command: false,
    publication: false,
    lifecycle: false,
    conflict: false,
  };
  const rows: Array<[string, typeof none, string | null]> = [
    ["nothing holds", none, null],
    ["publish", { ...none, publication: true }, hold],
    ["lifecycle", { ...none, lifecycle: true }, hold],
    ["conflict", { ...none, conflict: true }, hold],
    ["another command", { ...none, command: true }, hold],
  ];

  for (const [label, flags, expected] of rows)
    expect(designAddHoldReason(flags), label).toBe(expected);
});

// A design rule an update checks refuses it with its own reason, even while
// a hold is on; any other failure under a hold reads as a save in flight,
// and without a hold it is thrown again (Software Architect N4, TASK-0049).
test("a refused update keeps its own reason under a hold", () => {
  const hold = "Wait for the current Sandbox action to finish.";
  const refusal = new SandboxCommandError(
    "A relationship between these modules already exists.",
  );
  expect(refusedDesignUpdate(refusal, hold)).toBe(
    "A relationship between these modules already exists.",
  );
  expect(refusedDesignUpdate(refusal, null)).toBe(
    "A relationship between these modules already exists.",
  );
  expect(refusedDesignUpdate(new Error("bug"), hold)).toBe(
    "A Sandbox change is already being saved.",
  );
  expect(() => refusedDesignUpdate(new Error("bug"), null)).toThrow("bug");
});
