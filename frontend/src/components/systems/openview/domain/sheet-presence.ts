// Sheet presence (docs/specs/sheets.md PR1-PR6, D13, D14): who has a sheet
// open now, and which cell each person is on. A person's state on the
// channel is a cell position and nothing else: no value, title or column
// name (PR2). What arrives is shown only for a current viewer, only its
// cell position is read, and nothing of it is rendered as text (D13).

/** The token lasts 60 s; it is renewed on the same channel before then. */
export const PRESENCE_REFRESH_MS = 45_000;
/**
 * Someone not on the token's viewer list renews it early, at most this
 * often: with the 45-second renewals, under the 12 a minute budget.
 */
export const PRESENCE_EARLY_RENEW_MS = 10_000;
/** A hidden tab keeps its place this long before it leaves the sheet. */
export const PRESENCE_GRACE_MS = 30_000;

export type PresenceCell = { rowId: string; columnKey: string };
export type PresencePeer = {
  userId: string;
  rowId: string | null;
  columnKey: string | null;
};
export type PresencePayload = {
  row_id: string | null;
  column_key: string | null;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const COLUMN_KEY = /^c[0-9a-z]{1,8}$/;

export function presencePayload(cell: PresenceCell | null): PresencePayload {
  return cell
    ? { row_id: cell.rowId, column_key: cell.columnKey }
    : { row_id: null, column_key: null };
}

/**
 * The cell in a tracked state: `row_id` and `column_key` only, each checked;
 * any other field is ignored. Bad or missing values mean no cell.
 */
function position(meta: unknown): PresencePayload {
  const none = { row_id: null, column_key: null };
  if (!meta || typeof meta !== "object" || Array.isArray(meta)) return none;
  const { row_id, column_key } = meta as Record<string, unknown>;
  return typeof row_id === "string" &&
    UUID.test(row_id) &&
    typeof column_key === "string" &&
    COLUMN_KEY.test(column_key)
    ? { row_id, column_key }
    : none;
}

/**
 * The people to show: each current viewer but this one, once (several tabs
 * give their latest state), in the channel's order. Anyone not on the
 * viewer list is not shown; nothing but a cell position is read.
 */
export function acceptedPeers(
  state: Record<string, unknown[]>,
  viewers: ReadonlySet<string>,
  selfId: string,
): PresencePeer[] {
  const peers: PresencePeer[] = [];
  for (const [userId, metas] of Object.entries(state)) {
    if (userId === selfId || !viewers.has(userId) || !Array.isArray(metas))
      continue;
    if (metas.length === 0) continue;
    const latest = position(metas[metas.length - 1]);
    peers.push({
      userId,
      rowId: latest.row_id,
      columnKey: latest.column_key,
    });
  }
  return peers;
}

// The five chart colours. `--chart-2` alone is under 3:1 on light cards, so
// its line takes some ink, as the Boards gantt bars do.
const COLOURS = [
  "var(--chart-1)",
  "color-mix(in oklab, var(--chart-2) 80%, var(--ink))",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
] as const;

/** A person's colour: their avatar ring and their cell outline. */
export function presenceColor(userId: string): string {
  let hash = 0;
  for (const character of userId)
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return COLOURS[hash % COLOURS.length];
}

/**
 * The grid cells to outline (PR2), `<row index>:<column key>` to a colour:
 * a person on a loaded row, in a column of this sheet. The colour comes from
 * the fixed set; nothing from the channel is written as text.
 */
export function presenceOutlines(
  peers: PresencePeer[],
  rowIndexOf: (rowId: string) => number,
  columnKeys: ReadonlySet<string>,
): Map<string, string> {
  const outlines = new Map<string, string>();
  for (const peer of peers) {
    if (!peer.rowId || !peer.columnKey || !columnKeys.has(peer.columnKey))
      continue;
    const index = rowIndexOf(peer.rowId);
    if (!Number.isSafeInteger(index) || index < 0) continue;
    outlines.set(`${index}:${peer.columnKey}`, presenceColor(peer.userId));
  }
  return outlines;
}
