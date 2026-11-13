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

// FX-SR-8: the search words in the address (`q` on the Search page, `search`
// in Files) belong to the account and organization that wrote or filled
// them. The tab remembers, per name, the owner of each recent value (S3-6:
// not only the latest), also across a reload, so a page opened for another
// account or organization drops the words instead of filling its field.
const ADDRESS_WORDS_KEY = "slateops-search-address-words";
/** Values kept per name; the oldest go first. */
const ADDRESS_WORDS_LIMIT = 50;
type AddressWordsName = "q" | "search";
/** Per name: [value, scope] pairs, oldest first; the last writer owns a value. */
type AddressWords = Record<AddressWordsName, [string, string][]>;

/** The stored record; an old one-entry shape or a broken value reads as empty. */
function readAddressWords(): AddressWords {
  const words: AddressWords = { q: [], search: [] };
  try {
    const parsed: unknown = JSON.parse(
      window.sessionStorage.getItem(ADDRESS_WORDS_KEY) ?? "{}",
    );
    if (typeof parsed !== "object" || parsed === null) return words;
    for (const name of ["q", "search"] as const) {
      const entries: unknown = (parsed as Record<string, unknown>)[name];
      if (!Array.isArray(entries)) continue;
      words[name] = entries
        .filter(
          (entry): entry is [string, string] =>
            Array.isArray(entry) &&
            entry.length === 2 &&
            typeof entry[0] === "string" &&
            typeof entry[1] === "string",
        )
        .slice(-ADDRESS_WORDS_LIMIT);
    }
  } catch {
    // A broken record reads as empty.
  }
  return words;
}

/** The scope of the search words: the verified account and organization. */
export function addressWordsScope(
  userId: string | null,
  organizationId: string | null,
): string {
  return `${userId ?? ""}:${organizationId ?? ""}`;
}

/** Records that `scope` wrote or filled these words. */
export function rememberAddressWords(
  name: AddressWordsName,
  scope: string,
  value: string,
): void {
  try {
    const words = readAddressWords();
    words[name] = [
      ...words[name].filter(([written]) => written !== value),
      [value, scope] as [string, string],
    ].slice(-ADDRESS_WORDS_LIMIT);
    window.sessionStorage.setItem(ADDRESS_WORDS_KEY, JSON.stringify(words));
  } catch {
    // Without storage the words stay unowned, as on a first visit.
  }
}

/** Whether another account or organization wrote or filled these words. */
export function addressWordsOfAnotherScope(
  name: AddressWordsName,
  scope: string,
  value: string,
): boolean {
  if (typeof window === "undefined") return false;
  const owner = readAddressWords()[name].find(([written]) => written === value);
  return owner !== undefined && owner[1] !== scope;
}

/**
 * Writes the settled words to the current Search page or Files address in
 * place (FX-SR-7, DR-4.8): the native history replace, which Next.js syncs
 * with `useSearchParams`, so no navigation starts. When a navigation has
 * already left the page, nothing is written, so it is never undone.
 */
export function replaceAddressWords(
  section: "search" | "files",
  name: AddressWordsName,
  value: string,
): void {
  const url = new URL(window.location.href);
  const current = url.searchParams.get("section");
  if (
    url.pathname !== "/platform" ||
    (section === "search"
      ? current !== null && current !== "search"
      : current !== "files") ||
    (url.searchParams.get(name) ?? "") === value
  )
    return;
  if (value) url.searchParams.set(name, value);
  else url.searchParams.delete(name);
  const query = url.searchParams.toString();
  window.history.replaceState(null, "", `/platform${query ? `?${query}` : ""}`);
}
