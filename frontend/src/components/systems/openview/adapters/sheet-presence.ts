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
  rememberRefused,
  type PresenceCell,
  type PresencePeer,
} from "../domain/sheet-presence";

// Sheet presence over Supabase Realtime (docs/specs/sheets.md D13, D14). The
// browser asks FastAPI for a 60-second token for one sheet's private topic,
// joins it on a client of its own (no OpenComms channel rides on it), tracks
// only a cell position under the person's id, and renews the token every 45
// seconds on the same channel. A refused renewal for a hidden or missing
// sheet ends presence for good; any other, and a channel the service closes
// or fails, is tried once more (on a new client when the token has ended),
// then presence stops. Loaded on first use only, so the Realtime client is
// in no page's first load.

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

/** A token this close to its end is not renewed on its channel. */
const EXPIRY_MARGIN_MS = 5_000;
const EARLY_RENEWALS_A_MINUTE = 2;
const TRACK_GAP_MS = 100;

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
  // Failed token requests and lost channels since the last good join or
  // renewal: one more try each, then presence stops (no loop).
  let failures = 0;
  let viewers = new Set<string>();
  let expiresAt = 0;
  let cell: PresenceCell | null = null;
  let client: RealtimeClient | undefined;
  let channel: RealtimeChannel | undefined;
  let joined = false;
  let tracking = false;
  let sentCell: string | undefined;
  let lastTrackAt = Number.NEGATIVE_INFINITY;
  let cancelThrottle: (() => void) | undefined;
  let cancelTimer: (() => void) | undefined;
  let issuing: AbortController | undefined;
  let renewing = false;
  let earlyQueued = false;
  let shown: string | undefined;
  const earlyAt: number[] = [];
  // People on the channel but not on this token's list: a renewal not yet
  // started may list them. Once a newer token leaves them out, they ask for
  // no more early renewals (each 45-second renewal still checks them). At
  // most 50 are remembered; more still ask, within the two a minute.
  const waiting = new Set<string>();
  const refused = new Set<string>();

  const emit = (peers: PresencePeer[]) => {
    const key = JSON.stringify(peers);
    if (key === shown) return;
    shown = key;
    input.onPeers(peers);
  };

  const show = () => {
    if (ended) return;
    const state = channel ? channel.presenceState() : {};
    for (const key of Object.keys(state))
      if (key !== input.selfId && !viewers.has(key) && !refused.has(key))
        waiting.add(key);
    if (waiting.size > 0) renewEarly();
    emit(acceptedPeers(state, viewers, input.selfId));
  };

  // Someone joined after this token was issued: renew now, at most once in
  // 10 seconds and twice a minute. With the 45-second renewals that is at
  // most about 3.3 requests a minute, under the budget of 12.
  function renewEarly() {
    if (renewing || earlyQueued || !client || failures > 0 || ended) return;
    const at = now();
    while (earlyAt.length > 0 && at - earlyAt[0] >= 60_000) earlyAt.shift();
    if (earlyAt.length >= EARLY_RENEWALS_A_MINUTE) return;
    const wait =
      (earlyAt.at(-1) ?? Number.NEGATIVE_INFINITY) +
      PRESENCE_EARLY_RENEW_MS -
      at;
    cancelTimer?.();
    cancelTimer = undefined;
    if (wait <= 0) {
      earlyAt.push(at);
      void renew();
      return;
    }
    earlyQueued = true;
    cancelTimer = schedule(() => {
      earlyQueued = false;
      earlyAt.push(now());
      void renew();
    }, wait);
  }

  // One position in flight, at most one every 100 ms; the latest one wins.
  const track = async () => {
    if (!channel || !joined || tracking || ended || cancelThrottle) return;
    const payload = presencePayload(cell);
    const wanted = JSON.stringify(payload);
    if (wanted === sentCell) return;
    const wait = lastTrackAt + TRACK_GAP_MS - now();
    if (wait > 0) {
      cancelThrottle = schedule(() => {
        cancelThrottle = undefined;
        void track();
      }, wait);
      return;
    }
    tracking = true;
    sentCell = wanted;
    lastTrackAt = now();
    try {
      await channel.track(payload);
    } finally {
      tracking = false;
    }
    void track();
  };

  /** Drops the client and its channel; the session may open a new one. */
  const retire = async () => {
    const leaving = client;
    client = undefined;
    channel = undefined;
    joined = false;
    if (leaving) {
      await leaving.removeAllChannels().catch(() => {});
      await leaving.disconnect();
    }
  };

  const stop = async () => {
    if (ended) return;
    emit([]);
    ended = true;
    cancelTimer?.();
    cancelTimer = undefined;
    cancelThrottle?.();
    cancelThrottle = undefined;
    issuing?.abort();
    await retire();
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
    // The service closes the channel when its token ends: a retry that
    // comes after that opens a new client, and nobody shows meanwhile.
    if (client && now() + wait >= expiresAt - EXPIRY_MARGIN_MS) {
      emit([]);
      void retire();
    }
    cancelTimer = schedule(() => void renew(), wait);
  };

  // The channel was closed or failed (the service closed it, its token
  // ended, or the join was refused): nobody shows, and the next token opens
  // a new client, once.
  const lost = () => {
    emit([]);
    cancelTimer?.();
    cancelTimer = undefined;
    // The cancelled timer may have been a queued early renewal; let later
    // newcomers ask for one again.
    earlyQueued = false;
    void retire();
    failures += 1;
    if (failures > 1) {
      void stop();
      return;
    }
    void renew();
  };

  const issue = async () => {
    issuing = new AbortController();
    const token = await requestPresenceToken(input.sheetId, issuing.signal);
    if (ended) throw new DOMException("Presence ended", "AbortError");
    viewers = new Set(token.viewers);
    expiresAt = Date.parse(token.expires_at);
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
      const current = client;
      if (!current) {
        for (const key of asked) waiting.add(key);
        await open(token);
        return;
      }
      // The same channel takes the new token (`access_token`), and Realtime
      // checks it again.
      await current.setAuth(token.token);
      if (ended || client !== current) return;
      failures = 0;
      for (const key of asked)
        if (!viewers.has(key)) rememberRefused(refused, key);
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
    if (ended || client !== socket) return;
    const opened = socket.channel(token.topic, {
      config: {
        private: true,
        presence: { key: input.selfId, enabled: true },
        broadcast: { ack: false, self: false },
      },
    });
    channel = opened;
    opened.on("presence", { event: "sync" }, show).subscribe((status) => {
      if (ended || channel !== opened) return;
      if (status === "SUBSCRIBED") {
        joined = true;
        failures = 0;
        // A new join starts with nothing tracked on the server.
        sentCell = undefined;
        lastTrackAt = Number.NEGATIVE_INFINITY;
        void track();
        return;
      }
      joined = false;
      emit([]);
      if (
        status === "CLOSED" ||
        status === "CHANNEL_ERROR" ||
        status === "TIMED_OUT"
      )
        lost();
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
