Native arithmetic reference
===========================

``native_fund_rules.json`` freezes the fifteen fund/health-minimum amount
formulas from ``Data-Dance/cssk-public`` commit
``481955b7ff0d290c710173db799ab7ccc1c564e5``:
``l10n_sk_hr_payroll_oca/data/hr_salary_rule_data.xml``.

These are XML field bodies; decode XML entities before executing the reference.
They deliberately retain the existing rounding and OOP/cap order. A disclosed
arithmetic correction must review its changed expected amounts separately;
this reference must not silently follow the implementation being tested.

The separate health-eligibility FIX leaves this JSON unchanged. AST parity
pins the twelve unaffected rules. Full runtime parity still covers ordinary
non-exempt sub-cent and signed inputs. The three changed health eligibility
rules are checked independently against student/pension agreements, pensioner
employment, ordinary minimum top-up and individually evidenced exclusions.
