"use client";

import { useEffect } from "react";
import { trackFocusSource } from "@/lib/focus-source";

/** Marks what moved focus last on `<html>`; see `lib/focus-source.ts`. */
export function FocusSource() {
  useEffect(() => trackFocusSource(document.documentElement), []);
  return null;
}
