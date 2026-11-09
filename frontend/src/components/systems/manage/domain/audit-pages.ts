/**
 * Audit pages by cursor (contract 2.3). Page 1 sends no cursor; page n + 1
 * sends the `next_cursor` of page n, so the page number is the stack depth
 * plus one. The stack belongs to one reader in one organization and one
 * request (filters, search, order, department, page size): for any other,
 * it is empty, so a cursor never crosses an account or an organization
 * (code review check 22) and a changed request starts at page 1.
 */
export type AuditPageReader = {
  userId: string;
  /** Null while the shell has not admitted an organization. */
  organizationId: string | null;
};

export type AuditPages = {
  reader: AuditPageReader | null;
  request: string;
  /** The cursor of each page after the first. */
  cursors: readonly string[];
};

export const emptyAuditPages: AuditPages = {
  reader: null,
  request: "",
  cursors: [],
};

function owns(
  pages: AuditPages,
  reader: AuditPageReader,
  request: string,
): boolean {
  return (
    pages.reader !== null &&
    pages.reader.userId === reader.userId &&
    pages.reader.organizationId === reader.organizationId &&
    pages.request === request
  );
}

/** The cursors of this reader's pages for this request; empty for others. */
export function auditPageCursors(
  pages: AuditPages,
  reader: AuditPageReader,
  request: string,
): readonly string[] {
  return owns(pages, reader, request) ? pages.cursors : [];
}

/** Next adds a page's `next_cursor`; page n keeps the first n - 1 cursors. */
export type AuditPageTurn =
  | { to: "next"; cursor: string }
  | { to: "previous" }
  | { to: "page"; index: number };

export function turnAuditPage(
  pages: AuditPages,
  reader: AuditPageReader,
  request: string,
  turn: AuditPageTurn,
): AuditPages {
  const cursors = auditPageCursors(pages, reader, request);
  return {
    reader,
    request,
    cursors:
      turn.to === "next"
        ? [...cursors, turn.cursor]
        : turn.to === "previous"
          ? cursors.slice(0, -1)
          : cursors.slice(0, Math.max(0, turn.index)),
  };
}
