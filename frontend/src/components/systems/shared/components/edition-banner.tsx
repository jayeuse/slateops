"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Alert } from "@/components/ui/alert";
import { LICENSING_PAGE, useLicense } from "../adapters/license-api";
import { nearestLimit } from "../../manage/domain/license-rules";

function day(value: string | null): string {
  if (!value) return "";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

/**
 * The edition banner (spec editions.md ED-12). Everyone sees the warning and
 * the read-only state; administrators also see the grace period and a limit
 * at 80% or more. Each names the next step and links to the licensing page.
 */
export function EditionBanner() {
  const license = useLicense();
  const pathname = usePathname();
  if (!license) return null;
  // Usage counts reach administrators only.
  const admin = license.limits.some((item) => item.used !== null);
  const onLicensingPage = pathname === "/manage";
  let text: string | null = null;
  let tone: "default" | "destructive" = "default";
  if (license.read_only) {
    tone = "destructive";
    text = admin
      ? `The license ended on ${day(license.ends)}. Only administrators can change data until you import a new license file or reduce use to the Desk limits.`
      : `Slate Operations is read-only. The license ended on ${day(license.ends)}; your administrator can renew it.`;
  } else if (license.phase === "warning") {
    tone = "destructive";
    text = `The license ended on ${day(license.ends)}. On ${day(license.warning_ends)} this installation becomes Desk.`;
  } else if (license.phase === "grace" && admin) {
    text = `The license ended on ${day(license.ends)}. Renew it by ${day(license.grace_ends)}.`;
  } else if (admin) {
    const near = nearestLimit(license);
    if (near)
      text = `${near.label}: ${near.used} of ${near.allowed} used on ${license.edition_name}.${license.can_import ? "" : " The installation owner can upgrade."}`;
  }
  if (!text) return null;
  return (
    <Alert
      role={tone === "destructive" ? "alert" : "status"}
      variant={tone}
      className="mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-1"
    >
      <p className="min-w-0">{text}</p>
      {license.can_import && !onLicensingPage ? (
        <Link
          href={LICENSING_PAGE}
          className="text-action-text inline-flex min-h-11 items-center font-medium underline underline-offset-4"
        >
          Upgrade or renew
        </Link>
      ) : null}
    </Alert>
  );
}
