/** People offered under "People" in Find a conversation and the switcher. */
export const PEOPLE_LIMIT = 5;

type Candidate = { user_id: string };
type ConversationMatch = {
  conversation:
    | { kind: "direct"; participant_ids: readonly string[] }
    | { kind: "group"; participant_ids: readonly string[] }
    | { kind: "channel" };
};

/**
 * DR-5.3: a person whose one-to-one direct message is among the visible
 * conversation matches shows once, as that conversation. A direct that is not
 * visible (hidden, or its name does not match) leaves the person offered; the
 * start call then opens the existing conversation.
 */
export function peopleToOffer<T extends Candidate>(
  candidates: readonly T[],
  matches: readonly ConversationMatch[],
): T[] {
  const shown = new Set(
    matches.flatMap(({ conversation }) =>
      conversation.kind === "direct"
        ? conversation.participant_ids.map((id) => id.toLowerCase())
        : [],
    ),
  );
  return candidates
    .filter((person) => !shown.has(person.user_id.toLowerCase()))
    .slice(0, PEOPLE_LIMIT);
}
