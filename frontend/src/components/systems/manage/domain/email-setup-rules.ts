import type { PartStatus } from "./health-rules";

/**
 * What Manage → Email and the shell's email notice say (DEC-0042): the email
 * part of `GET /api/system/status`, as a headline and one line under it.
 * Email is set up only in Slate Operations settings on the server PC; the web
 * API does not expose the sending address, so nothing here names it.
 */

type StatusParts = { parts: readonly { key: string; status: PartStatus }[] };

/** The email part's word, or `unknown` when the response has none. */
export function emailStatus(status: StatusParts): PartStatus {
  return status.parts.find((part) => part.key === "email")?.status ?? "unknown";
}

/** The shell notice shows only for this one word (AC-E1). */
export function emailNotSetUp(status: StatusParts | undefined): boolean {
  return status !== undefined && emailStatus(status) === "not_set_up";
}

export type EmailHeadline = {
  tone: "working" | "not_set_up" | "not_working" | "unknown";
  sentence: string;
  line: string | null;
};

export function emailHeadline(status: PartStatus): EmailHeadline {
  switch (status) {
    case "not_set_up":
      return {
        tone: "not_set_up",
        sentence: "Email is not set up.",
        line: "Invitations and password emails cannot be sent until it is.",
      };
    case "set_up":
      return {
        tone: "working",
        sentence: "Email is set up.",
        line: "No email was sent recently, so Slate Operations cannot confirm that it works.",
      };
    case "working":
    case "slow":
      return { tone: "working", sentence: "Email is working.", line: null };
    case "not_working":
      return {
        tone: "not_working",
        sentence: "Email is not working.",
        line: "Invitations and password emails may not arrive. Check the email settings on the server PC.",
      };
    default:
      return {
        tone: "unknown",
        sentence: "The email status is not known.",
        line: null,
      };
  }
}

/** Google's pages for a Gmail app password (AC-E2 step 3). */
export const GMAIL_TWO_STEP_URL =
  "https://myaccount.google.com/signinoptions/two-step-verification";
export const GMAIL_APP_PASSWORDS_URL =
  "https://myaccount.google.com/apppasswords";
