/** The add hold and the save queue, as one render of Build sees them. */
export type CreateHoldState = {
  /** `designAddHoldReason`: why no add is accepted now, or null. */
  hold: string | null;
  /** The save queue holds the draft (a save is queued or in flight). */
  saving: boolean;
};

/**
 * True when a save was just refused, so an open entry or Connect closes
 * (N1 rule 3, B5c). A refused save is the one hold that arrives as the save
 * queue empties: a publish or a lifecycle action starts only on an empty
 * queue, and an edit's own save holds while its save is in flight. Any
 * other hold keeps the entry open with its controls disabled (rule 6).
 */
export function refusedSaveClosesCreate(
  previous: CreateHoldState,
  next: CreateHoldState,
): boolean {
  return next.hold !== null && previous.saving && !next.saving;
}
