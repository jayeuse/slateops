import { expect, test } from "@playwright/test";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { Design } from "../../../src/components/systems/sandbox/domain/model";
import { bindSandboxHistoryAccess } from "../../../src/components/systems/sandbox/state/sandbox-history-access";
import {
  latestPublishedVersionOptions,
  publishedFieldTypes,
  useLatestPublishedVersion,
  type PublishedFieldType,
} from "../../../src/components/systems/sandbox/state/use-latest-published-version";
import { installFetch } from "../helpers/fake-fetch";
import {
  configuredSandboxDesign,
  sandboxDocumentFromDesign,
} from "../../helpers/sandbox-fixtures";

// Build reads the latest published version once per version (FAST-5) and
// looks a field up by its published identity, the pair (module id, field id).

const first = "00000000-0000-4000-8000-000000000001";
const second = "00000000-0000-4000-8000-000000000002";

/** Service requests and Equipment both hold a field `sample-field-Status`;
 * here only Equipment's is published as Number. */
function publishedDesign(): Design {
  const design = structuredClone(configuredSandboxDesign);
  const status = design.modules
    .find((item) => item.id === "sample-equipment")
    ?.fields.find((field) => field.id === "sample-field-Status");
  if (!status) throw new Error("Equipment needs its Status field");
  status.type = "Number";
  status.options = "";
  return design;
}

function versionDetail(id: string) {
  return {
    id,
    sequence: 3,
    kind: "published",
    label: "Published 3",
    note: null,
    sourceDocumentRevision: 4,
    sourceVersionId: null,
    contentHash: "c".repeat(64),
    byteCount: 321,
    metadataRevision: 1,
    createdAt: "2026-11-10T10:00:00Z",
    performedBy: null,
    isDeleted: false,
    deletedAt: null,
    document: sandboxDocumentFromDesign(publishedDesign()),
  };
}

/** The lookup Build gets from the hook, rendered once from this cache. */
function lookupFrom(
  client: QueryClient,
  versionId: string | null,
): PublishedFieldType | null {
  let seen: PublishedFieldType | null | undefined;
  function Probe() {
    seen = useLatestPublishedVersion(versionId);
    return null;
  }
  renderToStaticMarkup(
    createElement(QueryClientProvider, { client }, createElement(Probe)),
  );
  if (seen === undefined) throw new Error("The hook was not rendered");
  return seen;
}

test.beforeEach(() => {
  bindSandboxHistoryAccess(new QueryClient());
});

// UX-C11: a field matches on (module id, field id), not on the field id alone.
test("a published field is found by its module and field ids together", () => {
  const typeOf = publishedFieldTypes(
    sandboxDocumentFromDesign(publishedDesign()),
  );
  expect(typeOf("sample-equipment", "sample-field-Status")).toBe("Number");
  expect(typeOf("sample-requests", "sample-field-Status")).toBe("Select");
});

// UX-C11: no notice when the latest version lacks the pair.
test("a field the latest published version does not have has no published type", () => {
  const typeOf = publishedFieldTypes(
    sandboxDocumentFromDesign(publishedDesign()),
  );
  expect(typeOf("sample-requests", "sample-field-Title")).toBe("Text");
  expect(typeOf("sample-equipment", "sample-field-Title")).toBeNull();
  expect(typeOf("sample-missing", "sample-field-Status")).toBeNull();
});

// UX-C11: no notice with no published version, and no read either.
test("with no published version Build has no published types and reads nothing", () => {
  const mock = installFetch(() => Response.json(versionDetail(first)));
  try {
    expect(lookupFrom(new QueryClient(), null)).toBeNull();
    expect(mock.requests).toHaveLength(0);
  } finally {
    mock.restore();
  }
});

// UX-C11: the read version gives Build its field types.
test("a read published version gives Build each field's published type", async () => {
  const client = new QueryClient();
  const mock = installFetch(() => Response.json(versionDetail(first)));
  try {
    await client.fetchQuery(latestPublishedVersionOptions(first));
    const typeOf = lookupFrom(client, first);
    expect(typeOf?.("sample-equipment", "sample-field-Status")).toBe("Number");
    expect(String(mock.requests[0]?.input)).toContain(
      `/sandbox/versions/${first}`,
    );
  } finally {
    mock.restore();
  }
});

// UX-C11: a failed read shows no notice; the publish blocker decides.
test("a refused published version read leaves Build with no published types", async () => {
  const client = new QueryClient();
  const mock = installFetch(() =>
    Response.json({ detail: "Refused" }, { status: 403 }),
  );
  try {
    await expect(
      client.fetchQuery(latestPublishedVersionOptions(first)),
    ).rejects.toThrow();
    expect(lookupFrom(client, first)).toBeNull();
  } finally {
    mock.restore();
  }
});

// UX-C11: one read per published version, kept until a newer one.
test("each published version is read once and kept until a newer one is published", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { staleTime: 30_000, gcTime: 300_000 } },
  });
  const mock = installFetch((input) => {
    const id = String(input).split("/").at(-1) ?? "";
    return Response.json(versionDetail(id));
  });
  try {
    await client.fetchQuery(latestPublishedVersionOptions(first));
    // Build remounts on every selection; a later visit must not read again.
    const later = Date.now() + 60 * 60_000;
    const now = Date.now;
    Date.now = () => later;
    try {
      await client.fetchQuery(latestPublishedVersionOptions(first));
    } finally {
      Date.now = now;
    }
    expect(mock.requests).toHaveLength(1);

    await client.fetchQuery(latestPublishedVersionOptions(second));
    expect(mock.requests).toHaveLength(2);
    expect(String(mock.requests[1]?.input)).toContain(
      `/sandbox/versions/${second}`,
    );
  } finally {
    mock.restore();
  }
});

// NB-3 (Software Architect review, PR4): a version that nothing shows any
// more leaves the cache on the client's normal schedule, so older published
// versions do not stay in memory for the whole session.
test("a published version read is let go once nothing shows it", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { gcTime: 1 } },
  });
  const mock = installFetch((input) => {
    const id = String(input).split("/").at(-1) ?? "";
    return Response.json(versionDetail(id));
  });
  try {
    const options = latestPublishedVersionOptions(first);
    const removed = new Promise<boolean>((resolve) => {
      // A hang guard well above the 1 ms collection, not a wait for it.
      const guard = setTimeout(() => resolve(false), 2_000);
      client.getQueryCache().subscribe((event) => {
        if (event.type === "removed") {
          clearTimeout(guard);
          resolve(true);
        }
      });
    });
    await client.fetchQuery(options);
    expect(await removed).toBe(true);
    expect(client.getQueryData(options.queryKey)).toBeUndefined();
  } finally {
    mock.restore();
  }
});
