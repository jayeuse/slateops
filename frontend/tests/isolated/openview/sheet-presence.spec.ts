import { expect, test } from "@playwright/test";

import { joinSheetPresence } from "../../../src/components/systems/openview/adapters/sheet-presence";
import {
  acceptedPeers,
  presenceColor,
  presenceOutlines,
  presencePayload,
  rememberRefused,
  type PresencePeer,
} from "../../../src/components/systems/openview/domain/sheet-presence";
import { installFetch } from "../helpers/fake-fetch";
import {
  fakeRealtimeSockets,
  settle,
  type Frame,
} from "../helpers/fake-realtime-socket";

// docs/specs/sheets.md PR1-PR6, D13, D14 (SH-63 to SH-66): sheet presence.
// The browser joins the sheet's own private topic with a 60-second token,
// tracks only a cell position, renews the token every 45 seconds on the same
// channel, and accepts only current viewers with a clean position.

const org = "00000000-0000-4000-8000-0000000009a0";
const sheet = "00000000-0000-4000-8000-0000000009a1";
const self = "00000000-0000-4000-8000-0000000009b0";
const ana = "00000000-0000-4000-8000-0000000009b1";
const ben = "00000000-0000-4000-8000-0000000009b2";
const cy = "00000000-0000-4000-8000-0000000009b3";
const dee = "00000000-0000-4000-8000-0000000009b4";
const eli = "00000000-0000-4000-8000-0000000009b5";
const fay = "00000000-0000-4000-8000-0000000009b6";
const gus = "00000000-0000-4000-8000-0000000009b7";
const hal = "00000000-0000-4000-8000-0000000009b8";
const stranger = "00000000-0000-4000-8000-0000000009bf";
const row1 = "00000000-0000-4000-8000-0000000009c1";
const row2 = "00000000-0000-4000-8000-0000000009c2";
const topic = `org:${org}:worksheet:${sheet}`;

test("a presence message carries the cell position only", () => {
  expect(presencePayload({ rowId: row1, columnKey: "c3" })).toEqual({
    row_id: row1,
    column_key: "c3",
  });
  expect(presencePayload(null)).toEqual({ row_id: null, column_key: null });
});

test("only current viewers are shown, and a cell is read from row_id and column_key alone", () => {
  const state = {
    [ana]: [{ presence_ref: "1", row_id: row1, column_key: "c3" }],
    // The viewer is never shown to themselves.
    [self]: [{ presence_ref: "2", row_id: row1, column_key: "c1" }],
    // Not among the token's viewers.
    [stranger]: [{ presence_ref: "3", row_id: row1, column_key: "c1" }],
    // Has the sheet open, on no cell yet.
    [ben]: [{ presence_ref: "4", row_id: null, column_key: null }],
    // A key that is not a column key, a row that is not an id, half a
    // position, no position at all: here, on no cell.
    [cy]: [{ presence_ref: "5", row_id: row1, column_key: 'c1"]{x}' }],
    [dee]: [{ presence_ref: "6", row_id: "row-1", column_key: "c1" }],
    [gus]: [{ presence_ref: "10", row_id: row1, column_key: null }],
    [hal]: ["Passed"],
    // Any other field is ignored, never shown.
    [eli]: [
      { presence_ref: "7", row_id: row1, column_key: "c1", value: "Passed" },
    ],
    // Two tabs: one person, at the latest position.
    [fay]: [
      { presence_ref: "8", row_id: row1, column_key: "c1" },
      { presence_ref: "9", row_id: row2, column_key: "c2" },
    ],
  };
  const viewers = new Set([self, ana, ben, cy, dee, eli, fay, gus, hal]);
  expect(acceptedPeers(state, viewers, self)).toEqual([
    { userId: ana, rowId: row1, columnKey: "c3" },
    { userId: ben, rowId: null, columnKey: null },
    { userId: cy, rowId: null, columnKey: null },
    { userId: dee, rowId: null, columnKey: null },
    { userId: gus, rowId: null, columnKey: null },
    { userId: hal, rowId: null, columnKey: null },
    { userId: eli, rowId: row1, columnKey: "c1" },
    { userId: fay, rowId: row2, columnKey: "c2" },
  ]);
});

