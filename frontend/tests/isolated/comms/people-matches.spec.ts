import { expect, test } from "@playwright/test";
import { peopleToOffer } from "../../../src/components/systems/comms/domain/people-matches";
import { focusComposerWhenReady } from "../../../src/components/systems/comms/components/people-matches";

const me = "00000000-0000-4000-8000-000000000101";
const noah = "00000000-0000-4000-8000-000000000201";
const sofia = "00000000-0000-4000-8000-000000000202";
const mara = "00000000-0000-4000-8000-000000000203";
const person = (user_id: string, display_name: string) => ({
  user_id,
  display_name,
  avatar_url: null,
});
const direct = (other: string) => ({
  conversation: { kind: "direct" as const, participant_ids: [me, other] },
});
const group = (...others: string[]) => ({
  conversation: { kind: "group" as const, participant_ids: [me, ...others] },
});
const channel = { conversation: { kind: "channel" as const } };

test("UF-C5.2 a person with a visible one-to-one direct message shows once, as that conversation", () => {
  const candidates = [person(noah, "Noah Tan"), person(sofia, "Sofia Garcia")];
  // Noah's direct is among the matches: he shows only as that conversation.
  expect(
    peopleToOffer(candidates, [channel, direct(noah.toUpperCase())]),
  ).toEqual([person(sofia, "Sofia Garcia")]);
  // A shared group is not a one-to-one direct: both people stay offered.
  expect(peopleToOffer(candidates, [group(noah, sofia)])).toEqual(candidates);
  // A direct that is not among the visible matches (hidden or another name)
  // leaves the person under People; the pick opens that conversation.
  expect(peopleToOffer(candidates, [direct(mara)])).toEqual(candidates);
});

test("UF-C5.2 People lists at most five people", () => {
  const many = ["1", "2", "3", "4", "5", "6"].map((n) =>
    person(`00000000-0000-4000-8000-00000000030${n}`, `Person ${n}`),
  );
  expect(
    peopleToOffer(many, []).map((candidate) => candidate.display_name),
  ).toEqual(["Person 1", "Person 2", "Person 3", "Person 4", "Person 5"]);
});

/** A composer stand-in and a document that holds it once it "mounts". */
class FakeComposer {
  disabled = false;
  focused = 0;
  getClientRects() {
    return [{}];
  }
  focus() {
    this.focused += 1;
    world.active = this;
  }
}
const world: { active: unknown; mounted: Record<string, FakeComposer> } = {
  active: null,
  mounted: {},
};
function installDocument() {
  const body = {};
  world.active = body;
  world.mounted = {};
  const saved = {
    document: Object.getOwnPropertyDescriptor(globalThis, "document"),
    textarea: Object.getOwnPropertyDescriptor(
      globalThis,
      "HTMLTextAreaElement",
    ),
  };
  Object.defineProperty(globalThis, "HTMLTextAreaElement", {
    configurable: true,
    value: FakeComposer,
  });
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      body,
      get activeElement() {
        return world.active;
      },
      getElementById: (id: string) => world.mounted[id] ?? null,
    },
  });
  return () => {
    for (const [name, descriptor] of [
      ["document", saved.document],
      ["HTMLTextAreaElement", saved.textarea],
    ] as const)
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else Reflect.deleteProperty(globalThis, name);
  };
}
/** Frames run only when the test steps them. */
function fakeFrames() {
  const queued = new Map<number, () => void>();
  let next = 0;
  return {
    frame: (step: () => void) => {
      next += 1;
      queued.set(next, step);
      return next;
    },
    cancel: (handle: number) => void queued.delete(handle),
    run() {
      const steps = [...queued.values()];
      queued.clear();
      for (const step of steps) step();
    },
  };
}

test("FX-N3-1 a cancelled composer wait never focuses, even when the composer mounts later", () => {
  const restore = installDocument();
  try {
    const frames = fakeFrames();
    const cancel = focusComposerWhenReady("c1", frames.frame, frames.cancel);
    frames.run(); // The composer does not exist yet.
    cancel(); // As a second start does.
    const composer = new FakeComposer();
    world.mounted["composer-c1"] = composer;
    frames.run();
    frames.run();
    expect(composer.focused).toBe(0);
  } finally {
    restore();
  }
});

test("FX-N3-1 a second start ends the first wait; only the newer composer takes focus", () => {
  const restore = installDocument();
  try {
    const frames = fakeFrames();
    focusComposerWhenReady("first", frames.frame, frames.cancel);
    focusComposerWhenReady("second", frames.frame, frames.cancel);
    const first = new FakeComposer();
    const second = new FakeComposer();
    world.mounted["composer-first"] = first;
    world.mounted["composer-second"] = second;
    frames.run();
    expect([first.focused, second.focused]).toEqual([0, 1]);
  } finally {
    restore();
  }
});
