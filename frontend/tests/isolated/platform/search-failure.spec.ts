import { expect, test } from "@playwright/test";

import { ApiError } from "../../../src/lib/api";
import { isSearchAdmissionError } from "../../../src/components/systems/platform/helpers/search-failure";

// An admission refusal on any search card asks the shell to check the
// session. Every failed card says "<Kind> could not be searched." with Try
// again (docs/specs/ux-friction-pass.md DR-4.8); the http journeys "Search
// ignores old replies, hides denial and recovers with explicit retry" and
// "UF-C4.5 Messages and Files cards …" own those words.

const admissionRows: { name: string; error: unknown; denied: boolean }[] = [
  {
    name: "mfa_required",
    error: new ApiError(403, "Private detail", undefined, "mfa_required"),
    denied: true,
  },
  {
    name: "ip_not_allowed",
    error: new ApiError(403, "Private detail", undefined, "ip_not_allowed"),
    denied: true,
  },
  { name: "a plain 403", error: new ApiError(403, "Denied"), denied: false },
  { name: "a 401", error: new ApiError(401, "Expired"), denied: false },
  { name: "no error", error: null, denied: false },
  {
    name: "an object that only looks like an API error",
    error: { status: 403, code: "mfa_required" },
    denied: false,
  },
];

for (const row of admissionRows)
  test(`search admission: ${row.name} ${row.denied ? "asks" : "does not ask"} the session check`, () => {
    expect(isSearchAdmissionError(row.error)).toBe(row.denied);
  });