test("a person's colour is one of four chart colours, never the focus blue, the same each time", () => {
  const colours = new Set([
    // Under 3:1 on light cards alone, so its line takes some ink (Boards).
    "color-mix(in oklab, var(--chart-2) 80%, var(--ink))",
    "var(--chart-3)",
    "var(--chart-4)",
    "var(--chart-5)",
  ]);
  for (const person of [ana, ben, cy, dee, eli, fay, gus, hal]) {
    expect(colours).toContain(presenceColor(person));
    expect(presenceColor(person)).toBe(presenceColor(person));
  }
});

test("a ring goes on a loaded row's cell of this sheet, with the person's colour, initials and name; two on one cell both show", () => {
  const loaded = new Map([
    [row1, 0],
    [row2, 7],
  ]);
  const names = new Map([
    [ana, "Ana Reyes"],
    [eli, "Eli Tan"],
  ]);
  const outlines = presenceOutlines(
    [
      { userId: ana, rowId: row2, columnKey: "c3" },
      // On no cell yet, on a row not loaded, on a column this sheet lacks.
      { userId: ben, rowId: null, columnKey: null },
      {
        userId: cy,
        rowId: "00000000-0000-4000-8000-0000000009cf",
        columnKey: "c1",
      },
      { userId: dee, rowId: row1, columnKey: "c9" },
      // Same cell as Ana.
      { userId: eli, rowId: row2, columnKey: "c3" },
      // A name not read yet: a question mark, never anything from the channel.
      { userId: fay, rowId: row1, columnKey: "c1" },
    ],
    (rowId) => loaded.get(rowId) ?? -1,
    new Set(["c1", "c2", "c3"]),
    (userId) => names.get(userId),
  );
  expect([...outlines]).toEqual([
    [
      "7:c3",
      [
        { color: presenceColor(ana), initials: "AR", name: "Ana Reyes" },
        { color: presenceColor(eli), initials: "ET", name: "Eli Tan" },
      ],
    ],
    [
      "0:c1",
      [
        {
          color: presenceColor(fay),
          initials: "?",
          name: "Someone on this sheet",
        },
      ],
    ],
  ]);
});

function tokenBody(token: string, viewers: string[], at = topic) {
  return {
    token,
    topic: at,
    expires_at: new Date(Date.now() + 60_000).toISOString(),
    viewers,
  };
}
const answer = (body: unknown, status = 200, headers = {}) =>
  Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store", ...headers },
  });
const notFound = () =>
  answer(
    {
      detail: { code: "worksheet_not_found", message: "Sheet not found" },
    },
    404,
  );

function clock() {
  const timers: { callback: () => void; delay: number; cancelled: boolean }[] =
    [];
  return {
    timers,
    live: () => timers.filter((timer) => !timer.cancelled),
    value(callback: () => void, delay: number) {
      // A timer that fires is spent, as a real one is.
      const timer = {
        callback: () => {
          timer.cancelled = true;
          callback();
        },
        delay,
        cancelled: false,
      };
      timers.push(timer);
      return () => {
        timer.cancelled = true;
      };
    },
  };
}

function session(schedule: ReturnType<typeof clock>, now = () => 0) {
  const seen = { peers: [] as PresencePeer[][], gone: 0 };
  const joined = joinSheetPresence({
    sheetId: sheet,
    selfId: self,
    onPeers: (peers) => seen.peers.push(peers),
    onGone: () => (seen.gone += 1),
    schedule: schedule.value,
    now,
  });
  return { joined, seen };
}

const tracks = (frames: Frame[]) =>
  frames
    .filter((frame) => frame.event === "presence")
    .map((frame) => frame.payload);

