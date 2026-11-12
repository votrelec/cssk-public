=========
Changelog
=========

Unreleased
----------

* Accept a reviewed concurrent-employer minimum notice for insured agreements
  without granting OP eligibility. Keep the retained calendar-profile schema
  unchanged so older posted monthly sources remain valid predecessors.

* Compare complete retained monthly relationship identities across native
  contract versions, preserving the same-version compatibility of older proofs.

* Validate new payroll calendar sources against effective ordinary contracts,
  keeping benefit days, explicit 2N exclusions and actual 2D/2Y roles distinct.
  Retain employment dates separately from premium days.

* Relicensed to **AGPL-3**. Part of a repository-wide move to a single licence:
  everything Data Dance authors is AGPL-3 except the modules that depend on Odoo
  Enterprise, which OEEL forbids from carrying it. What differs between modules
  is now whether they are published, not how they are licensed.

Carry-over to 18.0
~~~~~~~~~~~~~~~~~~

* Not yet ported: scoped payroll-source coordination and current-source
  validation at confirmation. Adapt version ownership to contracts.

* Not yet ported: health514 profile/format integration. Adapt version ownership
  to contracts and rerun profile, insurer, source, refund and retained-file cases.

* Not yet ported: recorded fund evidence, engine-neutral missing-reader policy
  and explicitly reviewed legacy corrections. Adapt contract/engine adapters
  and rerun signed, optional-module, refund and legacy-review scenarios.
* Not yet ported. Adapt the HR-version factual API to contracts and rerun the
  engine-independent, access, revision, source-boundary and concurrency cases.
* Not yet ported. Use contract-scoped profile/evidence fields and apply the same
  eligibility predicates in both engine rules; rerun the profile/output matrix.
* Not yet ported. Adapt version helpers to contracts; mirror engine rules and
  rerun calendar, cent-boundary, access and retained-fund cases.

[19.0.1.8.0] — 2026-11-11
-------------------------

Added
~~~~~

* Engine-neutral current-source signature validation and scoped Slovak
  employment/calendar coordination with transaction retry semantics.

[19.0.1.6.0] — 2026-11-11
-------------------------

Added
~~~~~

* Read-only checked statutory-profile reader bound to the existing identity
  and salary facts, with independent copies for declaration consumers.
* Cooperative health-profile hook on the native employment version for
  country output modules to add historical insurer and OP facts once.

[19.0.1.5.0] — 2026-11-11
-------------------------

Added
~~~~~

* Engine-neutral monthly OP/minimum helpers and cooperative reviewed-calendar
  inputs for payroll rules; separate statutory day counts and shared profile.

Fixed
~~~~~

* Round OP upward after proration; postpone monthly OP for concurrent employers
  or self-employment and distinguish benefit days from no-income 2N days.
* Apply disability-month facts consistently and check recognised invalidity
  against the reviewed calendar without requiring a separate ZTP checkbox.

Changed
~~~~~~~

* Existing native absence fallback remains available without a calendar.
  Multi-source income allocation and declaration codecs are separate work.

[19.0.1.4.0] — 2026-11-11
-------------------------

Added
~~~~~

* Engine-neutral monthly health calendars with reviewed intervals, source
  references, immutable revisions, company access rules and employee UI.
* Separate same-employer 2P and strike 2S facts, alongside 2D/2Y days and
  benefit, disability, state-insured and concurrent-employer facts.
* Dated written minimum opt-out references and a shared factual calendar API.

Changed
~~~~~~~

* This calendar contribution changes no salary-rule arithmetic or recorded
  premium shape. Payroll and declaration consumers remain separate work.

Fixed
~~~~~

* Reject incomplete calendar revisions, profile/calendar disability conflicts
  and a minimum opt-out supported only by another role at the same employer.
* Serialize review/revision against child changes and recheck child boundaries
  when changing their parent. Retain strike facts without inventing no-income days.

[19.0.1.3.1] — 2026-11-11
-------------------------

Added
~~~~~

* Engine-neutral statutory health agreement exclusions and a separate
  pension-state-insuree minimum predicate, with dated individual basis evidence.

