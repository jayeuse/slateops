import { expect, test } from "@playwright/test";

import { ApiError } from "../../../src/lib/api";
import { setPersonTemporaryPassword } from "../../../src/components/systems/access/adapters/security-api";
import { temporaryPasswordFailure } from "../../../src/components/systems/access/helpers/person-security-outcome";
import { ids, installCsrfCookie, installFetch } from "./fixtures";

// Generated per run, so no literal secret sits in the repository (secret scan).
const TEMPORARY_PASSWORD = `Tp${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;

// DEC-0042: an administrator sets a temporary password for a person. The
// server chooses one when the body has none and shows it once; a typed one is
// sent as typed and never comes back. Each refusal code has its own words;
// the http journey keeps one generated, one typed and one refusal.

const answer = (password: string | null) => ({
  operation_id: "00000000-0000-4000-8000-000000000911",
  user_id: ids.guest,
  temporary_password: password,
  local_revocation: "committed",
  revoked_sessions: 2,
});

test("AC-T-UI a temporary password posts the typed password or none, and reads the server's password once", async () => {
  const restoreCookie = installCsrfCookie("security-token");
  let reply = answer(TEMPORARY_PASSWORD);
  const mock = installFetch(() => Response.json(reply));
  try {
    await expect(
      setPersonTemporaryPassword(ids.guest, null),
    ).resolves.toMatchObject({ temporary_password: TEMPORARY_PASSWORD });
    reply = answer(null);
    await expect(
      setPersonTemporaryPassword(ids.guest, "a typed temporary one"),
    ).resolves.toMatchObject({ temporary_password: null });
    expect(
      mock.requests.map(({ input, init }) => [
        String(input),
        init?.method,
        JSON.parse(String(init?.body)),
      ]),
    ).toEqual([
      [`/api/users/${ids.guest}/temporary-password`, "POST", {}],
      [
        `/api/users/${ids.guest}/temporary-password`,
        "POST",
        { password: "a typed temporary one" },
      ],
    ]);
  } finally {
    mock.restore();
    restoreCookie();
  }
});

test("AC-T-UI an answer for another person is refused", async () => {
  const restoreCookie = installCsrfCookie("security-token");
  const mock = installFetch(() =>
    Response.json({ ...answer(null), user_id: ids.admin }),
  );
  try {
    await expect(setPersonTemporaryPassword(ids.guest, null)).rejects.toThrow();
  } finally {
    mock.restore();
    restoreCookie();
  }
});

const refusal = (status: number, code: string) =>
  new ApiError(status, "server words", { code, message: "server words" }, code);

const failures: [string, unknown, string][] = [
  [
    "a password the rules refuse",
    refusal(422, "password_policy_violation"),
    "This password does not meet the password rules. Use 12 to 128 characters and avoid a common password.",
  ],
  [
    "an owner",
    refusal(409, "security_target_owner"),
    "You cannot set a temporary password for an owner of this organization or of the installation.",
  ],
  [
    "yourself",
    refusal(409, "security_target_self"),
    "Change your own password in Account settings.",
  ],
  [
    "a person in another organization",
    refusal(409, "security_target_shared"),
    "This person also belongs to another organization. Only the installation owner can set their password.",
  ],
  [
    "a person who cannot sign in",
    refusal(409, "security_target_ineligible"),
    "This person cannot sign in now, so a temporary password cannot be set.",
  ],
  [
    "the administrator's own two-step",
    refusal(403, "mfa_required"),
    "Complete your own two-step verification first.",
  ],
  [
    "a password not confirmed after the sign-out",
    refusal(503, "security_action_incomplete"),
    "Their sessions ended, but the new password was not confirmed. Try again.",
  ],
  [
    "nothing changed",
    refusal(503, "user_security_unavailable"),
    "Nothing changed. Try again in a moment.",
  ],
  [
    "a changed session",
    new ApiError(401, "Unauthorized"),
    "Your session must be verified again.",
  ],
];

for (const [name, error, words] of failures)
  test(`AC-T-UI a refused temporary password names its reason: ${name}`, () => {
    expect(temporaryPasswordFailure(error)).toBe(words);
  });
