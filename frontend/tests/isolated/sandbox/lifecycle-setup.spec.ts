import { expect, test } from "@playwright/test";
import type { LifecycleDerivedChange } from "../../../src/lib/api";
import {
  lifecycleClosePreviewSchema,
  lifecyclePurgePreviewSchema,
  lifecyclePurgeResultSchema,
} from "../../../src/lib/lifecycle";
import { LifecyclePurgeReview } from "../../../src/components/systems/shared/lifecycle-purge-review";
import {
  LifecycleChannelChanges,
  lifecycleDoneNotice,
} from "../../../src/components/systems/sandbox/components/lifecycle-dialog";
import { staticMarkup } from "./static-markup";

const departmentId = "00000000-0000-4000-8000-000000000010";
const actorId = "00000000-0000-4000-8000-000000000001";
const channelId = (index: number) =>
  `00000000-0000-4000-8000-${String(100 + index).padStart(12, "0")}`;

function impact(
  operation: "close" | "reopen" | "purge",
  overrides: Record<string, unknown> = {},
) {
  return {
    target_type: "department",
    target_id: departmentId,
    operation,
    actor_id: actorId,
    rows: [],
    external_impacts: [],
    key_strips: [],
    blockers: [],
    derived_changes: [],
    impact_digest: "d".repeat(64),
    ...overrides,
  };
}

const archived: LifecycleDerivedChange = {
  role: "channel",
  target_id: channelId(0),
  name: "Sales",
  action: "close",
};
const staysOpen = (index: number, name: string): LifecycleDerivedChange => ({
  role: "channel",
  target_id: channelId(index),
  name,
  action: "keep",
});

