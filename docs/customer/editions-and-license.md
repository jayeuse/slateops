# Slate Operations editions and license files

> **Draft: not legal advice.**
>
> This page tells you what you can use free, what a paid edition adds, and how license files work. Nobody signs it. The Elastic License 2.0, which you accept in the setup wizard, is the agreement for the software.
>
> **Blanks to fill:** [owner legal name], [support contact], [where to get the setup file], [how to pay], [refund terms].

## 1. The software license

1. Slate Operations is licensed under the Elastic License 2.0, in the `LICENSE` file that comes with the software.
2. You can install and use Slate Operations for your own organization. Get the setup file from [where to get the setup file], and follow the [quick start](quick-start.md).
3. You cannot offer Slate Operations to other people as a hosted or managed service.
4. You cannot move, change, disable or go around the license file check.
5. The software comes "as is", as the "No Liability" section of the Elastic License 2.0 says.

## 2. The editions

Every installation starts as Desk, the free edition. A license file unlocks Office or Headquarters ([editions spec](../specs/editions.md); `backend/app/systems/manage/licensing/editions.py:48-62`).

| | Desk | Office | Headquarters |
|---|---|---|---|
| Price (US dollars) | Free | $39 a month or $390 a year | $89 a month or $890 a year |
| Organizations | 1 | 1 | 1 |
| People (administrators and members, active or invited) | 2 | 25 (set by the license file) | 100 (set by the license file) |
| Guests (read only, active or invited) | None | 2 for each person (50) | 2 for each person (200) |
| Published departments | 2 | No limit | No limit |
| Modules in a department | 3 | No limit | No limit |
| Records in a module | 1,000 | No limit | No limit |
| Sheets | 10 | No limit | No limit |
| Rows in a sheet | 1,000 | 10,000 | 10,000 |
| OpenComms, dashboards, reports, automations, Gantt, audit viewer | No | Yes | Yes |
| Backups, updates, audit recording | Yes | Yes | Yes |

Notes:

1. A person or guest counts once for the installation. A disabled person, a removed member and an expired guest do not count. A pending invitation counts. To free its place, disable or delete the person ([administrator guide](administrator-guide.md#5-edition-and-license-file)).
2. Drafts in the Sandbox have no limit. The department and module limits apply when you publish ([editions spec](../specs/editions.md#acceptance-criteria), ED-4).
3. At a limit, Slate Operations blocks only the action that adds a new item. It deletes nothing ([editions spec](../specs/editions.md#outcome)).
4. On Desk, a paid feature shows "&lt;feature&gt;: available in Office" instead of the feature (`frontend/src/components/systems/shared/components/edition-preview.tsx:68`).

## 3. How to buy a license file

1. Write to [support contact]. Tell us your organization name, the edition, and monthly or yearly.
2. Pay: [how to pay].
3. You get a license file by email. The file holds your organization name, the edition, the number of people, and the start and end dates ([editions spec](../specs/editions.md#license-file)).
4. Import the file in **Manage** → **Updates & licensing** → **Import license file**. The [administrator guide](administrator-guide.md) gives the steps.

The license check works with no internet. The file goes to nobody but your server PC.

There is no free trial. Refunds: [refund terms].

## 4. Renewal and the end of a license

Renewal is by hand. Before the end date, buy a new license file and import it.

| State | When | What happens |
|---|---|---|
| Active | From the start date to the end date | Your edition works fully. |
| Grace | Up to 14 days after the end date | Your edition works fully. Administrators see a renew banner. |
| Warning | The next 30 days | Your edition works fully. Everyone sees a warning banner. |
| Ended | After the warning | The installation runs as Desk. If it is above a Desk limit, only administrators can make changes. Everyone can still read. |

Source: [editions spec, States](../specs/editions.md#states); `backend/app/systems/manage/licensing/state.py:31-32`.

No state deletes your data. Import a new license file whose dates are current, and your edition comes back. Import refuses a file that has ended or that starts in the future (`backend/app/systems/manage/licensing/router.py:108-111`; [editions spec](../specs/editions.md#states)).

## 5. Updates

1. Updates are free in every edition.
2. The app shows an update when a newer stable release is published ([administrator guide](administrator-guide.md), chapter 3).
3. To update, run the newer setup file on the server PC. Your license file stays.

## 6. Help

Help is free. Write to [support contact]. The [getting help](getting-help.md) page tells you what to send.

## 7. Your data

Your data stays on your server PC and your backup drive. [owner legal name] does not get a copy. The [data and privacy statement](data-and-privacy.md) gives the details.
