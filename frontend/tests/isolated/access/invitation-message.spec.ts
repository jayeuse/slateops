import { expect, test } from "@playwright/test";

import { invitationMessage } from "../../../src/components/systems/access/helpers/invitation-message";

// REQ-0024 addition 5: an invitation link alone does not say where the person
// joins or which names they sign in with. The administrator copies one
// message that says all of it.

const link =
  "https://slateops.example/auth/setup#token_hash=abc123&type=invite";

test("AC-I2 the invitation message names the organization, the link, how long it works and both sign-in names", () => {
  expect(
    invitationMessage({
      organization: "Harbor Logistics",
      link,
      email: "eve.stone@example.com",
      username: "eve_stone",
    }),
  ).toBe(
    "You are invited to join Harbor Logistics on Slate Operations. " +
      "Open this link to choose your password: https://slateops.example/auth/setup#token_hash=abc123&type=invite — it works once, for 24 hours. " +
      "Then sign in with eve.stone@example.com or your username eve_stone.",
  );
});

test("AC-I2 without a known organization the message still names the product and both sign-in names", () => {
  expect(
    invitationMessage({
      organization: null,
      link,
      email: "eve.stone@example.com",
      username: "eve_stone",
    }),
  ).toBe(
    "You are invited to join Slate Operations. " +
      "Open this link to choose your password: https://slateops.example/auth/setup#token_hash=abc123&type=invite — it works once, for 24 hours. " +
      "Then sign in with eve.stone@example.com or your username eve_stone.",
  );
});
