# Fund evidence protocol

## New source validation and contract coverage

`hr.version._l10n_sk_validate_health_calendar_source(day)` owns engine-neutral registration consistency. Call it only for new payroll calculation and authoritative profile creation, before salary-rule `safe_eval` where possible. Do not call it from `_cssk_recorded_fund_profile`, declaration legacy fallback readers or retained attachment operations. It checks reviewed 2/2P and 2N facts against effective native ordinary contracts, keeping benefit, agreement, exemption and post-contract 2Y meanings separate.

The common retained profile may include `contract_period = {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD" | null}`. Capture these raw source-contract dates, tied to the existing profile version and payroll identity. Do not use a wage version's effective end as the contract end. A monthwide payslip on a contract ending on day 15 only covers that contract through day 15. A later wage version in the same open contract leaves full-month coverage valid. Never backfill an old profile from today's HR card.

The monthly calendar also retains `employment_dates` separately from `insured_dates`: benefits may remove premium days without removing registration; actual 2Y can lie after a contract end. The health form owns its use of these facts for completeness and wire days.

### Enterprise bridge contract

The private Enterprise implementation is not part of this public tree. Its maintainer must mirror the OCA calls before new `compute_sheet` salary evaluation and from the authoritative `_l10n_sk_fund_profile` builder, after native version resolution. Its common profile builder must freeze the same source-contract dates. Its historical/refund reader must return the retained independent profile without calling the live validator. Public tests here execute OCA and engine-neutral base only; this is an integration contract, not an executed Enterprise test.

The base owns the pure signed record shape and abstract identity/salary checks.
Concrete payroll bridges own physical JSON storage and native refund semantics.
Decimal strings preserve the values actually used, including float artefacts
and zero amounts. Consumers apply the relevant statutory cent rounding before
serialising a wire base; they must not print a raw fractional-cent string or
reconstruct a base by dividing a rounded premium. Arithmetic fixes belong to
separate calculation changes with statutory boundary tests.

The declaration framework owns missing-evidence policy. Missing evidence from
an installed recorder differs from an engine without any recorder. A legacy
correction can use a reasoned explicit declaration review without backfilling
or recomputing already filed payroll.

## Retained statutory profile protocol

`_l10n_sk_checked_fund_profile()` checks the existing identity and salary binding before returning an independent copy of the once-retained profile. It does not reclassify historical payroll from today's employee card. `_l10n_sk_health_profile(day)` is the cooperative version hook for country output facts; birth numbers belong to the declaration, outside the common fund profile.
