# Editions and the license file

> **Status: implemented (2026-11-25).** Source: owner decisions DEC-0029, DEC-0050, DEC-0054, DEC-0055 and DEC-0059, and the owner's answers in company record TASK-0127. Nothing here changes the verified architecture documents.

## Outcome

Each installation runs one edition: Desk (free), Office or Headquarters. A signed license file unlocks Office or Headquarters with no internet. Without a license file, the installation is Desk. The administrator sees the edition, the use against each limit and the prices in Manage → Updates & licensing, and imports the license file there.

### Preserved

- Every security control in `SECURITY.md`. Backups, updates and audit recording run in every edition.
- No data is ever deleted because of an edition or a limit. A limit blocks only an action that adds an item above it.
- Development and test installations (`ENVIRONMENT=development` or `test`) without a license file run unlimited, so sample packs and the test suites keep working. Production (`ENVIRONMENT=production`) without a license file is Desk.

### Excluded

Payment code (Paddle checkout links are added later, DEC-0055), automatic renewal, binding a license to one machine, the managed cloud plans, and a limit check on lifecycle reopen.

## Editions

| | Desk | Office | Headquarters |
|---|---|---|---|
| Price | Free | $39 a month or $390 a year | $89 a month or $890 a year |
| Organizations | 1 | 1 | 1 |
| Seats (admins and members, active or invited) | 2 | 25 | 100 |
| Guests (active or invited) | 0 | 2 per seat | 2 per seat |
| Published departments | 2 | No limit | No limit |
| Modules per department | 3 | No limit | No limit |
| Records per module | 1,000 | No limit | No limit |
| Sheets | 10 | No limit | No limit |
| Rows per sheet | 1,000 | 10,000 (sheet limit) | 10,000 (sheet limit) |
| OpenComms, dashboards, reports, automations, Gantt, audit viewer | No ("Available in Office") | Yes | Yes |

A seat or guest counts once for the installation. A disabled person, a removed membership and an expired guest do not count; a pending invitation counts until it is removed. The seat count of a license file sets the seats; guests are twice that number.

## License file

One line of text: `<payload>.<signature>`, both base64url without padding. The payload is UTF-8 JSON:

```json
{"v": 1, "id": "<uuid>", "customer": "Acme Ltd", "edition": "office", "seats": 25,
 "starts": "2026-12-01", "ends": "2026-12-31", "issued": "2026-11-30"}
```

The signature is Ed25519 over the payload bytes. The application holds the public keys only. Production accepts only the production key. Development and test also accept the development key, for hands-on passes; the test suites make their own key for each run.

`operations/issue_license.py` issues a file from a private key file. Both private keys live in the owner's `~/.config/slateops-license/`, outside every repository.

## States

Dates are whole UTC days. "Now" is the later of the clock and the latest time the installation has seen, so a clock set back does not extend a license.

| State | When | Effect |
|---|---|---|
| Desk | No license file | Desk limits and gates |
| Active | `starts` ≤ today ≤ `ends` | The edition of the file |
| Grace | Up to 14 days after `ends` | The edition of the file; renew banner |
| Warning | The next 30 days | The edition of the file; warning banner for everyone |
| Ended | After the warning | Desk limits and gates; above any Desk limit, read-only for everyone except administrators |

A file whose `starts` is in the future is refused at import.

## Acceptance criteria

- **ED-1** A valid production-key file imported by the installation owner is stored and the edition shows at once. A file with a bad signature, a development-key file in production, an unknown edition, or `ends` before `starts` is refused with 422 `license_invalid`, and nothing changes.
- **ED-2** Without a license file in production, `GET /api/license` reports Desk; in development and test it reports the unlimited development edition.
- **ED-3** On Desk, inviting a third admin or member is refused with 403 `edition_limit` (`limit: "seats"`); inviting a guest is refused (`limit: "guests"`). Restoring a removed person and changing a guest to a member follow the same rule.
- **ED-4** On Desk, a publish that creates a third live department, or a fourth live module in one department, is refused with 403 `edition_limit`. A publish that creates nothing new succeeds even when the installation is already above a limit.
- **ED-5** On Desk, creating the 1,001st record in a module (form or import) is refused with 403 `edition_limit` (`limit: "records"`).
- **ED-6** On Desk, creating an 11th sheet, or adding the 1,001st row to a sheet (row, import or copy), is refused with 403 `edition_limit`.
- **ED-7** On Desk, the OpenComms, dashboard, report and audit viewer APIs answer 403 `edition_required`; a publish that adds an automation is refused; the automation worker runs no automation. Audit recording continues.
- **ED-8** `operations/create_organization.py` refuses a second organization in every edition.
- **ED-9** In the Ended state above a Desk limit, a member's or guest's write request answers 403 `license_read_only`; an administrator's write succeeds; reads succeed for everyone.
- **ED-10** Manage → Updates & licensing shows the edition, the license state and end date, the use against each limit, the three editions with their prices, and "Import license file". An import error shows the reason.
- **ED-11** On Desk, OpenComms, OpenView dashboards and reports, the Boards Gantt view, the Sandbox automations and the Manage Audit tab show "Available in Office" with a link to the licensing page instead of the feature.
- **ED-12** A banner shows to administrators when a limit reaches 80% or the license is in Grace, to everyone in Warning and in the read-only state, with a link to the licensing page.

## Known items

- Two requests that add the last free seat at the same moment can both pass (no lock on the count).
- Reopening a closed department or module through lifecycle does not check the limits.
- The Gantt view is hidden in the browser only; its data comes from the Boards card API, which every edition keeps.
- On Desk the Manage Audit tab, with its security events, shows the preview. One record's history stays in every edition.
- An edition refusal (403 `edition_required`) never sets the OpenView access latch.
