"use client";

import * as m from "motion/react-m";
import { MotionScope } from "@/components/motion-scope";
import { moveTransition } from "@/lib/motion-transitions";

/**
 * The Motion half of a segmented group's pill (toggle-group.tsx loads it
 * lazily, so a page with no segmented group loads no Motion). Choosing
 * another option moves the pill there over --motion-base with
 * --ease-in-out; under Reduce motion it jumps. There is no layoutDependency:
 * Motion snapshots the pill on each render, which is how a new pill starts
 * from where the old one is now; if a count changes an option's width, the
 * pill eases to the new size (the state that changed).
 */
export default function MotionSegmentedPill({
  id,
  className,
}: {
  id: string;
  className: string;
}) {
  return (
    <MotionScope>
      <m.span
        aria-hidden="true"
        data-slot="segmented-pill"
        data-pill=""
        layoutId={id}
        transition={moveTransition()}
        className={className}
      />
    </MotionScope>
  );
}
