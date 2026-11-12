# OCA recording integration

Only compute_sheet receives the in-process recording capability. Direct
get_lines_dict/_get_payslip_lines and JSON-shaped context flags cannot modify
evidence. Each charging rule emits the base/rate/amount it actually used.
Custom rule quantities or invalid optional facts leave evidence missing without
preventing the native calculation. The shared statutory profile is stored once;
restricted birth numbers are not copied into it.

The native refund adapter reads the original evidence and supplies its direction
and effective pairing. Historical records are not backfilled. Frozen original
formula JSON plus AST/runtime comparisons protect this evidence contribution's
arithmetic boundary. Reference-arithmetic fixtures remove the optional
MIN_WAGE_TOPUP rule from their test structure so their named low/subcent inputs
remain those inputs; the surcharge module tests the statutory top-up itself.

## Declaration profile adapter

`_cssk_recorded_fund_profile()` uses the same native refund origin as fund records. Missing or invalid optional evidence returns false, while access failures propagate. The bridge delegates health-profile construction to the version hook and does not duplicate insurer/calendar storage or recalculate an old profile when a declaration reads it.

## Calculation source lifecycle

The engine-neutral base owns `source_fingerprint`, the abstract current-source
check and employee/version coordination. This engine owns generated JSON,
source signature, confirmation timestamp and refund-original reference. The
existing capture writer alone adds `_l10n_sk_fund_capture_metadata()` to the
shared JSON; no second fund ledger or arithmetic reconstruction is introduced.

`_l10n_sk_fund_source_facts()` is a cooperative dict of current calculation
sources, compared only before initial confirmation. It covers native identity,
actual salary/input/worked-day lines, relevant dated parameters and rules,
selected employment facts, health profile/calendar, absences and work calendars.
Providers must extend the dict and matching source-writer coordination for
additional calculation inputs. `_l10n_sk_monthly_predecessors()` returns raw
confirmed same-company/employee end-month peers, including unsupported straddlers
and refunds. Arithmetic consumers apply effective-pair removal and typed profile
eligibility themselves. Stored predecessor entries contain only IDs and hashes
of identity, salary and retained JSON, avoiding recursive snapshot growth.

`_l10n_sk_lock_fund_payslips()` takes employee epochs first, then sorted payslip
rows FOR NO KEY UPDATE, compatible with source FK KEY SHARE readers. Every
coordinated source writer performs an actual non-key epoch UPDATE; advisory
locks or cache invalidation alone do not refresh a REPEATABLE READ snapshot.
Relevant source changes can therefore raise SerializationFailure. Odoo's RPC
wrapper retries requests; jobs, imports and standalone scripts must roll back
and retry their entire transaction. Czech profiles and unrelated HR notes do
not acquire the Slovak source epoch.

Child creates inspect only their explicit/default new parent: copy() can invoke
create() on the original nonempty recordset. Child writes inspect old and new
parents. Generated values and context defaults cannot grant a lifecycle bypass.
The private generated stamp writer is not an RPC capability.

OCA/payroll 332 provides `_copy_refund_payslip()`. The localization extends it
to establish the original reference before the native without-compute confirm.
It preserves the full copied amounts, including negative incremental health
minimum adjustments, and leaves payment/filing corrections to their workflows.
Stock OCA 2eca6caa has no such hook and cannot prepare this identity; no native
refund_sheet replacement or caller-supplied context bypass is provided.
Retained profile/fund reads never call the current-source check or today's HR.

The structure hook _l10n_sk_fund_parameter_codes() supplies parameter dependencies
to both capture and source writers. Extend it for rules using helper methods
or dynamic codes; merely hashing the resulting profile cannot prevent a stale
REPEATABLE READ transaction from missing a newly inserted dated value.

The monthly tax extension is imported after the concrete lifecycle and
parameter-code providers. Otherwise the providers' initial implementations
shadow its cooperative overrides even though all classes are present. Test the
executed composition: a changed helper-only allowance parameter and a changed
January pension version must both reject a stale current-version confirmation.
Recalculation must then use the new values. Current source facts include the
live tax configuration, while derived context-only monthly tax output is removed
from the profile used for that fingerprint.

## Monthly tax warning without optional fund evidence

`l10n_sk_monthly_tax_unverified` is a generated readonly/copy-false status bit,
not a second tax ledger. The typed calculation context evaluates profile tax
completeness after native calculation even if an unrelated custom fund rule
leaves the optional fund collection absent. The existing warning ORs this bit
with the retained JSON profile warning. A new copy clears the bit; its next
calculation refreshes it. Public create/write and context defaults reject both
true and false values. Only the private writer can store the calculation's
status, inside the same savepoint as native compute. Retained fund JSON and
missing-record declaration policies are unchanged.

## Atomic closing and native batch order

Closing writes apply non-state values once through cooperative super before
source validation. Each newly closing record is then validated, stamped and
closed in order within one savepoint. The next same-month predecessor signature
therefore sees an earlier closing record in the same transaction. A stale
precomputed batch rolls back all attempted closures and child/header edits.

`action_payslip_done` delegates each pending singleton to native super in order,
retaining native automatic-compute settings and the explicit without-compute
context. It does not reproduce the engine or refund body. Already done/paid
records validate retained identity/salary evidence only; they never compare
against today's HR or later monthly predecessor signatures. Stock OCA has no
paid selection; the paid regression models a payment adapter's selection and
validation cache extension and does not execute an actual payment.

Public create/context defaults cannot establish a new native refund link.
Only the native copy hook's generated original identity permits that link;
existing unchanged legacy links remain historical. All generated-value guards
and lower cooperative field owners still run before closing.

Payslip create/write access is checked before acquiring employee source epochs.
Denied callers therefore cannot change epoch rows or acquire source locks.

# Monthly relationship identity and medical sources

`_l10n_sk_fund_relationship_facts()` records the native employee, company and
legal contract dates. Optional bridges can append assigned relationship
identifiers or a distinct legal title. The complete dictionary participates in
the immutable profile; monthly consumers compare every extension key and their
own relevant fund, health or tax settings. A new wage version alone does not
restart monthly deductions. Older proofs without the key remain compatible on
the same version and contract dates; a different version becomes an unverified
monthly source under the common declaration policy.

PN providers extend `_l10n_sk_fund_source_facts()` and
`_l10n_sk_fund_capture_metadata()` directly. The older social-only extra-facts
hook remains available to older installations but is not the active common
recorder protocol. Concrete source providers load before the final cooperative
monthly-tax consumer. The current source signature includes medical references,
reviewed daily bases, retained calculation evidence and dated PN parameters.
