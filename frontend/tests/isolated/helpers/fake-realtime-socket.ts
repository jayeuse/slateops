// A WebSocket stand-in for the Realtime client in isolated tests: it records
// each frame the client sends, answers joins, leaves, heartbeats, presence
// and token frames with "ok", and lets a test send server frames. `location`
// is set so the client builds its same-origin gateway address.

export type Frame = {
  topic: string;
  event: string;
  payload: Record<string, unknown>;
  ref: string | null;
  join_ref?: string | null;
};

const ANSWERED = [
  "phx_join",
  "phx_leave",
  "heartbeat",
  "presence",
  "access_token",
];

export function fakeRealtimeSockets(
  address = "http://127.0.0.1:3104/openview",
) {
  const sockets: FakeSocket[] = [];
  class FakeSocket extends EventTarget {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSING = 2;
    static CLOSED = 3;
    CONNECTING = 0;
    OPEN = 1;
    CLOSING = 2;
    CLOSED = 3;
    readyState = 0;
    url: string;
    protocol = "";
    bufferedAmount = 0;
    binaryType = "arraybuffer";
    frames: Frame[] = [];
    onopen: ((event: Event) => void) | null = null;
    onmessage: ((event: MessageEvent) => void) | null = null;
    onclose: ((event: CloseEvent) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    constructor(target: string | URL) {
      super();
      this.url = String(target);
      sockets.push(this);
      queueMicrotask(() => {
        if (this.readyState !== 0) return;
        this.readyState = 1;
        const event = new Event("open");
        this.onopen?.(event);
        this.dispatchEvent(event);
      });
    }
    send(value: string) {
      const frame = JSON.parse(value) as Frame;
      this.frames.push(frame);
      if (ANSWERED.includes(frame.event))
        queueMicrotask(() =>
          this.emit({
            ...frame,
            event: "phx_reply",
            payload: { status: "ok", response: {} },
          }),
        );
    }
    emit(frame: Frame) {
      if (this.readyState !== 1) return;
      const event = new MessageEvent("message", {
        data: JSON.stringify(frame),
      });
      this.onmessage?.(event);
      this.dispatchEvent(event);
    }
    close() {
      if (this.readyState === 3) return;
      this.readyState = 3;
      const event = Object.assign(new Event("close"), {
        code: 1000,
        reason: "",
        wasClean: true,
      }) as CloseEvent;
      this.onclose?.(event);
      this.dispatchEvent(event);
    }
  }
  const before = ["WebSocket", "location"].map(
    (name) =>
      [name, Object.getOwnPropertyDescriptor(globalThis, name)] as const,
  );
  Object.defineProperty(globalThis, "WebSocket", {
    configurable: true,
    value: FakeSocket,
  });
  Object.defineProperty(globalThis, "location", {
    configurable: true,
    value: new URL(address),
  });
  return {
    sockets,
    restore() {
      for (const [name, descriptor] of before) {
        if (descriptor) Object.defineProperty(globalThis, name, descriptor);
        else Reflect.deleteProperty(globalThis, name);
      }
    },
  };
}

/** Lets queued tasks run until `ready` holds (a hang guard, not a wait). */
export async function settle(ready: () => boolean, turns = 200) {
  for (let turn = 0; turn < turns && !ready(); turn += 1)
    await new Promise((done) => setTimeout(done, 0));
  if (!ready()) throw new Error("The expected state never came");
}
