import type { ReactNode } from "react";
import { CommsClientProvider } from "@/components/systems/comms/state/client-context";
import { EditionGate } from "@/components/systems/shared/components/edition-gate";

export default function CommsLayout({ children }: { children: ReactNode }) {
  // OpenComms is an Office feature (spec docs/specs/editions.md ED-11).
  return (
    <EditionGate feature="opencomms" className="h-full">
      <CommsClientProvider>{children}</CommsClientProvider>
    </EditionGate>
  );
}
