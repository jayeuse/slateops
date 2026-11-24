"use client";

import { PersonAvatar } from "@/components/person-avatar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import { presenceColor, type PresencePeer } from "../domain/sheet-presence";

// The sheet header's "who is here" (docs/specs/sheets.md PR1): an avatar for
// each other person with the sheet open now, ringed in their colour, the
// name on hover or focus. More than four collapse into "+N". Names and
// photos come from the person cards the page reads, never from the channel.

const SHOWN = 4;

export type PresencePerson = { name: string; avatarUrl: string | null };

// A 44px target on a phone (Software Architect, F9-N5).
const trigger =
  "focus-visible:outline-ring rounded-full outline-offset-2 focus-visible:outline-2 max-sm:inline-flex max-sm:min-h-11 max-sm:min-w-11 max-sm:items-center max-sm:justify-center";

/** One avatar, ringed in the person's colour over the page's own colour. */
function Ringed({
  peer,
  name,
  person,
}: {
  peer: PresencePeer;
  name: string;
  person: PresencePerson | undefined;
}) {
  return (
    <span
      className="inline-flex rounded-full"
      style={{
        boxShadow: `0 0 0 2px var(--background), 0 0 0 4px ${presenceColor(peer.userId)}`,
      }}
    >
      <PersonAvatar
        name={name}
        avatarUrl={person?.avatarUrl ?? null}
        size="sm"
      />
    </span>
  );
}

export function SheetPresenceAvatars({
  peers,
  people,
}: {
  peers: PresencePeer[];
  /** Each peer's card, by id; a card not read yet reads as a person. */
  people: ReadonlyMap<string, PresencePerson>;
}) {
  if (peers.length === 0) return null;
  const names = peers.map(
    (peer) => people.get(peer.userId)?.name ?? "Someone on this sheet",
  );
  const rest = names.slice(SHOWN);
  return (
    <div
      role="group"
      aria-label="On this sheet now"
      className="flex items-center gap-1.5"
    >
      {peers.slice(0, SHOWN).map((peer, index) => (
        <Tooltip key={peer.userId}>
          <TooltipTrigger
            render={
              <button
                type="button"
                aria-label={names[index]}
                className={trigger}
              />
            }
          >
            <Ringed
              peer={peer}
              name={names[index]}
              person={people.get(peer.userId)}
            />
          </TooltipTrigger>
          <TooltipContent>{names[index]}</TooltipContent>
        </Tooltip>
      ))}
      {rest.length > 0 ? (
        <Tooltip>
          <TooltipTrigger
            render={
              <button
                type="button"
                aria-label={`${rest.length} more: ${rest.join(", ")}`}
                className={trigger}
              />
            }
          >
            <span
              aria-hidden="true"
              className="bg-muted text-muted-foreground ring-background relative flex size-6 items-center justify-center rounded-full text-xs font-medium tabular-nums ring-2"
            >
              +{rest.length}
            </span>
          </TooltipTrigger>
          <TooltipContent>{rest.join(", ")}</TooltipContent>
        </Tooltip>
      ) : null}
    </div>
  );
}
