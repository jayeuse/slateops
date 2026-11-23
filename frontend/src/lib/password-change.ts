import { ApiError } from "./api";

// The forced password change (DEC-0042): after an administrator sets a
// temporary password, the server answers every call except a few auth routes
// with 403 `password_change_required` until the person chooses their own.
export {
  PASSWORD_CHANGE_ROUTE,
  notifyPasswordChangeRequired,
  subscribePasswordChangeRequired,
} from "./password-change-signal";

/** The words for a refused password change (Account settings and the page). */
export function passwordChangeErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "The current password was not accepted.";
    if (error.status === 429)
      return "Too many password attempts. Wait before trying again.";
    if (error.status === 503)
      return "Password changes are temporarily unavailable. Try again later.";
    if (error.status === 422)
      return "The new password was not accepted. Check the password requirements and try again.";
  }
  return "The password could not be changed. Try again.";
}
