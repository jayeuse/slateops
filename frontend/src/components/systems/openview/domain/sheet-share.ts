import type {
  WorksheetDetail,
  WorksheetShare,
} from "../adapters/worksheets-api";

// Who may do what on a sheet's page, and the words that explain sharing and
// the open state (docs/specs/sheets.md V5, V8, L7, L10; Screens 3 to 5).

/** The viewer's part: an open sheet is read-only to everyone (L2). */
export type SheetRole = "open" | "owner" | "edit" | "view";

export type SheetActions = {
  share: boolean;
  rename: boolean;
  remove: boolean;
  history: boolean;
  export: boolean;
};

export function sheetRole(
  sheet: Pick<WorksheetDetail, "state" | "myLevel">,
): SheetRole {
  return sheet.state === "open" ? "open" : sheet.myLevel;
}

export function sheetActions(role: SheetRole): SheetActions {
  const owner = role === "owner";
  // Anyone who can see a sheet reads its history and exports it (H3, X2).
  return {
    share: owner,
    rename: owner,
    remove: owner,
    history: true,
    export: true,
  };
}

function counted(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`;
}

/** The owner's access chip: who the sheet is shared with. */
export function sharedWithWords(shares: readonly WorksheetShare[]): string {
  const people = shares.filter((share) => share.subject === "user").length;
  const groups = shares.length - people;
  const parts = [
    people ? counted(people, "person", "people") : null,
    groups ? counted(groups, "group", "groups") : null,
  ].filter(Boolean);
  return parts.length ? `Shared with ${parts.join(" and ")}` : "Only you";
}

type Place = Pick<WorksheetDetail, "recordId" | "anchorTitle" | "moduleName">;

/** What a reader must be able to read: the record, or a module sheet's module. */
function readable(sheet: Place) {
  return sheet.recordId
    ? `${sheet.anchorTitle}'s record`
    : `the ${sheet.moduleName} module`;
}

/** The two lines under the Share dialog's list (V4, V8). */
export function shareLines(
  sheet: Place,
  organization: string,
): [string, string] {
  return [
    `People see this sheet only while they can read ${readable(sheet)}.`,
    `If you leave ${organization}, this sheet opens read-only to everyone who can read ${readable(sheet)}.`,
  ];
}

/** The line under an open sheet's title (L10, Decision 10: no date). */
export function openLine(
  sheet: Place & Pick<WorksheetDetail, "owner">,
  organization: string,
): string {
  return `${sheet.owner.displayName} no longer has access to ${organization}. Everyone who can read ${readable(sheet)} can read this sheet. Nobody can change it.`;
}

/** The line under a share target (Screens 4): a group's size, or a guest. */
export function shareTargetWords(
  target: { memberCount: number } | { isGuest: boolean },
): string | null {
  if ("memberCount" in target)
    return `Group · ${target.memberCount} ${target.memberCount === 1 ? "person" : "people"}`;
  return target.isGuest ? "Guest · View only" : null;
}
