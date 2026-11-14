// One selection pill for every rail of choices (Human Owner, 2026-11-14):
// tabs, link tabs, segmented filters, the phone stage switcher, and Color
// mode. The rail is the sunken track, the pill the raised piece under the
// chosen option, and every option is 28px from 1280px (44px below). Rails,
// pills and options that are not Tabs carry data-pill-rail, data-pill and
// data-pill-option, so each look restyles them as it restyles its tabs
// (themes/*.css).

export const pillRailClass =
  "rounded-[var(--radius)] bg-[var(--surface-sunken)] p-1 shadow-[inset_0_0_0_1px_var(--rule)]";

export const pillClass =
  "rounded-[calc(var(--radius)*0.75)] bg-[var(--surface-raised)] shadow-[var(--lift),inset_0_0_0_1px_var(--rule)]";

/** The option's height: the 44px touch floor below 1280px, 28px from it. */
export const pillOptionHeightClass = "min-h-11 xl:min-h-7";
