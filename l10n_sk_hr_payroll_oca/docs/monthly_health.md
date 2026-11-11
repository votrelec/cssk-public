# Monthly health advances

Two or more confirmed remunerations for the same employee, company, calendar
month, frozen historical profile and resolved native engagement are reconciled
before native salary categories and TAXBASE. The current income and policy are
recorded explicitly in both health assessment records. Previous income, bases,
raw premiums, OP and minimum top-up come from checked retained records, never
from dividing a premium by its rate. There is no additional ledger.

The target is the existing canonical single-remuneration calculation over total
effective income. The current salary lines and recorded facts contain its signed
difference from actual previous charges. OP, monthly days and the minimum apply
once. For 2026 full-month ordinary employment with OP, 200 + 200 EUR gives a
400 EUR target: OP 340, employee base 60, raw employee premium 3, employer premium
44 and top-up 0. The first top-up 23.45 is returned by the second salary line;
the original confirmed salary lines and retained JSON remain unchanged.
With 2027 dated minimum base 295.22, the final top-up is 0.23 EUR.

Signed fragments are valid evidence. The 514 adapter reconciles the person first
and validates the final XML/TXT amounts. A negative incremental OP or top-up is
not a negative monthly statutory charge. Benefits reduce minimum days while 2N
also reduces OP employment days. Disability and statutory exemptions retain the
existing profile rules. Insurer registration is independent of premium days.

## Canonical extension contract

Before changing any health component, all three health rules must pass
`hr.salary.rule._l10n_sk_is_canonical_fund_rule()`. It compares relevant arithmetic
configuration and normalized Python AST with the read-only shipped XML, cached
per process. A semantically identical copied rule is supported; XML identity,
display names and agreeing custom metadata are insufficient proof. Each actual
native amount must also agree with its explicit recorder and canonical current
source calculation before an override. Access failures propagate.

The engine bridge owns `_l10n_sk_monthly_predecessors()` and effective native
refund pairs. An implicit `contract_id=False` uses the resolved frozen version;
False is never treated as an engagement identity. A native copied refund retains
the exact original signed salary fragments. Its early source identity requires
the native `_copy_refund_payslip()` hook (OCA payroll PR 332). No custom
`refund_sheet()` implementation or public context bypass is introduced.

Different historical profiles, unsupported source days, legacy records without
the explicit monthly facts, custom formulas, and an orphaned dependent fragment
cannot establish an exact next difference. Preserve the native current charges
and mark the source as unverified for the shared original/corrective review
policy. Allocation across other employers, multiple HR cards and different
engagement profiles is a separate boundary; this calculation does not claim
such an allocation or a complete GL, income tax, bonus or NET settlement.
The form names multiple HR cards for review. Checked actual records marked
`monthly_unverified` remain monetary evidence: originals carry a named warning,
corrections require the existing explicit review and audit identity. They do not
silently switch to a gross-derived amount or alter filed attachments.

Legal basis: Act 580/2004, [section 16(16–18) and section 16a](https://static.slov-lex.sk/static/SK/ZZ/2004/580/20260701.print.html),
[OP rounding](https://www.dovera.sk/platitel/zamestnavatel/tema-legislativne-informacie/odpocitatelna-polozka),
and [2027 minimum](https://www.dovera.sk/platitel/zamestnavatel/tema-legislativne-informacie/odvody-od-januara-2027).
