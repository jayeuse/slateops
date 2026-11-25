"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Alert } from "@/components/ui/alert";
import { FilePickerButton } from "@/components/ui/file-picker-button";
import { ApiError } from "@/lib/api";
import {
  importLicense,
  licenseKeys,
  licenseQueryOptions,
  type LicenseStatus,
} from "../../shared/adapters/license-api";
import { currentOrganizationId } from "@/lib/organization-context";
import {
  editionPriceWords,
  licenseStateWords,
  limitRows,
} from "../domain/license-rules";

const rowClassName =
  "grid min-w-0 grid-cols-[7rem_minmax(0,1fr)] items-baseline gap-3 py-1.5 sm:grid-cols-[8.5rem_minmax(0,1fr)]";

/**
 * The edition (spec editions.md ED-10): what this installation runs, its use
 * against each limit, the three editions with their prices, and the license
 * file import. Only the installation owner sees this section.
 */
export function LicensePanel() {
  const queryClient = useQueryClient();
  const license = useQuery(licenseQueryOptions());
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<{
    kind: "error" | "success";
    text: string;
  } | null>(null);

  async function onFiles(files: File[]) {
    const file = files[0];
    if (!file) return;
    setPending(true);
    setMessage(null);
    try {
      const text = await file.text();
      const status = await importLicense(text);
      queryClient.setQueryData(
        licenseKeys.status(currentOrganizationId()),
        status,
      );
      setMessage({
        kind: "success",
        text: `License imported. This installation now runs ${status.edition_name}.`,
      });
    } catch (error) {
      setMessage({
        kind: "error",
        text:
          error instanceof ApiError && error.status === 422
            ? error.message
            : "The license file could not be imported. Try again.",
      });
    } finally {
      setPending(false);
    }
  }

  const status: LicenseStatus | undefined = license.data;
  return (
    <section
      aria-labelledby="manage-license-heading"
      className="bg-card border-border min-w-0 shrink-0 rounded-[var(--radius)] border"
    >
      <div className="border-border flex min-h-14 flex-wrap items-center gap-x-2 border-b px-4 py-2">
        <h2
          id="manage-license-heading"
          data-slot="section-title"
          className="mr-auto font-semibold"
        >
          Edition and license
        </h2>
        {status?.can_import ? (
          <FilePickerButton
            accept=".slatelicense,.txt,text/plain"
            aria-label="License file"
            disabled={pending}
            onFiles={(chosen) => void onFiles(chosen)}
          >
            {pending ? "Importing license file…" : "Import license file"}
          </FilePickerButton>
        ) : null}
      </div>
      <div className="px-4 py-2">
        {message ? (
          <Alert
            role={message.kind === "error" ? "alert" : "status"}
            variant={message.kind === "error" ? "destructive" : "default"}
            className="my-1.5"
          >
            {message.text}
          </Alert>
        ) : null}
        {license.isError ? (
          <Alert role="alert" variant="destructive" className="my-1.5">
            The edition could not be loaded. Try again.
          </Alert>
        ) : !status ? (
          <p role="status" className="text-muted-foreground py-1.5 text-sm">
            Loading the edition…
          </p>
        ) : (
          <>
            <dl className="grid min-w-0 text-sm">
              <div className={rowClassName}>
                <dt className="text-muted-foreground">Edition</dt>
                <dd className="min-w-0">
                  {status.edition_name}
                  {status.customer ? (
                    <span className="text-muted-foreground">
                      {" "}
                      · Licensed to {status.customer}
                    </span>
                  ) : null}
                </dd>
              </div>
              <div className={rowClassName}>
                <dt className="text-muted-foreground">License</dt>
                <dd className="min-w-0">{licenseStateWords(status)}</dd>
              </div>
            </dl>
            <table className="mt-3 w-full min-w-0 text-sm">
              <caption className="text-muted-foreground mb-1 text-left text-xs">
                Use against the limits of {status.edition_name}
              </caption>
              <thead>
                <tr className="text-muted-foreground text-left">
                  <th scope="col" className="py-1.5 font-normal">
                    Item
                  </th>
                  <th scope="col" className="py-1.5 text-right font-normal">
                    Used
                  </th>
                  <th scope="col" className="py-1.5 text-right font-normal">
                    Limit
                  </th>
                </tr>
              </thead>
              <tbody>
                {limitRows(status).map((row) => (
                  <tr key={row.limit} className="border-border border-t">
                    <th scope="row" className="py-1.5 text-left font-normal">
                      {row.label}
                    </th>
                    <td
                      className={
                        row.full
                          ? "text-destructive py-1.5 text-right tabular-nums"
                          : "py-1.5 text-right tabular-nums"
                      }
                    >
                      {row.used}
                    </td>
                    <td className="py-1.5 text-right tabular-nums">
                      {row.allowed}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h3 className="mt-4 text-sm font-semibold">Editions</h3>
            <ul className="mt-1 grid gap-2 sm:grid-cols-3">
              {status.editions.map((edition) => (
                <li
                  key={edition.edition}
                  aria-current={
                    edition.edition === status.edition ? "true" : undefined
                  }
                  className="border-border aria-[current=true]:border-primary rounded-[var(--radius)] border p-3 text-sm"
                >
                  <p className="font-medium">
                    {edition.name}
                    {edition.edition === status.edition ? (
                      <span className="text-muted-foreground font-normal">
                        {" "}
                        · Current
                      </span>
                    ) : null}
                  </p>
                  <p className="text-muted-foreground">
                    {editionPriceWords(edition)}
                  </p>
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground mt-3 text-sm">
              After you pay for Office or Headquarters, you receive a license
              file. Import it here. It works with no internet.
            </p>
          </>
        )}
      </div>
    </section>
  );
}