function presenceState(socket: { emit(frame: Frame): void }, state: object) {
  socket.emit({
    topic: `realtime:${topic}`,
    event: "presence_state",
    payload: state as Record<string, unknown>,
    ref: null,
  });
}

test("a person joins the sheet's own private topic under their id and tracks only a cell position", async () => {
  const harness = fakeRealtimeSockets();
  const fetch = installFetch(() =>
    answer(tokenBody("presence-a", [self, ana])),
  );
  const schedule = clock();
  let time = 0;
  const { joined, seen } = session(schedule, () => time);
  try {
    await settle(() => harness.sockets[0]?.frames.length > 1);
    const socket = harness.sockets[0];
    expect(
      fetch.requests.map((request) => ({
        path: String(request.input),
        method: request.init?.method,
      })),
    ).toEqual([
      { path: `/api/worksheets/${sheet}/presence-token`, method: "POST" },
    ]);
    expect(socket.url).toBe(
      "ws://127.0.0.1:3104/realtime/v1/websocket?vsn=1.0.0",
    );
    const join = socket.frames.find((frame) => frame.event === "phx_join");
    expect(join?.topic).toBe(`realtime:${topic}`);
    expect(join?.payload).toMatchObject({
      config: { private: true, presence: { key: self, enabled: true } },
      access_token: "presence-a",
    });
    await settle(() => tracks(socket.frames).length === 1);
    expect(tracks(socket.frames)).toEqual([
      {
        type: "presence",
        event: "track",
        payload: { row_id: null, column_key: null },
      },
    ]);

    joined.move({ rowId: row1, columnKey: "c3" });
    // At most one position in 100 ms: this one waits out the first.
    expect(tracks(socket.frames)).toHaveLength(1);
    time = 100;
    schedule
      .live()
      .find((timer) => timer.delay <= 100)
      ?.callback();
    await settle(() => tracks(socket.frames).length === 2);
    expect(tracks(socket.frames)[1]).toEqual({
      type: "presence",
      event: "track",
      payload: { row_id: row1, column_key: "c3" },
    });

    presenceState(socket, {
      [ana]: { metas: [{ phx_ref: "1", row_id: row1, column_key: "c2" }] },
    });
    expect(seen.peers.at(-1)).toEqual([
      { userId: ana, rowId: row1, columnKey: "c2" },
    ]);
    // Nothing but the join, the positions and the keepalive goes out.
    expect(
      socket.frames
        .map((frame) => frame.event)
        .filter(
          (event) => !["phx_join", "presence", "heartbeat"].includes(event),
        ),
    ).toEqual([]);
    expect(schedule.live().map((timer) => timer.delay)).toEqual([45_000]);
  } finally {
    await joined.leave();
    fetch.restore();
    harness.restore();
  }
});

test("a move and a leave that arrive as changes move the person, then remove them", async () => {
  const harness = fakeRealtimeSockets();
  const fetch = installFetch(() =>
    answer(tokenBody("presence-a", [self, ana])),
  );
  const schedule = clock();
  const { joined, seen } = session(schedule);
  try {
    await settle(() => tracks(harness.sockets[0]?.frames ?? []).length === 1);
    const socket = harness.sockets[0];
    presenceState(socket, {
      [ana]: { metas: [{ phx_ref: "1", row_id: row1, column_key: "c1" }] },
    });
    const diff = (payload: object) =>
      socket.emit({
        topic: `realtime:${topic}`,
        event: "presence_diff",
        payload: payload as Record<string, unknown>,
        ref: null,
      });
    // The service sends a change as a join of the new state and a leave of
    // the old one.
    diff({
      joins: {
        [ana]: { metas: [{ phx_ref: "2", row_id: row2, column_key: "c2" }] },
      },
      leaves: {
        [ana]: { metas: [{ phx_ref: "1", row_id: row1, column_key: "c1" }] },
      },
    });
    expect(seen.peers.at(-1)).toEqual([
      { userId: ana, rowId: row2, columnKey: "c2" },
    ]);
    diff({
      joins: {},
      leaves: {
        [ana]: { metas: [{ phx_ref: "2", row_id: row2, column_key: "c2" }] },
      },
    });
    expect(seen.peers.at(-1)).toEqual([]);
  } finally {
    await joined.leave();
    fetch.restore();
    harness.restore();
  }
});

