"use client";

import {
  useLayoutEffect,
  useRef,
  type FocusEvent,
  type MutableRefObject,
  type ReactNode,
} from "react";
import { useStore } from "@xyflow/react";

import {
  DEPARTMENT_HEAD_HEIGHT,
  MODULE_TABLE,
} from "@/lib/sandbox/canvas-geometry";
import {
  departmentBarPlacement,
  moduleBarPlacement,
  type BarPlacement,
  type PointerRestEvent,
} from "@/components/systems/sandbox/helpers/element-bar";
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

/**
 * The element bars, drawn at screen scale over the canvas. Each tries three
 * places (helpers/element-bar.ts): a department's in its head band after
 * the name, then above the frame, then under the band inside the frame; a
 * module's under its card, then above the header, then under the header.
 * Below 768px the selected element's bar is pinned to the bottom of the
 * canvas instead, with its name.
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
      const frameLeft = box.x * zoom + x;
      const frameTop = box.y * zoom + y;
      let placement: BarPlacement;
      if (node.type === "department") {
        // Measured from the drawn head band, so the bar never covers the
        // name or the module count.
        const part = (name: string) =>
          container
            .querySelector(
              `[data-sandbox-node="${CSS.escape(owner)}"] [data-sandbox-part="${name}"]`,
            )
            ?.getBoundingClientRect();
        const name = part("department-name");
        const count = part("module-count");
        const identity = part("identity");
        const frameRight = (box.x + box.width) * zoom + x;
        placement = departmentBarPlacement({
          frameTop,
          bandBottom: (box.y + DEPARTMENT_HEAD_HEIGHT) * zoom + y,
          nameRight: name ? name.right - view.left : frameLeft + 34 * zoom,
          identityLeft: identity
            ? identity.left - view.left
            : frameLeft + 16 * zoom,
          countLeft: count ? count.left - view.left : frameRight - 16 * zoom,
          countRight: count ? count.right - view.left : frameRight - 16 * zoom,
          width,
          height,
        });
      } else {
        placement = moduleBarPlacement({
          left: frameLeft,
          top: frameTop,
          headerBottom: (box.y + MODULE_TABLE.headerHeight) * zoom + y,
          bottom: (box.y + box.height) * zoom + y,
          viewHeight: view.height,
          height,
        });
      }
      const { left, top, place } = placement;
      bar.dataset.place = place;
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
