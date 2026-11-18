import { ApiError } from "./api";

/**
 * An installation runs before its email is set up (DEC-0041). Until then the server
 * refuses an invitation or a password reset with `email_not_configured`.
 */
export const EMAIL_NOT_CONFIGURED_MESSAGE =
  "Email is not set up yet. Set it up in Slate Operations settings on the server PC.";

const RECOVERY_REQUEST_FAILED =
  "We could not process that request. Try again shortly.";

export function isEmailNotConfigured(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code as string | undefined) === "email_not_configured"
  );
}

/** The sign-in page's text for a failed password reset request. */
export function recoveryRequestFailureMessage(error: unknown): string {
  return isEmailNotConfigured(error)
    ? EMAIL_NOT_CONFIGURED_MESSAGE
    : RECOVERY_REQUEST_FAILED;
}
