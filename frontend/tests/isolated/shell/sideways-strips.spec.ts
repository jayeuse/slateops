import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { expect, test } from "@playwright/test";

// A one-row strip that scrolls sideways (filters, tabs, toolbars) never
// scrolls up and down (Human Owner, 2026-11-14). `overflow-x-auto` alone
// turns on vertical scrolling as well, so a 1px rounding at some zoom or
// text size shows a vertical scrollbar. A strip (a class list with
// `flex-nowrap` or a horizontal-only scroll on a flex row) also sets
// `overflow-y-hidden` at the same breakpoint.

const source = join(__dirname, "..", "..", "..", "src");

function files(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.(tsx|ts)$/.test(name) ? [path] : [];
  });
}

test("every one-row strip that scrolls sideways also stops vertical scroll", () => {
  const offenders: string[] = [];
  for (const path of files(source)) {
    const text = readFileSync(path, "utf8");
    for (const match of text.matchAll(
      /["`]([^"`]*overflow-x-auto[^"`]*)["`]/g,
    )) {
      const classes = match[1]!.split(/\s+/);
      const strip =
        classes.some((name) => name.endsWith("flex-nowrap")) ||
        classes.some((name) => /(^|:)flex$/.test(name));
      if (!strip) continue;
      for (const name of classes.filter((n) => n.endsWith("overflow-x-auto"))) {
        const prefix = name.slice(0, -"overflow-x-auto".length);
        if (!classes.includes(`${prefix}overflow-y-hidden`))
          offenders.push(`${relative(source, path)}: ${name}`);
      }
    }
  }
  expect(offenders).toEqual([]);
});
