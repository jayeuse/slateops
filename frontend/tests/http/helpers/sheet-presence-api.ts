import type { Page, WebSocketRoute } from "@playwright/test";

// Sheet presence (docs/specs/sheets.md D13): the presence token route and a
// stand-in for Supabase Realtime. The stand-in answers joins, leaves,
// keepalives, positions and token frames with "ok", records every frame, and
// sends each joined socket the presence state the test sets. It proves the
// browser side only; the live join, the write rule and revocation are the
// Realtime service's.

export const presenceOrg = "00000000-0000-4000-8000-0000000009e0";

export type PresenceFrame = {
  topic: string;
  event: string;
  payload: Record<string, unknown>;
  ref: string | null;
  join_ref?: string | null;
};
type Position = { row_id: string | null; column_key: string | null };

export async function installSheetPresenceApi(
  page: Page,
  options: { sheetId: string; viewers: string[]; status?: number },
) {
  const topic = `org:${presenceOrg}:worksheet:${options.sheetId}`;
  const sockets = new Map<WebSocketRoute, string>();
  const state = {
    viewers: options.viewers,
    status: options.status ?? 200,
    tokens: 0,
    opened: 0,
    closed: 0,
    frames: [] as PresenceFrame[],
    /** Who the channel says is here, by person id. */
    present: {} as Record<string, Position>,
    syncs: 0,
    /** Sends the present people to every joined socket. */
    sync() {
      // Each sync is a new state, as each tracked change is on the service.
      state.syncs += 1;
      for (const [socket, joinRef] of sockets)
        socket.send(
          JSON.stringify({
            topic: `realtime:${topic}`,
            event: "presence_state",
            payload: Object.fromEntries(
              Object.entries(state.present).map(([key, position], index) => [
                key,
                {
                  metas: [{ phx_ref: `p${state.syncs}.${index}`, ...position }],
                },
              ]),
            ),
            ref: null,
            join_ref: joinRef,
          }),
        );
    },
    /** The positions this browser tracked, in order. */
    tracked() {
      return state.frames
        .filter((frame) => frame.event === "presence")
        .map((frame) => frame.payload.payload);
    },
  };
  await page.route(
    (url) =>
      url.pathname === `/api/worksheets/${options.sheetId}/presence-token`,
    (route) => {
      state.tokens += 1;
      if (state.status !== 200)
        return route.fulfill({
          status: state.status,
          headers: { "Cache-Control": "no-store" },
          json: {
            detail: { code: "worksheet_not_found", message: "Sheet not found" },
          },
        });
      return route.fulfill({
        headers: { "Cache-Control": "no-store" },
        json: {
          token: `presence-${state.tokens}`,
          topic,
          expires_at: new Date(Date.now() + 60_000).toISOString(),
          viewers: state.viewers,
        },
      });
    },
  );
  await page.routeWebSocket("**/realtime/v1/websocket**", (socket) => {
    state.opened += 1;
    socket.onMessage((raw) => {
      const frame = JSON.parse(String(raw)) as PresenceFrame;
      state.frames.push(frame);
      if (
        [
          "phx_join",
          "phx_leave",
          "heartbeat",
          "presence",
          "access_token",
        ].includes(frame.event)
      )
        socket.send(
          JSON.stringify({
            ...frame,
            event: "phx_reply",
            payload: { status: "ok", response: {} },
          }),
        );
      if (frame.event === "phx_join") {
        sockets.set(socket, frame.join_ref ?? frame.ref ?? "");
        state.sync();
      }
      if (frame.event === "phx_leave") sockets.delete(socket);
    });
    socket.onClose(() => {
      sockets.delete(socket);
      state.closed += 1;
    });
  });
  return state;
}
