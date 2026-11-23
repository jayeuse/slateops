"use client";

import { lazy, Suspense, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { authMeOptions } from "@/components/systems/openview/adapters/openview-queries";
import { emailSetupStatusOptions } from "@/components/systems/manage/adapters/manage-queries";
import {
  useVerifiedWorkspaceUserId,
  useWorkspaceInteractionSuspended,
} from "@/components/systems/shared/runtime/workspace-identity";
import { PASSWORD_CHANGE_ROUTE } from "@/lib/password-change-signal";

// The line loads only when it shows, so no cold page carries it.
const EmailSetupNoticeLine = lazy(
  () => import("@/components/email-setup-notice-line"),
);

/**
 * Two checks of the signed-in account, from the identity the shell already
 * reads (DEC-0042):
 *
 * - A person who must choose a new password goes to the one page that works.
 *   AppPage handles a 403 `password_change_required` from any other call.
 * - An administrator, while email is not set up, sees one quiet line under
 *   the top bar that links to Manage → Email (AC-E1). Members and guests read
 *   nothing. It shares Manage → Email's status read, with no timed refresh, so
 *   it goes once a later read (Manage → Email reads again on open) says email
 *   is set up. A loading, failed or unknown read shows nothing. Manage → Email
 *   says the same, so the line stays away there; on System health it sends no
 *   read of its own, so that page keeps its one status read (S3-C5).
 */
export function ShellAccountChecks() {
  const router = useRouter();
  const userId = useVerifiedWorkspaceUserId();
  const suspended = useWorkspaceInteractionSuspended();
  const pathname = usePathname();
  const view = useSearchParams().get("view");
  const identity = useQuery({ ...authMeOptions(), enabled: !suspended });
  const self =
    !suspended && identity.data?.id === userId ? identity.data : undefined;
  const changeRequired = self?.passwordChangeRequired === true;
  useEffect(() => {
    if (changeRequired) router.replace(PASSWORD_CHANGE_ROUTE);
  }, [changeRequired, router]);

  const admin = self?.role === "admin" && !changeRequired;
  const manageView = pathname === "/manage" ? view?.toLowerCase() : undefined;
  const status = useQuery({
    ...emailSetupStatusOptions(),
    enabled: admin && manageView !== "health",
  });
  const notSetUp =
    status.data?.parts.some(
      (part) => part.key === "email" && part.status === "not_set_up",
    ) === true;
  if (!admin || manageView === "email" || !notSetUp) return null;
  return (
    <Suspense fallback={null}>
      <EmailSetupNoticeLine />
    </Suspense>
  );
}
