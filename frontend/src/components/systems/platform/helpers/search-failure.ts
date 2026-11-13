import { ApiError } from "@/lib/api";

/** An admission refusal on any search card asks the shell to check the session. */
export function isSearchAdmissionError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === "mfa_required" || error.code === "ip_not_allowed")
  );
}
