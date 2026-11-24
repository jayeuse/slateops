"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { authMeOptions } from "../adapters/openview-queries";
import type { SheetPresenceSession } from "../adapters/sheet-presence";
import {
  PRESENCE_GRACE_MS,
  type PresenceCell,
  type PresencePeer,
} from "../domain/sheet-presence";

/**
 * Who else has this sheet open now (docs/specs/sheets.md PR1-PR6, D13). The
 * page joins on open and leaves on navigation, after a tab has been hidden
 * for the grace period, and for good when the token route refuses the sheet.
 * `move` sends this person's cell; presence keeps no history.
 */
export function useSheetPresence(sheetId: string) {
  const identity = useQuery(authMeOptions());
  const selfId = identity.data?.id;
  const [peers, setPeers] = useState<PresencePeer[]>([]);
  const [gone, setGone] = useState(false);
  const [shown, setShown] = useState(true);
  const session = useRef<SheetPresenceSession | null>(null);
  const cell = useRef<PresenceCell | null>(null);

  // A short look away keeps the place; a long one leaves until shown again.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const changed = () => {
      clearTimeout(timer);
      if (document.visibilityState === "hidden")
        timer = setTimeout(() => setShown(false), PRESENCE_GRACE_MS);
      else setShown(true);
    };
    document.addEventListener("visibilitychange", changed);
    // A tab opened in the background starts its grace period at once.
    changed();
    return () => {
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", changed);
    };
  }, []);

  useEffect(() => {
    if (!selfId || gone || !shown) return;
    let left = false;
    let joined: SheetPresenceSession | null = null;
    void import("../adapters/sheet-presence")
      .then(({ joinSheetPresence }) => {
        if (left) return;
        joined = joinSheetPresence({
          sheetId,
          selfId,
          onPeers: (next) => {
            if (!left) setPeers(next);
          },
          onGone: () => {
            if (!left) setGone(true);
          },
        });
        session.current = joined;
        joined.move(cell.current);
      })
      // A part that fails to load leaves the sheet without presence.
      .catch(() => {});
    return () => {
      left = true;
      session.current = null;
      setPeers([]);
      void joined?.leave();
    };
  }, [sheetId, selfId, gone, shown]);

  const move = useCallback((next: PresenceCell) => {
    cell.current = next;
    session.current?.move(next);
  }, []);

  return { peers, move };
}