function text(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function channelRows(changes: LifecycleDerivedChange[]): string[] {
  const html = staticMarkup(LifecycleChannelChanges, { changes });
  return html
    .split("<li")
    .slice(1)
    .map((row) => text(`<li${row}`));
}

// SD-C32 (contributor), BE-SD7, DQ1 (a): the close preview carries the
// setup channel's archive and the department's other channels as "keep";
// a reopen result carries the unarchive; an unknown action is refused.
test("lifecycle impacts parse the setup channel changes", () => {
  const preview = {
    impact: impact("close", {
      derived_changes: [archived, staysOpen(1, "Sales leads")],
    }),
    token: "close-token",
    expires_at: "2027-10-01T00:00:00Z",
    confirmation_name: "Sales",
  };
  expect(lifecycleClosePreviewSchema.parse(preview)).toEqual(preview);
  const reopened = {
    impact: impact("reopen", {
      derived_changes: [{ ...archived, action: "reopen" }],
    }),
    operation_id: null,
  };
  expect(lifecyclePurgeResultSchema.parse(reopened)).toEqual(reopened);
  expect(
    lifecyclePurgeResultSchema.safeParse({
      ...reopened,
      impact: impact("reopen", {
        derived_changes: [{ ...archived, action: "delete" }],
      }),
    }).success,
  ).toBe(false);
  // Every impact carries the list, empty when nothing is derived.
  const withoutList: Record<string, unknown> = impact("reopen");
  delete withoutList.derived_changes;
  expect(
    lifecyclePurgeResultSchema.safeParse({
      impact: withoutList,
      operation_id: null,
    }).success,
  ).toBe(false);
});

// L1 (SD-C32): the archive row first, then each other channel with
// "Stays open", and the note under the heading.
test("a close preview lists the archived channel, then the channels that stay open", () => {
  const html = staticMarkup(LifecycleChannelChanges, {
    changes: [
      staysOpen(1, "Sales leads"),
      archived,
      staysOpen(2, "Sales escalations"),
    ],
  });
  expect(text(html)).toBe(
    "Channels Administrators and people given access can still post in open channels. Archived Sales Stays open Sales leads Stays open Sales escalations",
  );
});

// L2 and L3 (SD-C32, SD-C13): no note without a "Stays open" row; only
// "Stays open" rows when a person already archived the setup channel; no
// block when the department has no channels.
test("the channels block shows the note only with open channels, and hides when empty", () => {
  const archiveOnly = staticMarkup(LifecycleChannelChanges, {
    changes: [archived],
  });
  expect(text(archiveOnly)).toBe("Channels Archived Sales");
  expect(channelRows([staysOpen(1, "Sales leads")])).toEqual([
    "Stays open Sales leads",
  ]);
  expect(
    staticMarkup(LifecycleChannelChanges, {
      changes: [staysOpen(1, "Sales leads")],
    }),
  ).toContain("can still post in open channels.");
  expect(staticMarkup(LifecycleChannelChanges, { changes: [] })).toBe("");
});

// L1, long lists: more than five rows show five and a "Show all" control.
test("a close preview with many channels shows five and offers the rest", () => {
  const changes = [
    archived,
    ...Array.from({ length: 11 }, (_, index) =>
      staysOpen(index + 1, `Sales ${index + 1}`),
    ),
  ];
  const html = staticMarkup(LifecycleChannelChanges, { changes });
  expect(channelRows(changes)).toHaveLength(5);
  expect(text(html)).toContain("Show all 12 channels");
});

// L4 (SD-C12, lifecycle path; DQ2 (a)): the reopen notice names the restored
// channel; every other result keeps the plain notice.
test("the lifecycle notice names a channel that a reopen restored", () => {
  const result = (
    operation: "close" | "reopen",
    changes: LifecycleDerivedChange[],
  ) =>
    lifecyclePurgeResultSchema.parse({
      impact: impact(operation, { derived_changes: changes }),
      operation_id: null,
    });
  expect(
    lifecycleDoneNotice(result("reopen", [{ ...archived, action: "reopen" }])),
  ).toBe("Live change confirmed · Channel Sales restored");
  expect(lifecycleDoneNotice(result("reopen", []))).toBe(
    "Live change confirmed",
  );
  expect(lifecycleDoneNotice(result("close", [archived]))).toBe(
    "Live change confirmed",
  );
});

function purgePreview(overrides: Record<string, unknown>) {
  return lifecyclePurgePreviewSchema.parse({
    impact: impact("purge", overrides),
    token: "purge-token",
    expires_at: "2027-10-01T00:00:00Z",
    confirmation_name: "Sales",
    last_successful_backup_at: null,
  });
}

function blocker(code: string, detail: string) {
  return {
    code,
    entity_type: "departments",
    entity_id: departmentId,
    detail,
    conflicting_entity_type: null,
    conflicting_entity_id: null,
    field_id: null,
    field_name: null,
    module_id: null,
    module_name: null,
    department_id: departmentId,
    department_name: "Sales",
  };
}

// P1 (SD-C17, contributor): the client parses the OpenComms blocker and shows
// its detail without the "Resolve these dependencies" line, which other
// blockers still get.
test("a purge preview blocked by OpenComms content parses and shows no fix line", () => {
  const comms = blocker(
    "comms_department_content",
    "Sales has 1 category and 2 channels in OpenComms, so it stays closed",
  );
  const onlyComms = staticMarkup(LifecyclePurgeReview, {
    preview: purgePreview({ blockers: [comms] }),
  });
  expect(text(onlyComms)).toContain(
    "Delete forever is blocked Sales has 1 category and 2 channels in OpenComms, so it stays closed",
  );
  expect(onlyComms).not.toContain("Resolve these dependencies");
  const mixed = staticMarkup(LifecyclePurgeReview, {
    preview: purgePreview({
      blockers: [
        comms,
        blocker("purge_board_dependency", "Remove the Board link first."),
      ],
    }),
  });
  expect(mixed).toContain("Resolve these dependencies, then review again.");
});

// P2: setup link rows of the purge impact are counted by name.
test("a purge preview counts setup links", () => {
  const row = (entity_type: string, index: number) => ({
    entity_type,
    entity_id: channelId(index),
    is_deleted: true,
    deleted_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    state_fingerprint: "owned-live-state",
  });
  const html = staticMarkup(LifecyclePurgeReview, {
    preview: purgePreview({
      rows: [
        row("boards", 0),
        row("sandbox_bindings", 1),
        ...Array.from({ length: 6 }, (_, index) =>
          row("sandbox_derived_objects", index + 2),
        ),
      ],
    }),
  });
  expect(text(html)).toContain(
    "This deletes 1 Board, 1 design binding, and 6 setup links forever.",
  );
});
