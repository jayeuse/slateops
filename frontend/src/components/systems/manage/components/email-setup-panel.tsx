"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CircleCheck,
  CircleDashed,
  CircleMinus,
  CircleX,
  ExternalLink,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { LoadingRegion } from "@/components/ui/loading-region";
import { Skeleton } from "@/components/ui/skeleton";
import { apiErrorReference } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

import { emailSetupPageStatusOptions } from "../adapters/manage-queries";
import {
  emailHeadline,
  emailStatus,
  GMAIL_APP_PASSWORDS_URL,
  GMAIL_TWO_STEP_URL,
  type EmailHeadline,
} from "../domain/email-setup-rules";

const TONE_ICONS: Readonly<
  Record<EmailHeadline["tone"], { icon: LucideIcon; className: string }>
> = {
  working: { icon: CircleCheck, className: "text-flow-text" },
  not_set_up: { icon: CircleMinus, className: "text-warn-text" },
  not_working: { icon: CircleX, className: "text-danger-text" },
  unknown: { icon: CircleDashed, className: "text-muted-foreground" },
};

const cardClassName =
  "bg-card border-border min-w-0 rounded-[var(--radius)] border";

// From 1280px each pane scrolls alone and its last card takes the free
// height, as on System health (D23).
const paneClassName =
  "relative flex min-w-0 flex-col gap-4 xl:min-h-0 xl:overflow-y-auto xl:overscroll-contain xl:[&>:last-child]:flex-1";

const linkClassName =
  "text-action-text inline-flex min-h-11 items-center gap-1 font-medium underline underline-offset-4 xl:min-h-0";

function ExternalTextLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className={linkClassName}>
      {children}
      <ExternalLink aria-hidden="true" className="size-3.5" />
    </a>
  );
}

function Step({ number, children }: { number: number; children: ReactNode }) {
  return (
    <li className="grid min-w-0 grid-cols-[1.75rem_minmax(0,1fr)] items-baseline gap-x-2">
      <span className="bg-muted text-muted-foreground grid size-6 place-items-center rounded-full text-xs font-semibold tabular-nums">
        {number}
      </span>
      <div className="min-w-0">{children}</div>
    </li>
  );
}

function CardHeader({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div className="border-border flex min-h-14 items-center border-b px-4 py-2">
      <h2 id={id} data-slot="section-title" className="font-semibold">
        {children}
      </h2>
    </div>
  );
}

/**
 * Manage → Email (DEC-0042, AC-E2), for administrators: a band with the email
 * status from `GET /api/system/status`, over two panes with the setup steps in
 * reading order, where each happens: on the server PC (1, 2), then in Set up
 * email (3, 4). The page reads the status again on open, so the shell notice
 * goes as soon as email is set up. The web API does not expose the sending
 * address, so the page does not name one.
 */
export function EmailSetupPanel() {
  const status = useQuery({
    ...emailSetupPageStatusOptions(),
    refetchOnMount: "always",
  });
  const data = status.data;
  const headline = data ? emailHeadline(emailStatus(data)) : null;
  const icon = headline ? TONE_ICONS[headline.tone] : null;
  const failed = status.isError && !data;
  return (
    <div className="manage-scroll min-w-0">
      <div className="flex min-w-0 flex-col gap-4 xl:h-full">
        <section
          aria-labelledby="email-setup-status"
          className={cn(cardClassName, "p-4 xl:shrink-0")}
        >
          <LoadingRegion
            loading={status.isPending}
            label="Loading the email status"
            skeleton={
              <div className="flex flex-col gap-2">
                <Skeleton className="h-[1.125rem] w-48" />
                <Skeleton className="h-3.5 w-3/5" />
              </div>
            }
          >
            <div className="flex items-start gap-2">
              {icon ? (
                <icon.icon
                  aria-hidden="true"
                  className={cn("mt-0.5 size-5 shrink-0", icon.className)}
                />
              ) : null}
              <div className="min-w-0">
                <h2
                  id="email-setup-status"
                  data-slot="section-title"
                  className="text-lg font-semibold"
                >
                  {headline
                    ? headline.sentence
                    : failed
                      ? "The email status cannot be checked now."
                      : "Email status"}
                </h2>
                {headline?.line ? (
                  <p className="text-muted-foreground mt-1 text-sm">
                    {headline.line}
                  </p>
                ) : null}
              </div>
            </div>
          </LoadingRegion>
          {failed ? (
            <Alert
              role="alert"
              variant="destructive"
              className="mt-3 flex flex-wrap items-center gap-3"
              reference={apiErrorReference(status.error)}
            >
              <p className="mr-auto">The email status could not be loaded.</p>
              <Button
                type="button"
                variant="outline"
                className="min-h-11 xl:min-h-8"
                disabled={status.isFetching}
                onClick={() => void status.refetch()}
              >
                Retry
              </Button>
            </Alert>
          ) : null}
        </section>

        <div className="grid min-w-0 gap-4 xl:min-h-[15rem] xl:flex-1 xl:grid-cols-2 xl:grid-rows-[minmax(0,1fr)]">
          <div data-email-pane="server" className={paneClassName}>
            <section
              aria-labelledby="email-setup-server"
              className={cardClassName}
            >
              <CardHeader id="email-setup-server">On the server PC</CardHeader>
              <ol
                role="list"
                className="flex list-none flex-col gap-3 px-4 py-3 text-sm leading-6"
              >
                <Step number={1}>
                  Open{" "}
                  <strong className="font-semibold">
                    Slate Operations settings
                  </strong>{" "}
                  from the Start menu.
                </Step>
                <Step number={2}>
                  Select <strong className="font-semibold">Set up email</strong>
                  .
                </Step>
              </ol>
            </section>
          </div>

          <div data-email-pane="provider" className={paneClassName}>
            <section
              aria-labelledby="email-setup-provider"
              className={cardClassName}
            >
              <CardHeader id="email-setup-provider">In Set up email</CardHeader>
              <ol
                role="list"
                className="flex list-none flex-col gap-3 px-4 py-3 text-sm leading-6"
              >
                <Step number={3}>
                  <p>For Gmail:</p>
                  <ol role="list" className="mt-1 flex list-none flex-col">
                    <li>
                      a. Turn on{" "}
                      <ExternalTextLink href={GMAIL_TWO_STEP_URL}>
                        2-Step Verification
                      </ExternalTextLink>{" "}
                      for the Gmail account.
                    </li>
                    <li>
                      b. Make an{" "}
                      <ExternalTextLink href={GMAIL_APP_PASSWORDS_URL}>
                        app password
                      </ExternalTextLink>
                      , and type it in Set up email.
                    </li>
                  </ol>
                </Step>
                <Step number={4}>
                  For another provider: type its mail server name, port, and
                  password in Set up email.
                </Step>
              </ol>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
