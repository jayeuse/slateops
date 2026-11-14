import type { ReactNode } from "react";

import { ProductMark } from "@/components/brand/product-mark";
import { cn } from "@/lib/utils";

/**
 * The frame of every signed-out page (SO-F, docs/specs/signed-out-pages.md):
 * the workspace top bar with the product link, and `main`. Both sit in the
 * root body column, so `main` takes the height under the bar and nothing
 * scrolls at rest. The page owns its session check: `busy` marks `main`,
 * and `actionsHidden` keeps the action slot's space while it hides.
 */
export function SignedOutFrame({
  children,
  actions,
  actionsHidden = false,
  busy = false,
}: {
  children: ReactNode;
  actions?: ReactNode;
  actionsHidden?: boolean;
  busy?: boolean;
}) {
  return (
    <>
      <header
        data-skin="topbar"
        className="border-border bg-card flex h-14 shrink-0 items-center justify-between gap-3 border-b px-4 sm:px-5"
      >
        <a
          href="/"
          className="flex min-h-11 min-w-0 items-center gap-2.5 rounded-md text-sm font-semibold xl:min-h-8"
        >
          <ProductMark />
          Slate Operations
        </a>
        {actions ? (
          <div
            className={cn(
              "flex shrink-0 items-center gap-2",
              actionsHidden && "invisible",
            )}
          >
            {actions}
          </div>
        ) : null}
      </header>
      <main
        id="main-content"
        data-skin="page"
        aria-busy={busy || undefined}
        className="flex flex-1 flex-col"
      >
        {children}
      </main>
    </>
  );
}
