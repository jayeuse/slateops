# Sample organization packs: research-based design

> **Status: done (2026-10-30) for all seven packs; Harbor and School through Phase G, the other five in PR #71. The Harbor field-service revision (Order of work, item 8) remains proposed.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/sample-organization-packs.md`.

## Outcome

Seven sample organization packs give the [UI-equivalent sample data](ui-equivalent-sample-data-plan.md#proposed-run-sizes-and-organization-packs) realistic, sourced content for different organization types. Each implemented pack's data files in `backend/operations/sample/packs/<key>/` are its source of truth, not this plan. The research reports are in [sample-organization-research/](sample-organization-research/).

## Rules for every pack

1. **The record budget counts operational records only.** A Standard run has 5,000 to 7,000 records; edges, trigger runs, history updates, Board items and OpenView items count separately.
2. **Each pack has at most 24 modules.** Deferred modules are listed per pack.
3. **Each pack declares its simulated span and sampling scope** in the manifest. Correct ratios between modules matter more than absolute totals.
4. **Record date fields follow the span and the season; `created_at` stays the real run time.**
5. **Automations are set-field rules on the same module.** A research rule that creates a follow-up record becomes a set-field flag plus a planned human step in a later work session.
6. **Counters change in history steps, not every day.** A step sets the counter past the rule's threshold, so the rule fires once.
7. **Separation of duties uses module boundaries.** Planned refusals cross a module or department boundary. A relationship writer needs write access to the source module and read access to the target module; if the creator lacks it, an eligible colleague links the records.
8. **Sensitive records get their own module.** Guests read only modules that are safe to show in full.
9. **Each pack has one named scenario** in which a child record settles part of a parent amount.
10. **Each pack lists the trade phrases it allows in the marker check.** The check blocks `sample`, `test`, `demo`, `dummy`, `fake`, `placeholder`, `lorem`, `ipsum`, `scenario` and `synthetic` everywhere else.
11. **A link to a record in another department is a relationship,** not a typed code. The naming record is the source and links itself after both records exist.

## Packs

| Pack | Country | Span | Named scenario | Deferred modules |
|---|---|---|---|---|
| `school` | United Kingdom (England) | One grading period | Fee Assessment settled in part by a Payment | Enrollment Change, Library Case, Room Booking, Purchase Request |
| `clinic` | United States | One quarter, with flu season | Claim settled in part by a payer Payment | Referral, Goods Receipt (a Purchase Order status), Infection Control Audit |
| `nonprofit` | Philippines | 12 months | Pledge settled in part by Donations; Cash Advance liquidated in part by Expense Lines | Enrollments (a relationship), Quotations (a count field), Volunteer Shifts, Volunteer Hours, Board Meetings |
| `local-government` | Philippines | One calendar year | Order of Payment settled in part by Official Receipts | Occupancy Certificate (a permit status), Council Session, Property and Fleet Asset, Plantilla Position, Personnel Action, Leave Application |
| `fmcg-distributor` | Philippines | One quarter | Sales Invoice settled in part by Collection Receipts | Display Agreement, Return Line (a reason code) |
| `manufacturer` | United States | 6 weeks with one month-end | Customer Invoice settled in part by Customer Payments | BOM Lines (the formula is a long-text field on the Bill of Materials), Incoming Inspection (a Material Lot status), Customer Complaint (an NCR source), Supplier Approval, Controlled Document, Cycle Count, Production Cost Variance |
| `harbor` | Philippines | Unchanged golden master | Unchanged | The field-service research proposes Service Appointments, Refrigerant Log Entries, Warranty Claims, Installation Projects with Change Orders, Collection Activity and Supplier Bills, for a later revision (item 8) |

## Product gaps found by the research

| Gap | Effect on the packs | Where it shows |
| --- | --- | --- |
| Create record, notification and assign task actions do not publish | Follow-up records come from planned human steps | All packs |
| No "today" value in trigger conditions | Due-date and aging rules need a stored counter | All packs |
| No status-transition permission inside a module | A writer can approve their own request; the data shows this only in fields | All packs; six of seven reports |
| No record-level or field-level access | A guest sees every row of a readable module; a sensitive field needs its own module | Clinic, nonprofit, school, FMCG |
| No formula field | Balances, variances and percentages are stored values that people or the simulation set | All packs |
| The six Sandbox organization templates are all business types | School, clinic, nonprofit and government have no template | Sandbox |

## Order of work

Items 1 to 7 (School, the shared engine with admin and reorganization phases, Clinic, Nonprofit, Local government, FMCG distributor, Manufacturer) are done.

8. The Harbor field-service revision, with a new golden master. Proposed, not started.

## Open items

- Order of work item 8 (Harbor field-service revision) is proposed.
- [Known gaps](../reviews/known-gaps.md) links to the product gaps above as sample-pack limits.
