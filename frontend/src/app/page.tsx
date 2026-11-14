"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Database, LockKeyhole } from "lucide-react";

import { SignedOutFrame } from "@/components/signed-out/signed-out-frame";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { workspaceStartRoute } from "@/components/workspace-start";
import { getSessionStatus } from "@/lib/auth-api";
import { cn } from "@/lib/utils";

const workflow = [
  ["01", "Join", "Your administrator sends you an invitation by email."],
  ["02", "Model", "Shape departments, modules, and fields around your team."],
  ["03", "Operate", "Work with validated records in one focused workspace."],
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
            Make the next action obvious.
          </h1>
          <p className="text-muted-foreground mt-5 max-w-xl text-base leading-7">
            Slate Operations gives teams a calm, structured place to design
            their operational data and keep work moving from setup to everyday
            records.
          </p>
          <div className={cn("mt-8", checkingSession && "invisible")}>
            <Button asChild size="lg" className="min-h-11">
              <a href="/login">
                Open workspace <ArrowRight aria-hidden="true" />
              </a>
            </Button>
          </div>
          <div className="text-muted-foreground mt-6 flex flex-wrap gap-x-6 gap-y-3 text-sm">
            <span className="inline-flex items-center gap-2">
              <LockKeyhole className="size-4" aria-hidden="true" /> Self-hosted
              access
            </span>
            <span className="inline-flex items-center gap-2">
              <Database className="size-4" aria-hidden="true" /> Your records
              stay on your server
            </span>
          </div>
        </div>

        <Card className="w-full lg:self-center">
          <CardHeader>
            <CardTitle>A guided start</CardTitle>
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
