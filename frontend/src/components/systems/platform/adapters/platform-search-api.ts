import type { Route } from "next";
import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";
import { apiFetch, apiContractError } from "@/lib/api";
import { pageEndsWithinTotal, wirePageCounts } from "@/lib/list-pagination";

/** Every kind `/api/search` reads. */
export const SEARCH_KINDS = [
  "record",
  "person",
  "post",
  "event",
  "file",
] as const;
export type SearchKind = (typeof SEARCH_KINDS)[number];
export type PlatformSearchKind = SearchKind;
// The one destination id each kind carries: module, Board, or department.
const DESTINATION_ID: Record<PlatformSearchKind, number | null> = {
  record: 0,
  person: null,
  post: 1,
  event: 1,
  file: 2,
};
const itemSchema = z
  .object({
    kind: z.enum(SEARCH_KINDS),
    id: z.uuid(),
    title: z.string(),
    context_label: z.string(),
    module_id: z.uuid().nullable(),
    board_id: z.uuid().nullable(),
    department_id: z.uuid().nullable(),
    can_open: z.boolean(),
  })
  .strict()
  .refine((item) =>
    [item.module_id, item.board_id, item.department_id].every(
      (id, index) => (id !== null) === (index === DESTINATION_ID[item.kind]),
    ),
  );
const pageSchema = z
  .object({
    items: z.array(itemSchema),
    pagination: z
      .object({
        limit: z.number().int().min(1).max(100),
        offset: z.number().int().nonnegative(),
        count: z.number().int().nonnegative(),
        total: z.number().int().nonnegative(),
        has_more: z.boolean(),
        total_is_capped: z.boolean(),
      })
      .strict(),
  })
  .strict();
export type PlatformSearchItem = z.output<typeof itemSchema>;
export async function readPlatformSearch(
  search: string,
  kind: PlatformSearchKind,
  offset: number,
  signal?: AbortSignal,
  limit = 10,
) {
  const params = new URLSearchParams({
    search,
    kind,
    limit: String(limit),
    offset: String(offset),
    sort_by: "relevance",
    sort_order: "desc",
    deleted: "exclude",
  });
  const page = await apiFetch(`/search?${params}`, pageSchema, {
    signal,
    cache: "no-store",
  });
  if (
    page.items.some((item) => item.kind !== kind) ||
    page.pagination.limit !== limit ||
    page.pagination.offset !== offset ||
    page.pagination.count !== page.items.length ||
    page.items.length > limit ||
    (page.items.length > 0 &&
      !pageEndsWithinTotal(wirePageCounts(page.pagination)))
  )
    throw apiContractError(page);
  return page;
}
export const platformSearchOptions = (
  search: string,
  kind: PlatformSearchKind,
  offset: number,
  limit = 10,
) =>
  queryOptions({
    queryKey: ["platform", "search", { search, kind, offset, limit }],
    enabled: search.length > 0 && search.length <= 100,
    queryFn: ({ signal }) =>
      readPlatformSearch(search, kind, offset, signal, limit),
  });
export function searchDestination(item: PlatformSearchItem): Route | null {
  if (!item.can_open) return null;
  const id = encodeURIComponent(item.id);
  switch (item.kind) {
    case "record":
      return `/openview?section=views&module=${encodeURIComponent(item.module_id!)}&record=${id}` as Route;
    case "person":
      return `/access?view=people&user=${id}` as Route;
    case "post":
      return `/boards?board=${encodeURIComponent(item.board_id!)}&section=posts&post=${id}` as Route;
    case "event":
      return `/boards?board=${encodeURIComponent(item.board_id!)}&section=calendar&event=${id}` as Route;
    case "file":
      return `/platform?section=files&department=${encodeURIComponent(item.department_id!)}&search=${encodeURIComponent(item.title)}` as Route;
  }
}
