/**
 * The signal that the server refused a call with 403
 * `password_change_required` (DEC-0042). It has no imports, so `apiFetch` can
 * raise it without an import cycle.
 */
const passwordChangeEvent = "slateops:password-change-required";

/** The one page that works while a temporary password is set. */
export const PASSWORD_CHANGE_ROUTE = "/auth/change-password";

/** `apiFetch` calls this when the server refuses a call for this reason. */
export function notifyPasswordChangeRequired(): void {
  if (typeof window !== "undefined")
    window.dispatchEvent(new Event(passwordChangeEvent));
}

export function subscribePasswordChangeRequired(
  listener: () => void,
): () => void {
  window.addEventListener(passwordChangeEvent, listener);
  return () => window.removeEventListener(passwordChangeEvent, listener);
}
