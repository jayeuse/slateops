"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";

import { SignedOutFrame } from "@/components/signed-out/signed-out-frame";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { workspaceStartRoute } from "@/components/workspace-start";
import { getSessionStatus } from "@/lib/auth-api";
import { cn } from "@/lib/utils";

const workflow = [
  [
    "01",
    "Draw",
    "Lay out your departments, what each one records, and how work moves between them.",
  ],
  [
    "02",
    "Test",
    "Send sample data through the drawing and see where it goes, before anyone relies on it.",
  ],
  [
    "03",
    "Work",
    "Your people keep records, boards and messages in one place, each seeing only what they may.",
  ],
] as const;

export default function Home() {
  const router = useRouter();
  const [checkingSession, setCheckingSession] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    async function checkSession() {
      try {
        const session = await getSessionStatus(controller.signal);
        if (session.authenticated) {
          const destination = await workspaceStartRoute();
          if (!controller.signal.aborted) router.replace(destination);
        } else if (!controller.signal.aborted) {
          setCheckingSession(false);
        }
      } catch {
        if (!controller.signal.aborted) setCheckingSession(false);
      }
    }
    void checkSession();
    return () => controller.abort();
  }, [router]);
  return (
    <SignedOutFrame
      busy={checkingSession}
      actionsHidden={checkingSession}
      actions={
        <Button asChild variant="outline" className="h-8 min-h-11 xl:min-h-8">
          <a href="/login">Sign in</a>
        </Button>
      }
    >
      <div className="mx-auto grid w-full max-w-6xl gap-10 px-4 pt-10 pb-12 sm:px-7 lg:my-auto lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)] lg:items-center lg:gap-16 lg:py-12">
        <div className="min-w-0">
          <h1
            data-slot="page-title"
            className="text-4xl leading-[1.1] font-bold tracking-[-0.025em] text-balance lg:text-5xl"
          >
            Draw your organization as it works.
          </h1>
          <p className="text-muted-foreground mt-5 max-w-xl text-base leading-7">
            Slate Operations turns the drawing into one system your people use
            every day.
          </p>
          <div className={cn("mt-8", checkingSession && "invisible")}>
            <Button asChild size="lg" className="min-h-11">
              <a href="/login">
                Open workspace <ArrowRight aria-hidden="true" />
              </a>
            </Button>
          </div>
          <p className="text-muted-foreground mt-6 text-sm">
            Staff join by invitation from their administrator.
          </p>
        </div>

        <Card className="w-full lg:self-center">
          <CardHeader>
            <CardTitle>How it works</CardTitle>
          </CardHeader>
          <ol className="divide-border divide-y">
            {workflow.map(([number, title, description]) => (
              <li className="flex gap-4 px-5 py-4" key={number}>
                <span className="text-muted-foreground font-mono text-xs leading-5 tabular-nums">
                  {number}
                </span>
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold">{title}</h3>
                  <p className="text-muted-foreground text-sm leading-5">
                    {description}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </SignedOutFrame>
  );
}
