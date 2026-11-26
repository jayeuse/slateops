# OpenComms plan

> **Status: code slices done (2026-10-22), PR #56; S32 (integrated acceptance and performance proof), S34 (sample Small profiles) and S35 (full-branch review) have no recorded result.** Sections 6 and the S32 scope are kept in full because that work is not done. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/opencomms.md`.

## Outcome

OpenComms is the real-time conversation layer of each organization: channels, categories, direct and group messages, and threads, at `/comms`. The backend is `backend/app/systems/comms/`; the frontend is `frontend/src/components/systems/comms/`. Supabase Realtime carries Comms live events, typing and presence on private topics with ids-only payloads; message content always loads through FastAPI, which applies the one access function. SSE stays for the other pages. The numbered architecture documents take precedence: [API boundaries](../architecture/07-api-architecture.md#opencomms-http-boundary), [lifecycle and durable work](../architecture/09-lifecycle-and-state-management.md#comms-retention-and-durable-work), [recovery](../architecture/15-error-handling-and-recovery.md#opencomms-refusals-and-command-recovery), [security](../architecture/14-security-architecture.md), the [operator boundary](../../infra/supabase/README.md#opencomms-ingress-and-private-publication) and the [sample-pack contract](sample-pack-contract.md#opencomms-controls). This plan replaced the earlier Comms tests and supersedes F9 and I4 in the [Tier 2.5 plan](test-suite-tier-2-5.md).

## 5. Slices

Code and tests cite these slice IDs. S00 Setup: base and Alembic head recorded; S01 Contract v1: API and event shapes, complete capability contract, legacy permission mapping; S02 Measurements and Realtime proofs; S03 Direction contract for the design; S04 Model, in-memory client, settings engine, capabilities; S05 Page split and URL state; S06 Sidebar, categories, navigation; S07 Timeline; S08 Composer; S09 Right pane, threads, people, presence display; S10 Settings dialog with progressive disclosure, access check; S11 Admin tools UI; S12 Notification preferences UI and desktop alert permission; S13 States, accessibility, mobile; S14 Phase A visual finish and behavior map; S15 Schema with tenancy and ordering; S16 Access, capabilities, settings engine, visibility; S17 Conversations, categories, messages, preferences, settings API; S18 Threads, reactions, pins, quotes, files, record references; S19 Search API; S20A Realtime foundation closure: topic kinds and grants, read-only browsers, same-origin route, private publication; S20 Comms events, typing and presence on Realtime; S21 Notifications; S22 Moderation, report queue, lifecycle; S23 Scheduled messages, retention, export; S24 Templates and bulk apply, settings history, join requests; S25 Link previews, SSRF-guarded; S26 HTTP and Realtime adapters, cache, outbox; S27 One connection set per browser and organization, reconnect; S28 Typing and presence UI; S29 Notifications, desktop alerts, badges; S30 Search UI; S31 Admin tools and settings wiring; in-memory engine moved to tests; S32 Fullstack acceptance and performance proof (pending); S33 Documentation.

## 7. Decisions

`D<n>` is an OpenComms decision. `F-D<n>` is a decision in the [Supabase foundation plan](supabase-foundation.md).

| ID | Decision |
|---|---|
| D1 | Looks: tokens and skin hooks, so the page works with every look; `/comms` is in the theme parity test. |
| D2 | The existing controls stay and become real, with common settings first and the rest under a collapsible "Advanced settings". Automation is the one exception (D29). |
| D3 | Guests are read only: no posting, reacting, or starting or joining direct messages. The read-only Realtime policy enforces the same on topics. |
| D4 | Message and reply history are keyset-paged by `seq`; other lists stay offset-paged. |
| D5 | Unaudited tables: read states, counters, member and personal preferences, thread follows, Realtime grants and presence. All carry `org_id` and RLS. Messages stay audited, with the body redacted. |
| D6 | Event payloads are ids only, on private Realtime topics. Comms tables publish no SSE invalidations; the in-app notification a send creates refreshes the recipient's bell over SSE. |
| D7 | Typing goes to grant holders of the conversation. Presence (online, away, offline) is server-originated from heartbeats, per organization. |
| D8 | Conversation model: categories; organization-wide and department channels (D44); direct and group messages (3 to 50 people); one-level threads with follow, state and "Also send to channel"; quote replies. No topics or forums. |
| D9 | Admins create channels. A category or channel may be linked to a department, whose access then carries over. Nothing is created automatically. |
| D10 | Org admins, department managers and groups granted `createChannel` create channels. Any member starts direct and group messages unless `dmRule` limits it. |
| D11 | Notifications: in-app bell, plus desktop alerts and sound while a tab is open; per-conversation levels, keywords, quiet hours, preview text and badges. No email, Web Push or digest. Everything is per organization. |
| D12 | No read receipts. Must-read stays on Boards. |
| D13 | Edit and delete windows are real; default no limit (0). Every edit shows an "edited" marker and keeps its history. Moderator removal is audited and restorable. |
| D14 | Virtualization only on a measured target miss (`@tanstack/react-virtual` approved). |
| D15 | A small safe message renderer, with no new dependency and no raw HTML. |
| D16 | Search covers OpenComms only: who, what, when, where, `has` and `is`. |
| D17 | Retention per organization, keep forever by default, with channel overrides and file retention. Only org admins set it, with a fresh password and an impact preview. Batched individual ORM deletes through `AuditSession`. No legal hold. |
| D18 | Admin tools are one surface; each tool opens on its common task. |
| D19 | Limits: 20 sends per 10 seconds per user per organization; body at most 4,000 characters; at most 10 attachments of 10 MiB each; group messages of 3 to 50 people. |
| D20 | Capacity target 300 concurrent users per installation, with one SSE stream and one Realtime socket per browser and organization (leader tab). Below 200 with correct delivery is a defect; 200 to 300 is a known issue. Levers, changed only with measurements and a SEC-R6 note: Realtime tenant limits (`max_concurrent_users` up to 500; channels per client 100), SSE hub caps, `SERVER_MAX_CONCURRENCY`, database pool size. |
| D21 | Sample executors land in the same commit as each frontend-called route. |
| D22 | Supervised student messages are deferred. |
| D23 | A record reference shows a card only to readers of the module, re-checked on every read; others see "Record unavailable". |
| D24 | Branch `codex/opencomms` from `main` at `6816f2b8` or later. |
| D25 | Mentions: @person among the conversation's readers. @channel and @here need `mentionChannel`; @here reaches online readers only. |
| D26 | Unread counts by query, capped at "99+". |
| D27 | Read and post come from the channel scope and department roles (D44); direct and group messages use membership. Capabilities follow section 7.2, granted by group, never per person, with no deny rules. "Check one person" explains each result. |
| D28 | One branch and one pull request, no mid-run merge. |
| D29 | Automation comes after OpenComms. |
| D30 | Link previews are real, SSRF-guarded and off by default. |
| D31 | Admins export. Direct and group messages are private sources and need a fresh admin password plus a reason. Exports are audited per organization. |
| D32 | Scheduled messages and the report queue are real. |
| D33 | Templates do bulk apply; settings history comes from the audit log, with restore. Join requests were removed with private channels (D44). |
| D34 | After removal, content is refused at once (404). Id-only events can continue for at most the 5-minute token lifetime. The grant row is deleted at once, so a re-join is refused. |
| D35 | Presence covers everyone in the organization, guests included, through one presence topic per organization; it shows on person cards too. |
| D36 | Sharing a readable conversation makes people visible to each other (card, mention, direct message), in `person_visibility.py`, signed off under SEC-R6. |
| D37 | Realtime topics: conversation, own-user and organization presence, named `org:<org_id>:<kind>:<id>` and `org:<id>:presence` (F-D24). Conversation topics need FastAPI-written grant rows, reconciled at token issue. Browsers are read-only on Comms topics. |
| D38 | Browser path: same-origin `/realtime/v1/websocket` to the provider gateway, with the gateway key injected as a header (Caddy in production, the launcher's upgrade proxy in development). |
| D39 | Publish path: FastAPI validates private, ids-only envelopes, discards them on rollback, and submits them after commit through a bounded HTTP publisher to a separate private provider listener. Delivery is best effort; clients repair gaps through authorized reads. The listener is unpublished in production and loopback-only in development. |
| D40 | Realtime client: `@supabase/realtime-js`, measured against the JS budget. |
| D41 | No entitlement gate in this phase; on-premises installations have no limits. |
| D42 | S34 runs the sample Small profiles with the guarded reset of local development application data between them, for that run only; never provider volumes. |
| D43 | Org admins do not read direct or group messages they are not part of: these are absent from the admin's sidebar, bootstrap, search and history (404). Admins still manage every organization and department channel, act on reported messages through the moderation queue, and export private conversations only through D31. |
| D44 | OpenComms is available to every organization member. A channel is organization-wide or belongs to one department, and department roles decide read, post and manage. No channel invitations, join requests, group-shared channels or private channels; hand-picked conversations are direct or group messages. Spec: `docs/specs/opencomms-department-access.md`. |
| D45 | A channel keeps one owner (organization or one department). Channel managers can give read, or read and post, to Access groups and individual people outside the department; grants add to department roles and never give manage. Category grants are inherited by the category's channels; no deny grants. Spec: `docs/specs/opencomms-department-access.md` (addendum). |

### 7.2 D27 capability matrix

Terms:
- A **conversation manager** is an org admin (for conversations the admin can read under D43), the department manager of a channel in that department, the conversation creator while the creator's member row exists, or a person with a `manager` member row (`ManagerSource` in `comms/access.py`). On a channel, member rows are only this manager roster (D44).
- A **poster** has `post` level.
- A **reader** has `read` level.
- Guests are readers only (D3).

| Capability | Allows | Held by default | Grantable to groups at | Default can be turned off for Everyone at | Lockable at workspace |
|---|---|---|---|---|---|
| `react` | Add and remove your own reactions | Every poster | – (on by default) | workspace, category, channel | yes |
| `reply` | Reply in a thread (also when `mode` limits root posts to managers) | Every poster | workspace, category, channel (to give readers in an announcements channel a reply right) | workspace, category, channel | yes |
| `createThread` | Start a thread from a message | Every poster | – | workspace, category, channel | yes |
| `attachFiles` | Attach files (within the file settings, the platform allowlist and the 10 MiB limit) | Every poster | – | workspace, category, channel | yes |
| `linkRecords` | Attach record links (cards still follow D23) | Every poster | – | workspace, category, channel | yes |
| `mentionChannel` | Use @channel and @here | Conversation managers | workspace, category, channel | – (off by default) | yes |
| `pin` | Pin and unpin any message | Conversation managers | workspace, category, channel | – | yes |
| `manageThreads` | Rename, resolve, lock, archive any thread (a thread starter can always resolve and reopen their own thread) | Conversation managers | workspace, category, channel | – | yes |
| `deleteOthersMessages` | Remove anyone's message (tombstone) and restore it | Conversation managers | workspace, category, channel | – | yes |
| `moderate` | Report queue, restrict a person, slow mode, lock or unlock the channel | Conversation managers | workspace, category, channel | – | yes |
| `manageChannel` | Edit settings and the manager roster of a channel, or the members of a direct or group message; archive, restore and duplicate | Conversation managers | category, channel | – | yes |
| `createChannel` | Create channels: a workspace grant means any category; a category grant means that category only. Since D44 a grant creates only department channels, in a department where the holder has a department role (owner, 2026-10-22). Source: `CapabilityInputs.grant_department` in `comms/capabilities.py` | Org admins; department managers for channels of their department, uncategorized or in a category bound to it | workspace, category | – | yes |
| `manageWorkspace` | Workspace settings and locks, retention, export, templates, settings history, capability grants at workspace scope | Org admins only | never | – | – |

Resolution rules:
1. Start with the defaults in the table, then apply scopes in the order workspace, category, channel. A group grant adds the capability at that scope and below; a lower scope never removes a higher grant (no deny rules).
2. For the five capabilities on by default, each scope has an "Everyone" switch; the most specific switch wins, and a workspace lock fixes the workspace value for every lower scope. Group grants add the capability back unless the workspace locks it.
3. Conversation managers hold every conversation capability in their conversations; org admins hold everything in their organization. Neither can be turned off.
4. Guests never hold a capability that writes, even through a group grant.
5. Any poster may @mention a reader of the conversation; @channel and @here need `mentionChannel`, and the mention limit applies.
6. "Check one person" lists every capability with its result and the deciding source.

## 6. Quality targets

Each target has a method. A miss is fixed within the slice. If it cannot be fixed after three different attempts and an analysis pass, the measured number becomes an owner-visible known issue; a miss never stops the run.

| Quality | Target | Method | Slice |
|---|---|---|---|
| Performance: JS | A cold `/comms` load transfers at most 365 KiB of compressed JS. Because the Phase A starting point was above that, each frontend slice grows it by at most 5% over the previous slice, and once the in-memory tools leave production the total ends below the Phase A starting point. Admin tools, the settings dialog and the Realtime client load on demand. | Production static build; Playwright records gzipped JS sizes | S04, S07, S10, S11, S26, S31 |
| Performance: timeline | With 5,000 messages, the newest 50 show within 200 ms of data arriving. A 3,000 px scroll produces at most 2 long tasks over 50 ms (Chromium, 4× CPU throttling). | Playwright + CDP + `PerformanceObserver('longtask')` | S07, S32 |
| Performance: server | Bootstrap for 50 conversations: p95 at most 150 ms. A history page of 50 in a 100,000-message conversation: at most 100 ms. Send: at most 150 ms. Search over 100,000 messages: at most 300 ms. The per-request organization baseline is reported separately from handler time. | pytest on isolated PostgreSQL with synthetic seeded rows; 30 serial samples | S17, S19, S32 |
| Effectiveness | Send-to-visible on the other screen: at most 1,000 ms p95 over 50 sends. Typing shows within 1,000 ms. Offline shows within 150 seconds of the last heartbeat. | S32 timing | S32 |
| Reliability | No lost or duplicated message across a reconnect or token refresh. Idempotent replay. Outbox retry. A scheduled message survives an API restart. A rollback publishes nothing. | Tests in S15, S20A, S20, S23, S26, S27 | listed |
| Isolation | A non-member, a person without a grant, or another organization's member never receives a Comms event, a presence update, a search hit, a file or a notification. After removal, content is refused at once (404); id-only events can continue for at most the token lifetime (5 minutes, D34). | Tests in S15–S21, S20A, S32 | listed |
| Efficiency | Bootstrap and message pages run the same number of SELECTs at every page size. A grant reconcile in the steady state writes nothing. One send writes at most one message, one counter, its mention rows, notification rows only for the S21 recipients, one audit row per audited table, and one publish per topic. | Query counter; reconcile test | S17, S20A, S20 |
| Purge | Purging a 10,000-message conversation completes within the database statement timeout, with a 15-second timing target, without weakening audited individual deletes or confirmation guards. | Measured once on a freed machine | S22, S32 |
| UX | Every scout finding is fixed or recorded as deferred. Each settings tab shows at most six common items. The finish reviewer returns `ship`. Plain copy for any organization in any country. | S14, S10 test, S31 | S10, S14, S31 |
| Host budget (provisional) | At the D20 target, the Realtime container stays at or below 1 GiB resident memory, and the API process grows by at most 512 MiB over its idle baseline. This stands in for the Windows host specification until Phase 4 sets one. | S02, S32 measurements | S02, S32 |

## Open items

- S32: integrated browser and provider acceptance with performance proof. Scope:

  S32 covers, with two real accounts on the production-level Realtime path: send, reply, react and attach; edit and delete; moderator remove and restore; a connection drop during sends that recovers in order with no duplicates; a removed member who stops seeing content at once and stops receiving ids within the token lifetime (D34); and a second organization in another tab that never sees the first organization's events.
- S34 (sample Small profiles) and S35 (full-branch review and gate) have no recorded result here.
- The quality targets in section 6 are targets, not results. The capacity burst and fan-out measurement, the 10,000-message purge timing and the timeline opening measurement have not run.
- After OpenComms: automation that posts to channels, email and push notifications and digests, the cloud free-tier gate, legal hold, custom emoji and media, read receipts and shared channels, supervised student messages (D22), platform-wide message search, a persisted offline outbox, cross-organization unread counts, and the window-focus session curtain.
