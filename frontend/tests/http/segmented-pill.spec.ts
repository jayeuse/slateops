import { expect, test, type Locator } from "./helpers/test";
import { mockAccessApi } from "./helpers/access-api";

// A segmented filter has one raised pill that moves to the chosen option
// (Human Owner, 2026-11-13: rules 9 and 20, ease-in-out for moves and one
// shared element). Under Reduce motion it jumps; the choice still reads.

/**
 * Presses the first idle option and samples the pill's left edge on each
 * frame. Returns where it started, where the option is, and every frame.
 */
const choose = (group: Locator) =>
  group.evaluate(async (root) => {
    const pill = () =>
      root.querySelector<HTMLElement>('[data-slot="segmented-pill"]')!;
    const target = root.querySelector<HTMLElement>('[aria-pressed="false"]')!;
    const from = pill().getBoundingClientRect().left;
    const to = target.getBoundingClientRect().left;
    target.click();
    const frames: number[] = [];
    for (let frame = 0; frame < 40; frame += 1) {
      await new Promise(requestAnimationFrame);
      frames.push(pill().getBoundingClientRect().left);
    }
    return { from, to, frames };
  });

const glided = ({ from, to, frames }: Awaited<ReturnType<typeof choose>>) =>
  frames.some(
    (left) => Math.min(from, to) + 2 < left && left < Math.max(from, to) - 2,
  );

test("the status filter's pill glides to the chosen option, and jumps under Reduce motion", async ({
  page,
}) => {
  await mockAccessApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/access?view=people");
  const status = page.getByRole("group", { name: "Status", exact: true });
  const pill = status.locator('[data-slot="segmented-pill"]');

  // One pill, inside the pressed option.
  await expect(pill).toHaveCount(1);
  await expect(
    status.locator('[aria-pressed="true"] [data-slot="segmented-pill"]'),
  ).toHaveCount(1);

  // The Motion pill loads after the first paint (a still pill stands in);
  // once it is in, every choice moves the pill through the space between
  // the two options, never a jump.
  await expect.poll(async () => glided(await choose(status))).toBe(true);
  for (let choice = 0; choice < 4; choice += 1)
    expect(glided(await choose(status))).toBe(true);
  await expect(
    status.locator('[aria-pressed="true"] [data-slot="segmented-pill"]'),
  ).toHaveCount(1);

  // On its way the pill passes under the other options' words, never over
  // them. The move is slowed through the look's token to hold a mid frame.
  await page.evaluate(() =>
    document.documentElement.style.setProperty("--motion-base", "2000ms"),
  );
  const far = status.locator('[aria-pressed="false"]').last();
  await far.click();
  await expect
    .poll(() =>
      status.evaluate((root) => {
        const pill = root
          .querySelector('[data-slot="segmented-pill"]')!
          .getBoundingClientRect();
        // Every idle option that the moving pill covers still shows its words.
        const covered = [
          ...root.querySelectorAll<HTMLElement>('[aria-pressed="false"]'),
        ].flatMap((item) => {
          const box = item.getBoundingClientRect();
          const x = box.left + box.width / 2;
          const y = box.top + box.height / 2;
          if (x < pill.left || x > pill.right) return [];
          return [item.contains(document.elementFromPoint(x, y))];
        });
        if (!covered.length) return "the pill covers no option yet";
        return covered.every(Boolean) ? "words show" : "the pill hides words";
      }),
    )
    .toBe("words show");
  await page.evaluate(() =>
    document.documentElement.style.removeProperty("--motion-base"),
  );
  await expect(
    status.locator('[aria-pressed="true"] [data-slot="segmented-pill"]'),
  ).toHaveCount(1);

  // Reduce motion (Appearance) makes the pill jump to the choice.
  await page.evaluate(() => {
    document.documentElement.dataset.motion = "reduced";
  });
  const jump = await choose(status);
  expect(glided(jump)).toBe(false);
  expect(Math.round(jump.frames.at(-1)!)).toBe(Math.round(jump.to));

  // So does the device's own reduced-motion setting, with Appearance off.
  await page.evaluate(() => {
    delete document.documentElement.dataset.motion;
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const deviceJump = await choose(status);
  expect(glided(deviceJump)).toBe(false);
  expect(Math.round(deviceJump.frames.at(-1)!)).toBe(Math.round(deviceJump.to));
});
