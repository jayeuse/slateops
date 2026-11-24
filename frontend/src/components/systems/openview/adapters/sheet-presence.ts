"use client";

import type { RealtimeChannel, RealtimeClient } from "@supabase/realtime-js";
import { z } from "zod";

import { ApiError, apiFetch } from "@/lib/api";
import { createGatewayRealtime } from "@/components/systems/shared/adapters/realtime-gateway";

import {
  PRESENCE_EARLY_RENEW_MS,
  PRESENCE_REFRESH_MS,
  acceptedPeers,
  presencePayload,
  type PresenceCell,
  type PresencePeer,
} from "../domain/sheet-presence";

// Sheet presence over Supabase Realtime (docs/specs/sheets.md D13, D14). The
// browser asks FastAPI for a 60-second token for one sheet's private topic,
// joins it on a client of its own (no OpenComms channel rides on it), tracks
// only a cell position under the person's id, and renews the token every 45
// seconds on the same channel. A refused renewal for a hidden or missing
// sheet ends presence for good; any other is tried once more, then presence
// stops. Loaded on first use only, so the Realtime client is in no page's
// first load.

export type SheetPresenceSession = {
  move(cell: PresenceCell | null): void;
  leave(): Promise<void>;
};

type Schedule = (callback: () => void, milliseconds: number) => () => void;

const later: Schedule = (callback, milliseconds) => {
  const timer = setTimeout(callback, milliseconds);
  return () => clearTimeout(timer);
};

const uuid = z.string().uuid();

function tokenSchema(sheetId: string) {
  return z
    .object({
      token: z.string().min(1),
      topic: z.string().refine((topic) => {
        const match = /^org:([^:]+):worksheet:([^:]+)$/.exec(topic);
        return (
          match !== null &&
          uuid.safeParse(match[1]).success &&
          match[2] === sheetId
        );
      }),
      expires_at: z.iso.datetime({ offset: true }),
      viewers: z.array(uuid),
    })
    .strict();
}

/** A 60-second token for one sheet's presence topic (D13). */
export function requestPresenceToken(sheetId: string, signal: AbortSignal) {
  return apiFetch(
    `/worksheets/${encodeURIComponent(sheetId)}/presence-token`,
    tokenSchema(sheetId),
    { method: "POST", cache: "no-store", signal },
  );
}

export function joinSheetPresence(input: {
  sheetId: string;
  selfId: string;
  onPeers: (peers: PresencePeer[]) => void;
  /** The token route refused the sheet: it is hidden or gone. */
  onGone: () => void;
  schedule?: Schedule;
  now?: () => number;
}): SheetPresenceSession {
  const schedule = input.schedule ?? later;
  const now = input.now ?? (() => Date.now());
  let ended = false;
  let failures = 0;
  let viewers = new Set<string>();
  let cell: PresenceCell | null = null;
  let client: RealtimeClient | undefined;
  let channel: RealtimeChannel | undefined;
  let joined = false;
  let tracking = false;
  let sentCell: string | undefined;
  let cancelTimer: (() => void) | undefined;
  let issuing: AbortController | undefined;
  let renewing = false;
  let earlyQueued = false;
  let lastEarly = Number.NEGATIVE_INFINITY;
  // People on the channel but not on this token's list: a renewal not yet
  // started may list them. Once a newer token leaves them out, they ask for
  // no more early renewals (they still come in at a 45-second renewal).
  const waiting = new Set<string>();
  const refused = new Set<string>();

  const show = () => {
    if (ended) return;
    const state = channel ? channel.presenceState() : {};
    for (const key of Object.keys(state))
      if (key !== input.selfId && !viewers.has(key) && !refused.has(key))
        waiting.add(key);
    if (waiting.size > 0) renewEarly();
    input.onPeers(acceptedPeers(state, viewers, input.selfId));
  };

  // Someone joined after this token was issued: renew now, at most once in
  // 10 seconds, so they show without waiting for the 45-second renewal.
  function renewEarly() {
    if (renewing || earlyQueued || !client || failures > 0 || ended) return;
    const wait = lastEarly + PRESENCE_EARLY_RENEW_MS - now();
    cancelTimer?.();
    cancelTimer = undefined;
    if (wait <= 0) {
      lastEarly = now();
      void renew();
      return;
    }
    earlyQueued = true;
    cancelTimer = schedule(() => {
      earlyQueued = false;
      lastEarly = now();
      void renew();
    }, wait);
  }

  // One position in flight at a time; the latest one wins.
  const track = async () => {
    if (!channel || !joined || tracking || ended) return;
    const payload = presencePayload(cell);
    const wanted = JSON.stringify(payload);
    if (wanted === sentCell) return;
    tracking = true;
    sentCell = wanted;
    try {
      await channel.track(payload);
    } finally {
      tracking = false;
    }
    void track();
  };

  const stop = async () => {
    if (ended) return;
    ended = true;
    cancelTimer?.();
    cancelTimer = undefined;
    issuing?.abort();
    input.onPeers([]);
    const leaving = client;
    client = undefined;
    channel = undefined;
    if (leaving) {
      await leaving.removeAllChannels().catch(() => {});
      await leaving.disconnect();
    }
  };

  const failed = (error: unknown) => {
    if (ended) return;
    if (error instanceof ApiError && error.status === 404) {
      void stop();
      input.onGone();
      return;
    }
    failures += 1;
    if (failures > 1) {
      void stop();
      return;
    }
    const wait =
      error instanceof ApiError && error.retryAfter !== undefined
        ? error.retryAfter * 1_000
        : 10_000;
    cancelTimer = schedule(() => void renew(), wait);
  };

  const issue = async () => {
    issuing = new AbortController();
    const token = await requestPresenceToken(input.sheetId, issuing.signal);
    if (ended) throw new DOMException("Presence ended", "AbortError");
    failures = 0;
    viewers = new Set(token.viewers);
    return token;
  };

  async function renew() {
    cancelTimer = undefined;
    if (ended) return;
    renewing = true;
    const asked = new Set(waiting);
    waiting.clear();
    try {
      const token = await issue();
      if (!client) {
        await open(token);
        return;
      }
      // The same channel takes the new token (`access_token`), and Realtime
      // checks it again.
      await client.setAuth(token.token);
      for (const key of asked) if (!viewers.has(key)) refused.add(key);
      renewing = false;
      cancelTimer = schedule(() => void renew(), PRESENCE_REFRESH_MS);
      show();
    } catch (error) {
      for (const key of asked) waiting.add(key);
      renewing = false;
      failed(error);
    } finally {
      renewing = false;
    }
  }

  async function open(token: { token: string; topic: string }) {
    const socket = createGatewayRealtime();
    client = socket;
    await socket.setAuth(token.token);
    if (ended) return;
    channel = socket
      .channel(token.topic, {
        config: {
          private: true,
          presence: { key: input.selfId, enabled: true },
          broadcast: { ack: false, self: false },
        },
      })
      .on("presence", { event: "sync" }, show)
      .subscribe((status) => {
        if (ended) return;
        joined = status === "SUBSCRIBED";
        if (joined) {
          // A rejoin starts with nothing tracked on the server.
          sentCell = undefined;
          void track();
        }
      });
    cancelTimer = schedule(() => void renew(), PRESENCE_REFRESH_MS);
  }

  void renew();

  return {
    move(next) {
      if (ended) return;
      cell = next;
      void track();
    },
    leave: stop,
  };
}
