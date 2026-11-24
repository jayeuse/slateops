import { z } from "zod";
import type { AccessSecurityEvent } from "../adapters/security-events-api";

export const eventLabels: Record<string, string> = {
  "identity.sign_in": "Sign-in",
  "identity.sign_in_failure": "Sign-in failure",
  "identity.lockout": "Sign-in lockout",
  "identity.ip_blocked": "Address blocked",
  "identity.password_change": "Password change",
  "identity.email_change_request": "Email change request",
  "identity.email_change_confirmed": "Email change confirmed",
  "identity.recovery_request": "Recovery request",
  "identity.recovery_complete": "Recovery completion",
  "identity.mfa.enrolled": "Two-step verification enrollment",
  "identity.mfa.verified": "Two-step verification",
  "identity.mfa.removed": "Two-step verification removal",
  "identity.mfa.cancelled": "Two-step verification setup cancellation",
  "identity.mfa.removal_incomplete": "Incomplete two-step verification removal",
  "identity.recovery": "Person recovery request",
  "identity.mfa_reset": "Two-step verification reset",
  "identity.session_revocation": "Session ending",
  "identity.local_admin_recovery": "Local administrator recovery",
  "identity.local_security_recovery": "Local security recovery",
  "user.invitation": "Invitation",
  "user.invitation_resend": "Invitation resend",
  "user.invitation_revocation": "Invitation revocation",
  "user.invitation_acceptance": "Invitation acceptance",
  "user.authentication_activation": "Sign-in enabled",
  "user.authentication_disable": "Sign-in disabled",
  "user.authentication_restore": "Sign-in restored",
  "workspace.security_policy_change": "Account policy change",
  "security.retention": "Session history cleanup",
  "backup.export.download": "Backup export download",
  "file.download": "File download",
  "records.export.authorized": "Record export authorization",
  "records.aggregate_snapshot.authorized": "Record summary authorization",
  "records.aggregate_snapshots.authorized": "Record summaries authorization",
  "lifecycle.record_purge": "Record deleted forever",
  "job.retry": "Job retry",
  "worksheets.export.authorized": "Sheet export authorization",
  "worksheets.opened_on_leave": "Sheets opened on leave",
  "worksheets.import.file_parsed": "Sheet import file check",
};

// How a sheet owner left (sheets spec D5.4 `path`).
const leavePaths: Record<string, string> = {
  membership_disabled: "when their membership was disabled",
  account_disabled: "when their account was disabled",
  membership_removed: "when they were removed from the organization",
  account_deleted: "when their account was deleted",
};

// Why an Excel file was refused (sheets spec D5.4 `reason`).
const importReasons: Record<string, string> = {
  too_large: "The file is too large.",
  archive_bounds: "The file expands past the size limit.",
  macro: "The file has macros.",
  unreadable: "The file could not be read.",
  limit: "The file has more rows or columns than a sheet allows.",
};

export function address(event: AccessSecurityEvent) {
  const parsed = z
    .union([z.ipv4(), z.ipv6()])
    .safeParse(event.metadata.ip_address);
  return parsed.success ? parsed.data : "Address unknown";
}
function recordedPerson(event: AccessSecurityEvent) {
  return event.subject_id ?? event.actor_id;
}
export type PersonNames = ReadonlyMap<string, string>;
export function personName(names: PersonNames, id: string | null) {
  return (id && names.get(id)) || "Unknown person";
}