test("the token is renewed every 45 seconds on the same channel", async () => {
  const harness = fakeRealtimeSockets();
  let issued = 0;
  const fetch = installFetch(() =>
    answer(
      issued++ === 0
        ? tokenBody("presence-a", [self, ana])
        : tokenBody("presence-b", [self, ana]),
    ),
  );
  const schedule = clock();
  const { joined, seen } = session(schedule);
  try {
    await settle(() => tracks(harness.sockets[0]?.frames ?? []).length === 1);
    const socket = harness.sockets[0];
    presenceState(socket, {
      [ana]: { metas: [{ phx_ref: "1", row_id: null, column_key: null }] },
    });
    expect(seen.peers.at(-1)?.map((peer) => peer.userId)).toEqual([ana]);
    expect(fetch.requests).toHaveLength(1);

    schedule.live()[0].callback();
    await settle(() =>
      socket.frames.some((frame) => frame.event === "access_token"),
    );
    expect(
      socket.frames.filter((frame) => frame.event === "access_token"),
    ).toEqual([
      expect.objectContaining({
        topic: `realtime:${topic}`,
        payload: { access_token: "presence-b" },
      }),
    ]);
    expect(harness.sockets).toHaveLength(1);
    await settle(() => schedule.live().length === 1);
    expect(schedule.live().map((timer) => timer.delay)).toEqual([45_000]);
  } finally {
    await joined.leave();
    fetch.restore();
    harness.restore();
  }
});

test("someone who joins after the token is renewed early, at most once in 10 seconds, and shown if the new token lists them", async () => {
  const harness = fakeRealtimeSockets();
  const answers = [
    tokenBody("presence-a", [self, ana]),
    tokenBody("presence-b", [self, ana, ben]),
    // Cy is not admitted (cannot see the sheet).
    tokenBody("presence-c", [self, ana, ben]),
  ];
  const fetch = installFetch(() => answer(answers.shift()));
  const schedule = clock();
  let time = 1_000;
  const { joined, seen } = session(schedule, () => time);
  try {
    await settle(() => tracks(harness.sockets[0]?.frames ?? []).length === 1);
    const socket = harness.sockets[0];
    presenceState(socket, {
      [ana]: { metas: [{ phx_ref: "1", row_id: null, column_key: null }] },
      [ben]: { metas: [{ phx_ref: "2", row_id: row2, column_key: "c1" }] },
    });
    // Renewed at once, not at the 45-second mark.
    await settle(() => fetch.requests.length === 2);
    await settle(() => seen.peers.at(-1)?.length === 2);
    expect(seen.peers.at(-1)?.map((peer) => peer.userId)).toEqual([ana, ben]);
    expect(schedule.live().map((timer) => timer.delay)).toEqual([45_000]);

    // Cy joins 4 seconds later: the next early renewal waits for the 10 s.
    time = 5_000;
    socket.emit({
      topic: `realtime:${topic}`,
      event: "presence_diff",
      payload: {
        joins: {
          [cy]: { metas: [{ phx_ref: "3", row_id: null, column_key: null }] },
        },
        leaves: {},
      },
      ref: null,
    });
    await new Promise((done) => setTimeout(done, 0));
    expect(fetch.requests).toHaveLength(2);
    expect(schedule.live().map((timer) => timer.delay)).toEqual([6_000]);
    time = 11_000;
    schedule.live()[0].callback();
    await settle(() => fetch.requests.length === 3);
    await settle(() => schedule.live().length === 1);
    expect(seen.peers.at(-1)?.map((peer) => peer.userId)).toEqual([ana, ben]);

    // Cy was checked and not admitted: their moves ask for nothing more.
    time = 30_000;
    socket.emit({
      topic: `realtime:${topic}`,
      event: "presence_diff",
      payload: {
        joins: {
          [cy]: { metas: [{ phx_ref: "4", row_id: row1, column_key: "c1" }] },
        },
        leaves: {
          [cy]: { metas: [{ phx_ref: "3", row_id: null, column_key: null }] },
        },
      },
      ref: null,
    });
    await new Promise((done) => setTimeout(done, 0));
    expect(fetch.requests).toHaveLength(3);
    expect(schedule.live().map((timer) => timer.delay)).toEqual([45_000]);
  } finally {
    await joined.leave();
    fetch.restore();
    harness.restore();
  }
});