Fixed
~~~~~

* Distinguish excluded agreement income from ordinary employment of a pensioner.
  The latter still carries premiums, with relief from the minimum top-up.
* Require a retained individual legal basis for a manually selected exclusion.
  State-insured status alone does not exclude ordinary employment income.
* Recognised ordinary/service invalidity independently establishes the reduced
  health rate under section 12(2), without requiring another ZTP checkbox.

[19.0.1.3.0] — 2026-11-11
-------------------------

Added
~~~~~

* Engine-neutral signed fund-record shape and abstract identity/salary checks.
  Optional invalid evidence remains missing; the payroll engine owns storage.
  Record strings preserve the actual rule precision for consumer rounding.

[19.0.1.2.2] — 2026-11-10
-------------------------

Fixed
~~~~~

- Floor the employee's daily social-insurance maximum before multiplying
  insured calendar days in a partial month (§ 138(13)). Preserve the whole
  monthly maximum for a full month and leave employer limits unchanged.
- Tests: the Enterprise engine has the same payslip test as the OCA engine
  (16 days of January 2026, employee disability premium 259.56).

[19.0.1.2.1] — 2026-11-10
-------------------------

Fixed
~~~~~

- Shared decimal sick-pay arithmetic: four-place downward daily-base rounding
  and upward eurocent compensation rounding, without binary-float artefacts.

[19.0.1.2.0] — 2026-11-09
-------------------------

Added
~~~~~

- ``l10n_sk_employee_social_cap`` and ``l10n_sk_month_employed_ratio``: the
  employee's maximum assessment base for a part-month employment
  (§ 138 ods. 13 zákona 461/2003), shared by both engines.
- The calendar-day sick-pay split in ``sick_pay.py``.

[19.0.1.1.2] — 2026-11-05
-------------------------

Fixed
~~~~~

- Czech catalogue: translated the strings that were still English.

[19.0.1.1.1] — 2026-10-27
-------------------------

**Changed**

- **Slovak translation.** A Slovak catalogue is added for its few labels.

[19.0.1.1.0] — 2026-10-27
-------------------------

**Fixed**

- The applicability table knows the worker's pension: § 4 ods. 1 písm. b) (no sickness or unemployment insurance on a DoVP/DoPČ with a dôchodok), § 19 ods. 3 písm. b) (no unemployment insurance after a starobný, predčasný starobný or over-70 % invalidný dôchodok) and § 128 ods. 3 (no disability premium after a starobný or predčasný starobný dôchodok, or a výsluhový one at pension age). The workaround of unticking *Regular monthly income* for a pensioner is no longer needed.
- The short-time work contribution applies to a pracovný pomer only (§ 128 ods. 1 písm. g) zákona 461/2003), not to a dohoda with a regular income.

[19.0.1.0.1] — 2026-10-27
-------------------------

**Fixed**

- A student on a **DoBPŠ** is no longer charged sickness or unemployment insurance (nor the short-time work contribution), even with a regular monthly income: § 4 ods. 1 písm. a) zákona 461/2003 takes the DoBPŠ out of the definition of a zamestnanec for those funds, and with a regular income the student is pension-insured only (§ 4 ods. 2 písm. b) bod 1). Applies to both payroll engines.
- Pensioners on a DoVP/DoPČ (§ 4 ods. 1 písm. b)) are still charged, because the contract records no pension status; untick *Regular monthly income* for them.
- The note on wage surcharges cites the paragraphs § 223 ods. 2 ZP actually extends to dohody (§§ 122a, 122b, 123; there is no § 122c).

19.0.1.0.0 (2026-08-03)
-----------------------

* Initial release.
* ``applicability`` — one table stating which contributions and entitlements
  apply to which of the four Slovak employment forms, and under which income
  regularity. Odoo-free, so it reads and diffs as the statement of law it is.
* ``hr.version.l10n_sk_applies(concept)`` — reachable from a salary-rule
  condition on either engine, since both hand the version to every rule.
* An unknown concept raises. Returning a default would let a typo look like a
  legal answer, and every caller is deciding whether to charge or pay someone.