/** Only emitter-recorded facts become text; attempts never imply completion. */
export function securityEventSentence(
  event: AccessSecurityEvent,
  names: PersonNames,
): string {
  const actor = personName(names, event.actor_id);
  const subject = personName(names, event.subject_id);
  const person = personName(names, recordedPerson(event));
  const network =
    address(event) === "Address unknown"
      ? "an unknown address"
      : address(event);
  const count = (key: string) => {
    const value = event.metadata[key];
    return typeof value === "number" &&
      Number.isSafeInteger(value) &&
      value >= 0
      ? value
      : null;
  };
  const result = (completed: string, action: string) => {
    if (event.outcome === "success") return completed;
    const endings = {
      attempt: "was attempted",
      partial: "was only partly completed",
      denied: "was denied",
      failure: "failed",
    };
    return `${action} ${endings[event.outcome]}.`;
  };
  switch (event.event_type) {
    case "identity.sign_in":
      return result(
        `${actor}'s sign-in was accepted from ${network}.`,
        `Sign-in for ${actor}`,
      );
    case "identity.sign_in_failure":
      return `Failed sign-in attempts were recorded from ${network}.`;
    case "identity.ip_blocked":
      return `Sign-in was blocked from ${network}.`;
    case "identity.lockout":
      return `Sign-in was temporarily locked from ${network}.`;
    case "identity.password_change":
      return result(
        `${actor} changed their password.`,
        `Password change for ${actor}`,
      );
    case "identity.email_change_request":
      return result(
        `${actor}'s email change was requested; both addresses still require confirmation.`,
        `Email change request for ${actor}`,
      );
    case "identity.email_change_confirmed":
      return result(
        `${person}'s confirmed email was saved during protected sign-in.`,
        `Confirmed email synchronization for ${person}`,
      );
    case "identity.recovery_request":
      return result(
        "A password recovery request was accepted.",
        "A password recovery request",
      );
    case "identity.recovery_complete":
      return result(
        `${person} completed password recovery.`,
        `Password recovery for ${person}`,
      );
    case "identity.mfa.enrolled":
      return result(
        `${person} enrolled a two-step verification factor.`,
        `Two-step verification enrollment for ${person}`,
      );
    case "identity.mfa.verified":
      return result(
        `${person} completed two-step verification.`,
        `Two-step verification for ${person}`,
      );
    case "identity.mfa.removed":
      return result(
        `${person} removed a two-step verification factor.`,
        `Two-step verification removal for ${person}`,
      );
    case "identity.mfa.cancelled":
      return result(
        `${person} cancelled two-step verification setup.`,
        `Two-step verification setup cancellation for ${person}`,
      );
    case "identity.mfa.removal_incomplete":
      return result(
        `Incomplete two-step verification removal was recorded for ${person}.`,
        `Two-step verification removal for ${person}`,
      );
    case "identity.recovery":
      return result(
        `${actor} requested password recovery for ${subject}.`,
        `Password recovery request by ${actor} for ${subject}`,
      );
    case "identity.mfa_reset":
      return result(
        `${actor} reset two-step verification for ${subject}.`,
        `Two-step verification reset by ${actor} for ${subject}`,
      );
    case "identity.session_revocation": {
      const scope = event.labels.scope;
      const completed =
        scope === "one"
          ? `${actor} ended a session for ${subject}.`
          : scope === "others"
            ? `${actor} ended ${subject}'s other sessions.`
            : scope === "all"
              ? `${actor} ended all sessions for ${subject}.`
              : `${actor} ended sessions for ${subject}.`;
      return result(completed, `Session ending by ${actor} for ${subject}`);
    }
    case "identity.local_admin_recovery":
      return result(
        `Local administrator recovery was requested for ${subject}.`,
        `Local administrator recovery for ${subject}`,
      );
    case "identity.local_security_recovery":
      return result(
        `Local security recovery completed for ${subject}.`,
        `Local security recovery for ${subject}`,
      );
    case "user.invitation":
      return result(
        `${actor} invited ${subject}.`,
        `An invitation from ${actor} to ${subject}`,
      );
    case "user.invitation_resend":
      return result(
        `${actor} resent an invitation for ${subject}.`,
        `Invitation resend by ${actor} for ${subject}`,
      );
    case "user.invitation_revocation":
      return result(
        `${actor} revoked ${subject}'s invitation.`,
        `Invitation revocation by ${actor} for ${subject}`,
      );
    case "user.invitation_acceptance":
      return result(
        `${person} accepted an invitation.`,
        `Invitation acceptance by ${person}`,
      );
    case "user.authentication_activation":
      return result(
        `${actor} enabled sign-in for ${subject}.`,
        `Enabling sign-in by ${actor} for ${subject}`,
      );
    case "user.authentication_disable":
      return result(
        `${actor} disabled sign-in for ${subject}.`,
        `Disabling sign-in by ${actor} for ${subject}`,
      );
    case "user.authentication_restore":
      return result(
        `${actor} restored sign-in for ${subject}.`,
        `Restoring sign-in by ${actor} for ${subject}`,
      );
    case "workspace.security_policy_change":
      return result(
        `${actor} changed the account security policy.`,
        `Account security policy change by ${actor}`,
      );
    case "security.retention": {
      const removed = count("deleted_sessions");
      return result(
        `Session history cleanup removed ${removed === null ? "session records" : `${removed} session record${removed === 1 ? "" : "s"}`}.`,
        "Session history cleanup",
      );
    }
    case "backup.export.download":
      return result(
        `Backup export download was authorized for ${actor}.`,
        `Backup export download by ${actor}`,
      );
    case "file.download":
      return result(
        `File download was authorized for ${actor}.`,
        `File download by ${actor}`,
      );
    case "records.export.authorized": {
      const rows = count("row_count");
      const records =
        rows === null ? "records" : `${rows} record${rows === 1 ? "" : "s"}`;
      const format =
        event.metadata.format === "xlsx"
          ? "Excel"
          : event.metadata.format === "csv"
            ? "CSV"
            : null;
      return result(
        `${actor} was authorized to export ${records}${format ? ` as ${format}` : ""}.`,
        `Record export by ${actor}`,
      );
    }
    case "records.aggregate_snapshot.authorized": {
      const buckets = count("bucket_count");
      return result(
        `${actor} was authorized to read a record summary${buckets === null ? "" : ` with ${buckets} group${buckets === 1 ? "" : "s"}`}.`,
        `Record summary by ${actor}`,
      );
    }
    case "records.aggregate_snapshots.authorized": {
      const queries = count("query_count");
      const buckets = count("bucket_count");
      const snapshots =
        queries === null
          ? "record summaries"
          : `${queries} record ${queries === 1 ? "summary" : "summaries"}`;
      return result(
        `${actor} was authorized to read ${snapshots}${buckets === null ? "" : ` with ${buckets} group${buckets === 1 ? "" : "s"}`}.`,
        `Record summaries by ${actor}`,
      );
    }
    case "lifecycle.record_purge":
      return result(
        `${actor} deleted a record forever.`,
        `Delete forever by ${actor}`,
      );
    case "job.retry": {
      const kinds: Record<string, string> = {
        "report-run": "report run",
        "post-publish": "post publication",
        "event-reminder": "event reminder",
        backup: "backup",
      };
      const kind =
        typeof event.metadata.kind === "string" &&
        Object.hasOwn(kinds, event.metadata.kind)
          ? kinds[event.metadata.kind]
          : null;
      return result(
        `${actor} queued a retry for ${kind ? `${/^[aeiou]/.test(kind) ? "an" : "a"} ${kind}` : "a"} job.`,
        `Job retry by ${actor}`,
      );
    }
    case "worksheets.export.authorized": {
      const rows = count("row_count");
      const format =
        event.metadata.format === "xlsx"
          ? "Excel"
          : event.metadata.format === "csv"
            ? "CSV"
            : null;
      const what =
        event.metadata.format === "template"
          ? "a sheet template"
          : `a sheet${rows === null ? "" : ` with ${rows} row${rows === 1 ? "" : "s"}`}${format ? ` as ${format}` : ""}`;
      return result(
        `${actor} was authorized to export ${what}.`,
        `Sheet export by ${actor}`,
      );
    }
    case "worksheets.opened_on_leave": {
      const opened = count("opened_count");
      const path =
        typeof event.metadata.path === "string" &&
        Object.hasOwn(leavePaths, event.metadata.path)
          ? ` ${leavePaths[event.metadata.path]}`
          : "";
      return result(
        opened === null
          ? `${subject}'s private sheets opened read-only${path}.`
          : opened === 1
            ? `${subject}'s private sheet opened read-only${path}.`
            : `${subject}'s ${opened} private sheets opened read-only${path}.`,
        `Opening ${subject}'s sheets`,
      );
    }
    case "worksheets.import.file_parsed": {
      const rows = count("row_count");
      const reason =
        typeof event.metadata.reason === "string" &&
        Object.hasOwn(importReasons, event.metadata.reason)
          ? ` ${importReasons[event.metadata.reason]}`
          : "";
      return event.outcome === "success"
        ? `${actor}'s Excel file was read for a sheet import${rows === null ? "" : `, with ${rows} row${rows === 1 ? "" : "s"}`}.`
        : `${result("", `Excel file check for ${actor}`)}${reason}`;
    }
    default:
      return "Other security event";
  }
}
