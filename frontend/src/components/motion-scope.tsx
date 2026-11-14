"use client";

import { domMax, LazyMotion, MotionConfig } from "motion/react";
import { useSyncExternalStore, type ReactNode } from "react";

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-motion"],
  });
  return () => observer.disconnect();
}

const reducedInApp = () =>
  document.documentElement.dataset.motion === "reduced";

/**
 * Wraps the components that animate with Motion. Import it only from a
 * module that a shared primitive loads lazily (ui/segmented-pill.tsx), so a
 * page that shows no Motion component loads no Motion. The features load
 * with that module, so a component that mounts mid-move (a pill arriving at
 * the chosen option) is tracked from its first frame.
 * Motion follows Reduce motion. The Appearance switch (data-motion="reduced"
 * on <html>, lib/appearance-preferences.ts) forces it; otherwise the device
 * setting decides. Under it Motion drops transform and layout animations and
 * keeps opacity and color, as the Signal Not Travel Rule says. Components
 * use `m` from motion/react-m; `strict` refuses the heavier `motion` one.
 */
export function MotionScope({ children }: { children: ReactNode }) {
  const reduced = useSyncExternalStore(subscribe, reducedInApp, () => false);
  return (
    <MotionConfig reducedMotion={reduced ? "always" : "user"}>
      <LazyMotion features={domMax} strict>
        {children}
      </LazyMotion>
    </MotionConfig>
  );
}
