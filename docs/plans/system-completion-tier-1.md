# System completion: Tier 1 plan

> **Status: done (2026-10-07), PR #32.** Slices S01 to S29 are delivered; S30's architecture reconciliation is present. [Tier 2](system-completion-tier-2.md) is the continuation and supersedes D4 and the W2b personal regional exclusions. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/system-completion-tier-1.md`.

## Outcome

Before OpenComms, every visible control does real, durable, server-authorized work, or it is not shown. An administrator runs the installation without a command line. The organization's identity (name, logo, look, regional formats) is shared; personal comfort (color mode, text size, density, motion, shortcuts) follows the person. Every request tells the person what happened. Main code: `frontend/src/lib/feedback.ts` and `frontend/src/lib/api-errors.ts` (request feedback), the generic `/files` adapter with record attachments and the Platform department library, the notification bell and shell subscriber, the Appearance page (`users.appearance`), the security policy, admin actions and security events in Access, and backup export and download in Manage. Current architecture is in [the architecture index](../architecture/README.md); unresolved acceptance work is in [known gaps](../reviews/known-gaps.md).

## Workstreams

| ID | Workstream |
|---|---|
| W1 | Remove placeholders and dead sample code |
| W2 | W2a organization look on the server; W2b personal Appearance settings |
| W3 | Access page: W3a security policy (Security tab), W3b admin actions on a person, W3c monitoring |
| W4 | Record attachments and the per-department file library |
| W5 | Backup download, then in-app restore |
| W6 | W6a notifications; W6b request feedback |
| W7 | Organization profile in workspace settings |

## 4. Order of work

"Phase A" to "Phase D" are stages of Tier 1, not sample phases.

| Phase | Work |
|---|---|
| Phase A | W1 removal, first. |
| Phase B | Shared foundations: B1 generic `/files` adapter, B2 feedback rule and shared error mapper with a root Toaster, B3 shell event subscriber and notification adapter, B4 security policy form moved into Access. |
| Phase C | Features W2 to W7. |
| Phase D | W5 in-place restore, after the host runner and installer exist. |

## 7. Decisions

| ID | Decision |
|---|---|
| D1 | The security policy moves from Manage to Access, with a redirect. |
| D2 | The Manage tab keeps the name "Organization". |
| D3 | Comms links to example records show "This example record is not in OpenView". |
| D4 | Superseded by Tier 2 W5: new-installation examples enable purge; existing installations keep their configured value. The `purge_enabled` projection and the disabled-installation UI guard stay. |
| D5 | Personal preferences are one JSONB column (`users.appearance`). |
| D6 | Text size and density are per device. |
| D7 | Color mode for new people is System; existing people keep their value. |
| D8 | A shell event subscriber is allowed (the `frontend/AGENTS.md` rule changed). |
| D9 | Guests do not see the organization contact details. |
| D10 | The 410 rollback route is removed. |
| D11 | An admin MFA reset requires the acting admin's MFA (AAL2). |
| D12 | Session and security-event retention are separate, administrator-editable integer days, 1 to 3650, each default 365, with no indefinite option. Backup retention stays separate. |

## 10. After Tier 1

The order is Tier 2, then OpenComms, then later work. "Tier 4" holds: trigger actions beyond "Set field", triggers that follow relationship links, notification preferences and digests, presence, conversation search, email delivery of reports, and in-place backup restore if the installer is not ready earlier.

## Open items

- Whole-branch and release acceptance for Tier 1 was a separate gate; this plan records no result. Slices S05 and S06 tested and fixed the four suspected bugs of the audit.
- W5b in-place restore (Phase D) was out of scope for this run. Its design: do it after the host runner and the Windows installer exist; take a verified backup before the restore; check that the snapshot matches the current release; stop all services, then replace the volumes; sign out every person; use a host journal as the source of truth, because the database itself is replaced.
- W5c import from another machine is deferred. Secret and role-password reconciliation across machines is the largest unknown.
