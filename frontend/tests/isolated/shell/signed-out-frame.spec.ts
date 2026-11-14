import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { expect, test } from "@playwright/test";

// AC-2 (TASK-0062, docs/specs/signed-out-pages.md SO-F1, SO-M3): the
// signed-out pages share one frame (`SignedOutFrame`) and one product mark
// (`ProductMark`, in components/brand). Before this, each page drew its own
// "SO" block in one of four styles, one of them in action blue.

const app = join(__dirname, "..", "..", "..", "src", "app");

const signedOutPages = [
  "page.tsx",
  "login/page.tsx",
  "auth/recovery/page.tsx",
  "setup/page.tsx",
  "auth/setup/page.tsx",
  "auth/email-change/page.tsx",
];

function files(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.(tsx|ts)$/.test(name) ? [path] : [];
  });
}

test("no page under src/app draws its own product mark", () => {
  const offenders = files(app).filter((path) => {
    const text = readFileSync(path, "utf8");
    // A bare "SO" JSX text node, or the string rendered as an expression.
    return />\s*SO\s*</.test(text) || /\{\s*["'`]SO["'`]\s*\}/.test(text);
  });
  expect(offenders.map((path) => relative(app, path))).toEqual([]);
});

test("every signed-out page renders the shared frame and no header or main of its own", () => {
  const offenders: string[] = [];
  for (const page of signedOutPages) {
    const text = readFileSync(join(app, page), "utf8");
    if (!text.includes("<SignedOutFrame")) offenders.push(`${page}: no frame`);
    if (/<(main|header)[\s>]/.test(text))
      offenders.push(`${page}: own main or header`);
  }
  expect(offenders).toEqual([]);
});
