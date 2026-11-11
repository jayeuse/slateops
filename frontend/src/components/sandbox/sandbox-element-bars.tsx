"use client";

import {
  useLayoutEffect,
  useRef,
  type FocusEvent,
  type MutableRefObject,
  type ReactNode,
} from "react";
import { useStore } from "@xyflow/react";

import { DEPARTMENT_HEAD_HEIGHT } from "@/lib/sandbox/canvas-geometry";
import type { PointerRestEvent } from "@/components/systems/sandbox/helpers/element-bar";
import { absoluteBoxes, type SandboxFlowNode } from "./sandbox-flow-model";

/**
 * The element bars (docs/specs/sandbox-ux-redesign.md, "Element bar"): small
 * raised bars drawn at screen scale over the canvas. The canvas places them
 * and decides when a pointed element's bar shows; the owner gives their
 * controls.
 */
export interface SandboxElementBars {
  /** A bar that stays whatever the pointer or canvas does (focus is in it, or an entry it opened is open). */
  held: string | null;
  /** The element of the focused Structure row. */
  focused: string | null;
  /**
   * The bar's accessible name ("Sales actions"). React Flow already names
   * each node's own group after the element, so the bar needs its own name.
   */
  label: (ownerId: string) => string;
  /** The controls of one element's bar; `pinned` is the bar at the bottom of a phone canvas. */
  render: (ownerId: string, pinned: boolean) => ReactNode;
  /** Focus entered or left a bar. */
  onFocusChange: (ownerId: string, focused: boolean) => void;
}

/** Space between an element and its bar, in screen pixels. */
const BAR_GAP = 6;

/**
 * The element bars, drawn at screen scale over the canvas: a department's in
 * its head band after the name, a module's under its card (above the header
 * when the card bottom is out of view). Below 768px the selected element's
 * bar is pinned to the bottom of the canvas instead, with its name.
 */
export function ElementBarLayer({
  owners,
  pinnedOwner,
  nodes,
  containerRef,
  bars,
  onPointer,
}: {
  owners: readonly string[];
  pinnedOwner: string | null;
  nodes: readonly SandboxFlowNode[];
  containerRef: MutableRefObject<HTMLDivElement | null>;
  bars: SandboxElementBars;
  onPointer: (event: PointerRestEvent) => void;
}) {
  // Re-rendered on every pan and zoom step, so the bars follow the canvas.
  const transform = useStore((store) => store.transform);
  const barRefs = useRef(new Map<string, HTMLDivElement>());
  useLayoutEffect(() => {
    const container = containerRef.current;
    if (container === null) return;
    const [x, y, zoom] = transform;
    const view = container.getBoundingClientRect();
    const boxes = absoluteBoxes(nodes);
    for (const [owner, bar] of barRefs.current) {
      const box = boxes.get(owner);
      const node = nodes.find((item) => item.id === owner);
      if (box === undefined || node === undefined) {
        bar.style.visibility = "hidden";
        continue;
      }
      const height = bar.offsetHeight;
      const width = bar.offsetWidth;
      let left = box.x * zoom + x;
      let top: number;
      if (node.type === "department") {
        // In the head band, after the name, clear of the module count.
        const part = (name: string) =>
          container
            .querySelector(
              `[data-sandbox-node="${CSS.escape(owner)}"] [data-sandbox-part="${name}"]`,
            )
            ?.getBoundingClientRect();
        const name = part("department-name");
        const count = part("module-count");
        left = (name ? name.right - view.left : left + 34 * zoom) + 8;
        top = (box.y + DEPARTMENT_HEAD_HEIGHT / 2) * zoom + y - height / 2;
        if (count && left + width > count.left - view.left - 8)
          top = box.y * zoom + y - height - BAR_GAP;
      } else {
        // Under the card, where the next field appears; above the header
        // when the card bottom is out of view.
        top = (box.y + box.height) * zoom + y + BAR_GAP;
        if (top + height > view.height - BAR_GAP)
          top = box.y * zoom + y - height - BAR_GAP;
      }
      bar.style.left = `${Math.round(left)}px`;
      bar.style.top = `${Math.round(top)}px`;
      bar.style.visibility = "visible";
    }
  });
  const focusHandlers = (owner: string) => ({
    onFocus: () => bars.onFocusChange(owner, true),
    onBlur: (event: FocusEvent<HTMLDivElement>) => {
      if (
        !event.currentTarget.contains(
          event.relatedTarget as globalThis.Node | null,
        )
      )
        bars.onFocusChange(owner, false);
    },
  });
  return (
    <>
      {owners.map((owner) => (
        <div
          key={owner}
          ref={(element) => {
            if (element) barRefs.current.set(owner, element);
            else barRefs.current.delete(owner);
          }}
          data-element-bar={owner}
          role="group"
          aria-label={bars.label(owner)}
          style={{ visibility: "hidden" }}
          // A raised bar at screen scale: slim controls from 1280px, the
          // 44px floor below (DESIGN.md "Sandbox canvas").
          className="slim-ui absolute z-20 inline-flex items-center gap-0.5 rounded-md bg-[var(--surface-raised)] p-[3px] shadow-[inset_0_0_0_1px_var(--rule),var(--lift-raised)] max-md:hidden"
          onPointerEnter={() => onPointer({ type: "barEnter" })}
          onPointerLeave={() => onPointer({ type: "barLeave", at: Date.now() })}
          {...focusHandlers(owner)}
        >
          {bars.render(owner, false)}
        </div>
      ))}
      {pinnedOwner ? (
        <div
          key={`pinned-${pinnedOwner}`}
          data-element-bar={pinnedOwner}
          data-pinned=""
          role="group"
          aria-label={bars.label(pinnedOwner)}
          className="absolute inset-x-2 bottom-2 z-20 flex items-center gap-1 rounded-md bg-[var(--surface-raised)] p-1 shadow-[inset_0_0_0_1px_var(--rule),var(--lift-raised)] md:hidden"
          {...focusHandlers(pinnedOwner)}
        >
          {bars.render(pinnedOwner, true)}
        </div>
      ) : null}
    </>
  );
}
