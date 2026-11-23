/**
 * How long an invitation link works. The server fixes it at 24 hours
 * (`invitation_provider.INVITATION_LIFETIME`) and does not send it.
 */
export const INVITATION_LINK_LIFETIME = "24 hours";

/**
 * The ready-to-send message an administrator copies with an invitation link
 * (REQ-0024 addition 5): where the person joins, the link, how long it works,
 * and the two names they sign in with afterwards.
 */
export function invitationMessage({
  organization,
  link,
  email,
  username,
}: {
  /** The inviting organization's name; null when the shell has not read it. */
  organization: string | null;
  link: string;
  email: string;
  username: string;
}): string {
  const where = organization
    ? `${organization} on Slate Operations`
    : "Slate Operations";
  return (
    `You are invited to join ${where}. ` +
    `Open this link to choose your password: ${link} — it works once, for ${INVITATION_LINK_LIFETIME}. ` +
    `Then sign in with ${email} or your username ${username}.`
  );
}