test("a refused renewal for a hidden sheet leaves the channel and ends presence for good", async () => {
  const harness = fakeRealtimeSockets();
  let issued = 0;
  const fetch = installFetch(() =>
    issued++ === 0 ? answer(tokenBody("presence-a", [self, ana])) : notFound(),
  );
  const schedule = clock();
  const { joined, seen } = session(schedule);
  try {
    await settle(() => tracks(harness.sockets[0]?.frames ?? []).length === 1);
    const socket = harness.sockets[0];
    presenceState(socket, {
      [ana]: { metas: [{ phx_ref: "1", row_id: null, column_key: null }] },
    });
    schedule.live()[0].callback();
    await settle(() => seen.gone === 1);
    expect(seen.peers.at(-1)).toEqual([]);
    await settle(() => socket.readyState === socket.CLOSED);
    expect(schedule.live()).toEqual([]);
    expect(fetch.requests).toHaveLength(2);
  } finally {
    await joined.leave();
    fetch.restore();
    harness.restore();
  }
});

test("another refused renewal is tried once more after Retry-After, then presence stops", async () => {
  const harness = fakeRealtimeSockets();
  let issued = 0;
  const fetch = installFetch(() => {
    issued += 1;
    if (issued === 1) return answer(tokenBody("presence-a", [self, ana]));
    if (issued === 2)
      return answer(
        {
          detail: {
            code: "presence_rate_limited",
            message: "Wait before joining again",
          },
        },
        429,
        { "Retry-After": "7" },
      );
    return answer({ detail: "Unavailable" }, 503);
  });
  const schedule = clock();
  const { joined, seen } = session(schedule);
  try {
    await settle(() => tracks(harness.sockets[0]?.frames ?? []).length === 1);
    const socket = harness.sockets[0];
    schedule.live()[0].callback();
    await settle(() => schedule.live().length === 1 && issued === 2);
    expect(schedule.live().map((timer) => timer.delay)).toEqual([7_000]);
    schedule.live()[0].callback();
    await settle(() => socket.readyState === socket.CLOSED);
    expect(schedule.live()).toEqual([]);
    expect(seen.gone).toBe(0);
    expect(seen.peers.at(-1)).toEqual([]);
    expect(fetch.requests).toHaveLength(3);
  } finally {
    await joined.leave();
    fetch.restore();
    harness.restore();
  }
});

test("a token for another topic, or a hidden sheet at the start, opens no socket", async () => {
  for (const reply of [
    () =>
      answer(tokenBody("presence-a", [self], `org:${org}:worksheet:${row1}`)),
    notFound,
  ]) {
    const harness = fakeRealtimeSockets();
    const fetch = installFetch(reply);
    const schedule = clock();
    const { joined } = session(schedule);
    try {
      await settle(() => fetch.requests.length === 1);
      await new Promise((done) => setTimeout(done, 0));
      expect(harness.sockets).toHaveLength(0);
    } finally {
      await joined.leave();
      fetch.restore();
      harness.restore();
    }
  }
});

