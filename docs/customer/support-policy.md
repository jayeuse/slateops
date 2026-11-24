# Slate Operations support policy

> **Draft: not legal advice. Review before use.**
>
> This policy belongs to the [setup and support agreement](service-agreement.md). If the two differ, the agreement applies.
>
> **Blanks to fill:** [support contact], [support hours], [time zone], [response time], [urgent response time], [visits per year], [owner legal name].
>
> **A Philippine lawyer must check:** that the response times are targets and not guarantees, and that the remote-access consent in section 4 is enough under the Data Privacy Act of 2012 (Republic Act 10173).

## 1. Who gives support

[owner legal name] gives support. Contact: [support contact].

## 2. When

- Support hours: [support hours], [time zone].
- First reply to a normal request: within [response time] during support hours.
- First reply to an urgent request: within [urgent response time] during support hours.
- These times are targets, not guarantees.

A request is **urgent** when nobody can sign in, or when the app or a backup fails for everybody.

## 3. What support includes

1. Answers to questions about the app and its use.
2. Help with problems in the installation that the Provider set up.
3. Installation of published updates by hand. Early builds get no update prompt in the app.
4. Help with backups, and a restore when the Customer asks for one. The Provider does the restore through a remote session ([plan 8.4](../plans/windows-installer.md#84-restore-in-v1)). Unverified: no restore has been tested on Windows yet ([Deployment architecture](../architecture/12-deployment-architecture.md#deployment-state-map)).
5. Up to [visits per year] visits on site each support year.

The [setup and support agreement](service-agreement.md), section 8, lists what support does not cover.

## 4. How to ask for help

1. Write to [support contact]. Say what you did, what you expected, and what happened.
2. If the problem is with setup or the server PC, open the Start menu and select **Slate Operations - Save report**. Send the zip file that it saves on your desktop ([plan 10.6](../plans/windows-installer.md#106-save-report)).
3. The report replaces passwords, keys, email addresses and user names. It is designed to hold no business records (unverified for the logs of third-party parts). Nothing is sent automatically ([plan 10.6](../plans/windows-installer.md#106-save-report)).

**Remote sessions.** The Provider connects to your PC only when you ask for it and agree to the session. You can stop the session at any time. The Provider uses the session only for the support task.

## 5. What the Customer does

1. Keep the server PC on and connected to the office network.
2. Keep the backup drive connected, and tell the Provider about a failed-backup warning.
3. Keep the printed or saved recovery key in a safe place. Without it, a backup cannot be read if the PC's disk is lost ([plan 8.3](../plans/windows-installer.md#83-recovery-key)).
4. Give the Provider access to the PC when a support task needs it.
