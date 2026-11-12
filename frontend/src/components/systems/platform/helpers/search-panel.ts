import type { Route } from "next";
import type { SearchHit } from "@/components/systems/comms/contract/types";
import { listTotalText } from "@/lib/list-pagination";
import {
  searchDestination,
  type PlatformSearchItem,
  type PlatformSearchKind,
} from "../adapters/platform-search-api";

// Rules of the header search panel (docs/specs/ux-friction-pass.md DR-4.3 to
// DR-4.7). The panel component owns the reads and the screen.

/** Each group reads and lists at most this many rows. */
export const PANEL_LIMIT = 5;

export type PanelGroupKind = PlatformSearchKind | "message";
/** The groups in their fixed order, with their headings. */
export const PANEL_GROUPS: readonly { kind: PanelGroupKind; title: string }[] =
  [
    { kind: "record", title: "Records" },
    { kind: "person", title: "People" },
    { kind: "post", title: "Posts" },
    { kind: "event", title: "Events" },
    { kind: "message", title: "Messages" },
    { kind: "file", title: "Files" },
  ];
export const PANEL_SCOPE = PANEL_GROUPS.map((group) => group.title).join(" · ");

export type ExcerptPart = { text: string; marked: boolean };
export type PanelRow = {
  /** Unique across groups; also the row's element id. */
  id: string;
  title: string;
  context: string;
  /** Null when the reader cannot open the result: the row is plain text. */
  href: Route | null;
  /** Message rows only: the excerpt with its matched words marked. */
  excerpt?: ExcerptPart[];
};

/** "Records · 12"; a capped total reads "1,000+". */
export function groupHeading(
  title: string,
  total: number,
  capped: boolean,
): string {
  return `${title} · ${listTotalText(total, capped)}`;
}

export function platformRows(items: readonly PlatformSearchItem[]): PanelRow[] {
  return items.slice(0, PANEL_LIMIT).map((item) => ({
    id: `${item.kind}-${item.id}`,
    title: item.title,
    context: item.context_label,
    href: searchDestination(item),
  }));
}

/** A message opens at itself in OpenComms (notification link format). */
export function messageRows(
  hits: readonly SearchHit[],
  formatDate: (value: string) => string,
): PanelRow[] {
  return hits.slice(0, PANEL_LIMIT).map((hit) => ({
    id: `message-${hit.message_id}`,
    title: hit.excerpt,
    context: `${hit.conversation_name} · ${hit.author_name} · ${formatDate(hit.created_at)}`,
    href: `/comms?conversation=${encodeURIComponent(hit.conversation_id)}&message=${encodeURIComponent(hit.message_id)}` as Route,
    excerpt: excerptParts(hit.excerpt, hit.matches),
  }));
}

/** Splits an excerpt at its match spans, which count code points, not UTF-16 units. */
export function excerptParts(
  excerpt: string,
  matches: SearchHit["matches"],
): ExcerptPart[] {
  const points = [...excerpt];
  const parts: ExcerptPart[] = [];
  let at = 0;
  for (const { start, end } of [...matches].sort((a, b) => a.start - b.start)) {
    // An overlapping span extends the mark before it.
    const from = Math.max(start, at);
    if (end <= from) continue;
    if (from > at)
      parts.push({ text: points.slice(at, from).join(""), marked: false });
    const last = parts[parts.length - 1];
    const text = points.slice(from, end).join("");
    if (from === at && last?.marked) last.text += text;
    else parts.push({ text, marked: true });
    at = end;
  }
  if (at < points.length)
    parts.push({ text: points.slice(at).join(""), marked: false });
  return parts;
}

/** The rows that open, in group order: the rows the arrow keys move over. */
export function activeOrder(groups: readonly PanelRow[][]): string[] {
  return groups.flatMap((rows) =>
    rows.filter((row) => row.href !== null).map((row) => row.id),
  );
}

/** The next active row; it wraps at either end. */
export function moveActive(
  order: readonly string[],
  current: string | null,
  step: 1 | -1,
): string | null {
  if (!order.length) return null;
  const index = current === null ? -1 : order.indexOf(current);
  if (index === -1) return step === 1 ? order[0] : order[order.length - 1];
  return order[(index + step + order.length) % order.length];
}

/** The Search page with the typed words (DR-4.8). */
export function showAllHref(text: string): Route {
  return `/platform?section=search&q=${encodeURIComponent(text)}` as Route;
}
