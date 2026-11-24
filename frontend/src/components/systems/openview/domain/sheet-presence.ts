import { personInitials } from "@/components/person-avatar";

// Sheet presence (docs/specs/sheets.md PR1-PR6, D13, D14): who has a sheet
// open now, and which cell each person is on. A person's state on the
// channel is a cell position and nothing else: no value, title or column
// name (PR2). What arrives is shown only for a current viewer, only its
// cell position is read, and nothing of it is rendered as text (D13).

/** The token lasts 60 s; it is renewed on the same channel before then. */
export const PRESENCE_REFRESH_MS = 45_000;
/**
 * Someone not on the token's viewer list renews it early, at most this
 * often (and twice a minute; see the adapter).
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

// Four chart colours: not `--chart-1`, whose blue reads as the focus outline
// (Product Designer, F9-B1). `--chart-2` alone is under 3:1 on light cards,
// so its line takes some ink, as the Boards gantt bars do.
const COLOURS = [
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

/** One person's ring on a cell: their colour, and who it is. */
export type PresenceMark = { color: string; initials: string; name: string };

/**
 * The grid cells to ring (PR2), `<row index>:<column key>` to the people on
 * it, in the channel's order: a person on a loaded row, in a column of this
 * sheet. Names come from the person cards the viewer reads (`nameOf`), never
 * from the channel; a name not read yet shows as "?".
 */
export function presenceOutlines(
  peers: PresencePeer[],
  rowIndexOf: (rowId: string) => number,
  columnKeys: ReadonlySet<string>,
  nameOf: (userId: string) => string | undefined,
): Map<string, PresenceMark[]> {
  const outlines = new Map<string, PresenceMark[]>();
  for (const peer of peers) {
    if (!peer.rowId || !peer.columnKey || !columnKeys.has(peer.columnKey))
      continue;
    const index = rowIndexOf(peer.rowId);
    if (!Number.isSafeInteger(index) || index < 0) continue;
    const name = nameOf(peer.userId);
    const key = `${index}:${peer.columnKey}`;
    outlines.set(key, [
      ...(outlines.get(key) ?? []),
      {
        color: presenceColor(peer.userId),
        initials: name ? personInitials(name) : "?",
        name: name ?? "Someone on this sheet",
      },
    ]);
  }
  return outlines;
}

/** People not admitted by a newer token, kept so they ask no more. */
const REFUSED_KEPT = 50;

/** Remembers a person not admitted; once 50 are kept, no more are added. */
export function rememberRefused(refused: Set<string>, userId: string) {
  if (refused.size < REFUSED_KEPT) refused.add(userId);
}
