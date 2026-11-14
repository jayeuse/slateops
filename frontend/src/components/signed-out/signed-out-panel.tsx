import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * The form panel of sign-in and recovery (SO-P, docs/specs/signed-out-pages.md):
 * one 24rem column centered under the top bar (m-auto, so a tall form keeps
 * its top on a short window), with the page title, its description, a
 * slim-ui card that holds the notices and the form, and one footer line.
 * `contentHidden` keeps the title and the empty card while the page checks
 * the session; the card's content and the footer keep their space.
 */
export function SignedOutPanel({
  title,
  titleId = "signed-out-title",
  description,
  children,
  footer,
  contentHidden = false,
}: {
  title: string;
  titleId?: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  contentHidden?: boolean;
}) {
  return (
    <div className="flex flex-1 flex-col px-4 py-8 sm:py-12">
      <div className="m-auto w-full max-w-sm">
        <h1
          id={titleId}
          data-slot="page-title"
          className="text-2xl leading-tight font-bold tracking-[-0.025em] sm:text-[1.875rem]"
        >
          {title}
        </h1>
        {description ? (
          <p className="text-muted-foreground mt-1.5 text-sm leading-6">
            {description}
          </p>
        ) : null}
        {/* The base Card is self-start; w-full keeps it the column's width. */}
        <Card className="slim-ui mt-6 w-full p-5">
          <div
            className={cn(
              "flex flex-col gap-4 [&_[data-slot=alert]]:wrap-anywhere",
              contentHidden && "invisible",
            )}
          >
            {children}
          </div>
        </Card>
        {footer ? (
          <p
            className={cn(
              "text-muted-foreground mt-6 text-center text-sm",
              contentHidden && "invisible",
            )}
          >
            {footer}
          </p>
        ) : null}
      </div>
    </div>
  );
}
