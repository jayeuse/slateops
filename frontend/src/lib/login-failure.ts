import { ApiError } from "@/lib/api";

/**
 * Wrong or malformed credentials: a 401, or a 422 when the server refuses the
 * email's form. The person fixes these themselves.
 */
function isCredentialFailure(error: unknown): boolean {
  return (
    error instanceof ApiError && (error.status === 401 || error.status === 422)
  );
}

/** The sign-in form's message for a refused or failed sign-in. */
export function loginFailureMessage(error: unknown): string {
  if (isCredentialFailure(error)) {
    // The same words for every refusal, so they never tell which part was wrong.
    return "Wrong email, username or password.";
  } else if (error instanceof ApiError && error.status === 429) {
    if (error.retryAfter === undefined)
      return "Too many attempts. Try again later.";
    const minutes = Math.max(1, Math.ceil(error.retryAfter / 60));
    return `Too many attempts. Try again in ${minutes} ${minutes === 1 ? "minute" : "minutes"}.`;
  } else if (error instanceof ApiError && error.status === 503) {
    return "Sign-in is not available now. Try again later.";
  } else if (
    error instanceof ApiError &&
    error.status === 403 &&
    error.code === "ip_not_allowed"
  ) {
    return "Sign-in from this network is not allowed. Contact your administrator.";
  } else {
    return "Unable to sign in. Check your connection and try again.";
  }
}

/**
 * The cause the sign-in alert takes its support reference from: none for a
 * credential failure, which needs no administrator, else the error itself.
 */
export function loginFailureCause(error: unknown): unknown {
  return isCredentialFailure(error) ? undefined : error;
}
