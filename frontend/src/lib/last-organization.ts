/**
 * Which organization a sign-in opens without asking (docs/specs/
 * ux-friction-pass.md, DR-13.1 to DR-13.3). The server still checks the open
 * as a pick; this rule only decides whether to ask it.
 */
type Membership = { orgId: string; name: string };

/** Why the server refused the automatic open. */
export type OpenRefusalKind = "mfa" | "network" | "other";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * The organization this browser opened last, when it is one of this
 * account's memberships and the account has several; otherwise null, and the
 * chooser shows. A value another account stored in the same browser is not a
 * membership, so it never opens. The membership's own id is returned, never
 * the stored text.
 */
export function lastOrganizationToOpen(
  stored: string | null,
  memberships: readonly Membership[],
): string | null {
  if (!stored || !UUID_PATTERN.test(stored) || memberships.length < 2)
    return null;
  const wanted = stored.toLowerCase();
  return (
    memberships.find((membership) => membership.orgId.toLowerCase() === wanted)
      ?.orgId ?? null
  );
}

/**
 * The refusal of an automatic open. `mfa_required` covers an account without
 * two-step and an enrolled account whose session has not passed it.
 */
export function openRefusalKind(
  status: number | null,
  code: string | null,
): OpenRefusalKind {
  if (status !== 403) return "other";
  if (code === "mfa_required") return "mfa";
  if (code === "ip_not_allowed") return "network";
  return "other";
}

/** The chooser's alert after a refused automatic open (Words, item 13). */
export function openRefusalMessage(
  organization: string,
  kind: OpenRefusalKind,
): string {
  if (kind === "mfa")
    return `${organization} asks for two-step verification. Choose it to continue.`;
  if (kind === "network")
    return `${organization} does not allow sign-in from this network.`;
  return `${organization} could not be opened.`;
}
