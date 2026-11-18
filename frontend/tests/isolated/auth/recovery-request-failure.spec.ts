import { expect, test } from "@playwright/test";

import { requestRecovery } from "../../../src/lib/auth-api";
import { recoveryRequestFailureMessage } from "../../../src/lib/email-setup";
import { installFetch } from "../helpers/fake-fetch";

// DEC-0041: until email is set up on the server PC, a password reset request ends with
// email_not_configured, and the sign-in page says where to set email up. Any other
// failure keeps the general message.

test("AC-B3 a password reset request without email setup names the server PC settings", async () => {
  const mock = installFetch(() =>
    Response.json(
      {
        detail: {
          code: "email_not_configured",
          message:
            "Email is not set up yet. Set it up in Slate Operations settings on the server PC.",
        },
      },
      { status: 503 },
    ),
  );
  try {
    const error = await requestRecovery("person@example.test").catch(
      (caught: unknown) => caught,
    );
    expect(recoveryRequestFailureMessage(error)).toBe(
      "Email is not set up yet. Set it up in Slate Operations settings on the server PC.",
    );
  } finally {
    mock.restore();
  }
});

test("a password reset request that fails for another reason keeps the general message", async () => {
  const mock = installFetch(() =>
    Response.json({ detail: "Recovery service unavailable" }, { status: 503 }),
  );
  try {
    const error = await requestRecovery("person@example.test").catch(
      (caught: unknown) => caught,
    );
    expect(recoveryRequestFailureMessage(error)).toBe(
      "We could not process that request. Try again shortly.",
    );
  } finally {
    mock.restore();
  }
});