test("a renewal refused until after the token's expiry drops the closed channel and its people, then joins anew", async () => {
  let time = Date.now();
  const harness = fakeRealtimeSockets();
  let issued = 0;
  const fetch = installFetch(() => {
    issued += 1;
    if (issued === 2)
      return answer(
        {
          detail: {
            code: "presence_rate_limited",
            message: "Wait before joining again",
          },
        },
        429,
        { "Retry-After": "30" },
      );
    return answer({
      ...tokenBody(`presence-${issued}`, [self, ana]),
      expires_at: new Date(time + 60_000).toISOString(),
    });
  });
  const schedule = clock();
  const { joined, seen } = session(schedule, () => time);
  try {
    await settle(() => tracks(harness.sockets[0]?.frames ?? []).length === 1);
    const first = harness.sockets[0];
    presenceState(first, {
      [ana]: { metas: [{ phx_ref: "1", row_id: null, column_key: null }] },
    });
    expect(seen.peers.at(-1)).toHaveLength(1);
    // 45 s in, the renewal must wait 30 s: the token ends at 60 s.
    time += 45_000;
    schedule.live()[0].callback();
    await settle(() => schedule.live().length === 1 && issued === 2);
    expect(schedule.live().map((timer) => timer.delay)).toEqual([30_000]);
    expect(seen.peers.at(-1)).toEqual([]);
    await settle(() => first.readyState === first.CLOSED);
    time += 30_000;
    schedule.live()[0].callback();
    await settle(() => harness.sockets.length === 2);
    const second = harness.sockets[1];
    await settle(() =>
      second.frames.some((frame) => frame.event === "phx_join"),
    );
    expect(
      second.frames.find((frame) => frame.event === "phx_join")?.payload,
    ).toMatchObject({ access_token: "presence-3" });
  } finally {
    await joined.leave();
    fetch.restore();
    harness.restore();
  }
});

test("a channel the service closes clears the people and joins again with a new token", async () => {
  for (const ending of [[["phx_close", {}]]] as [
    string,
    Record<string, unknown>,
  ][][]) {
    const harness = fakeRealtimeSockets();
    let issued = 0;
    const fetch = installFetch(() =>
      answer(tokenBody(`presence-${++issued}`, [self, ana])),
    );
    const schedule = clock();
    const { joined, seen } = session(schedule);
    try {
      await settle(() => tracks(harness.sockets[0]?.frames ?? []).length === 1);
      const first = harness.sockets[0];
      presenceState(first, {
        [ana]: { metas: [{ phx_ref: "1", row_id: null, column_key: null }] },
      });
      expect(seen.peers.at(-1)).toHaveLength(1);
      for (const [event, payload] of ending) first.serverFrame(event, payload);
      expect(seen.peers.at(-1)).toEqual([]);
      await settle(() => harness.sockets.length === 2);
      const second = harness.sockets[1];
      await settle(() => tracks(second.frames).length === 1);
      expect(
        second.frames.find((frame) => frame.event === "phx_join")?.payload,
      ).toMatchObject({ access_token: "presence-2" });
      expect(first.readyState).toBe(first.CLOSED);
    } finally {
      await joined.leave();
      fetch.restore();
      harness.restore();
    }
  }
});

