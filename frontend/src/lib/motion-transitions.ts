import type { Transition } from "motion/react";

// Motion reads each look's own timing tokens (globals.css, themes/*.css), so
// a look changes how things move without code changes. Values are read when
// a component renders; the fallbacks are Slate's, for the static prerender.

type Bezier = [number, number, number, number];

const SLATE_BASE_SECONDS = 0.22;
const SLATE_EASE_IN_OUT: Bezier = [0.65, 0, 0.35, 1];

function seconds(value: string, fallback: number): number {
  const match = value.trim().match(/^(\d*\.?\d+)(ms|s)$/);
  if (!match) return fallback;
  return Number(match[1]) / (match[2] === "ms" ? 1000 : 1);
}

function bezier(value: string, fallback: Bezier): Bezier {
  const points = value
    .match(/cubic-bezier\(([^)]+)\)/)?.[1]
    ?.split(",")
    .map(Number);
  return points?.length === 4 && points.every(Number.isFinite)
    ? (points as Bezier)
    : fallback;
}

/**
 * A move from one place to another (a selection pill gliding to the chosen
 * option): --motion-base with --ease-in-out, never a spring with bounce.
 */
export function moveTransition(): Transition {
  if (typeof document === "undefined")
    return {
      type: "tween",
      duration: SLATE_BASE_SECONDS,
      ease: SLATE_EASE_IN_OUT,
    };
  const style = getComputedStyle(document.documentElement);
  return {
    type: "tween",
    duration: seconds(
      style.getPropertyValue("--motion-base"),
      SLATE_BASE_SECONDS,
    ),
    ease: bezier(style.getPropertyValue("--ease-in-out"), SLATE_EASE_IN_OUT),
  };
}