test("early renewals stop at two a minute", async () => {
  const harness = fakeRealtimeSockets();
  const fetch = installFetch(() =>
    answer(tokenBody("presence-a", [self, ana])),
  );
  const schedule = clock();
  let time = 1_000;
  const { joined } = session(schedule, () => time);
  const outsider = (n: number) =>
    `00000000-0000-4000-8000-${String(970000 + n).padStart(12, "0")}`;
  const arrive = (socket: (typeof harness.sockets)[number], n: number) =>
    socket.emit({
      topic: `realtime:${topic}`,
      event: "presence_diff",
      payload: {
        joins: {
          [outsider(n)]: {
            metas: [{ phx_ref: `o${n}`, row_id: null, column_key: null }],
          },
        },
        leaves: {},
      },
      ref: null,
    });
  try {
    await settle(() => tracks(harness.sockets[0]?.frames ?? []).length === 1);
    const socket = harness.sockets[0];
    // The service sends the state first; changes follow it.
    presenceState(socket, {});
    // Newcomers the token does not list, 10 seconds apart: two early
    // renewals, then none until a minute has passed.
    arrive(socket, 1);
    await settle(() => fetch.requests.length === 2);
    await settle(() => schedule.live().length === 1);
    time = 11_000;
    arrive(socket, 2);
    await settle(() => fetch.requests.length === 3);
    await settle(() => schedule.live().length === 1);
    time = 21_000;
    arrive(socket, 3);
    await new Promise((done) => setTimeout(done, 0));
    expect(fetch.requests).toHaveLength(3);
    expect(schedule.live().map((timer) => timer.delay)).toEqual([45_000]);
    time = 71_000;
    arrive(socket, 4);
    await settle(() => fetch.requests.length === 4);
  } finally {
    await joined.leave();
    fetch.restore();
    harness.restore();
  }
});

test("at most 50 people are remembered as not admitted", () => {
  const refused = new Set<string>();
  for (let n = 0; n < 60; n += 1) rememberRefused(refused, `person-${n}`);
  expect(refused.size).toBe(50);
  expect(refused.has("person-0")).toBe(true);
  expect(refused.has("person-50")).toBe(false);
});

test("leaving while a renewal hands the channel its new token starts nothing more", async () => {
  const hold: { leave?: () => Promise<void> } = {};
  const harness = fakeRealtimeSockets({
    onSend: (frame) => {
      if (frame.event === "access_token") void hold.leave?.();
    },
  });
  let issued = 0;
  const fetch = installFetch(() =>
    answer(tokenBody(`presence-${++issued}`, [self, ana])),
  );
  const schedule = clock();
  const { joined, seen } = session(schedule);
  hold.leave = joined.leave;
  try {
    await settle(() => tracks(harness.sockets[0]?.frames ?? []).length === 1);
    schedule.live()[0].callback();
    await settle(() =>
      harness.sockets[0].frames.some((frame) => frame.event === "access_token"),
    );
    await new Promise((done) => setTimeout(done, 0));
    expect(schedule.live()).toEqual([]);
    expect(seen.peers.at(-1)).toEqual([]);
  } finally {
    await joined.leave();
    fetch.restore();
    harness.restore();
  }
});

test("the same people sent again are not passed on again", async () => {
  const harness = fakeRealtimeSockets();
  const fetch = installFetch(() =>
    answer(tokenBody("presence-a", [self, ana])),
  );
  const schedule = clock();
  const { joined, seen } = session(schedule);
  try {
    await settle(() => tracks(harness.sockets[0]?.frames ?? []).length === 1);
    const socket = harness.sockets[0];
    presenceState(socket, {
      [ana]: { metas: [{ phx_ref: "1", row_id: row1, column_key: "c1" }] },
    });
    const count = seen.peers.length;
    presenceState(socket, {
      [ana]: { metas: [{ phx_ref: "2", row_id: row1, column_key: "c1" }] },
    });
    expect(seen.peers).toHaveLength(count);
  } finally {
    await joined.leave();
    fetch.restore();
    harness.restore();
  }
});

test("leaving drops the channel and stops the renewal", async () => {
  const harness = fakeRealtimeSockets();
  const fetch = installFetch(() => answer(tokenBody("presence-a", [self])));
  const schedule = clock();
  const { joined } = session(schedule);
  try {
    await settle(() => tracks(harness.sockets[0]?.frames ?? []).length === 1);
    const socket = harness.sockets[0];
    await joined.leave();
    expect(socket.readyState).toBe(socket.CLOSED);
    expect(schedule.live()).toEqual([]);
    joined.move({ rowId: row1, columnKey: "c1" });
    await new Promise((done) => setTimeout(done, 0));
    expect(tracks(socket.frames)).toHaveLength(1);
  } finally {
    await joined.leave();
    fetch.restore();
    harness.restore();
  }
});
