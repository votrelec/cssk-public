---
title: Slovak Payroll
summary: The Slovak payroll family in one place — the monthly payslip for a pracovný pomer and the three dohody on either Odoo Enterprise Payroll or the OCA payroll app, with dated statutory rates, leave, the annual tax reconciliation and posting to the general ledger.
verified: 19.0.1.10.2
---

## What it is for {#purpose}

Slovak payroll is delivered as a family of modules. This page describes the
family as a whole; the individual add-ons have short pages that point back
here.

| Module | What it does |
|---|---|
| [module:l10n_sk_hr_payroll_base](module:l10n_sk_hr_payroll_base) (this module) | The four employment forms and one table saying which contributions and entitlements apply to each. Engine-neutral, no screens of its own. |
| [module:l10n_sk_hr_payroll_ee](module:l10n_sk_hr_payroll_ee) | The Slovak payslip on **Odoo Enterprise Payroll**, as an overlay on Odoo's own `l10n_sk_hr_payroll`. |
| [module:l10n_sk_hr_payroll_oca](module:l10n_sk_hr_payroll_oca) | The same payslip on the **OCA payroll app** (`payroll`), for Odoo Community. |
| [module:l10n_sk_hr_payroll_account_ee](module:l10n_sk_hr_payroll_account_ee), [module:l10n_sk_hr_payroll_account_oca](module:l10n_sk_hr_payroll_account_oca) | Posting payslips to the Slovak chart of accounts, one per engine. |
| [module:l10n_sk_hr_payroll_surcharges](module:l10n_sk_hr_payroll_surcharges) | Wage surcharges (*mzdové zvýhodnenia*) and the minimum wage claims of the six *stupne náročnosti*. |
| The statutory reports | See [Reports to the authorities](#declarations). |

The base module itself holds the employment forms and the applicability
table. It installs automatically as a dependency of the engine modules, and
you meet it only through them.

## Choosing an engine {#engines}

Both engines compute the same payslip from the same statutory figures, and the
development tests run identical cases through both and compare the results.
The choice is about which payroll application you run, not about the Slovak
rules.

| | Enterprise (`_ee`) | OCA (`_oca`) |
|---|---|---|
| Payroll app | Odoo Enterprise *Payroll* (`hr_payroll`) with Odoo's Slovak localization `l10n_sk_hr_payroll` | OCA `payroll`, works on Community |
| How it is built | Overlay: Odoo's Slovak structure is kept, its rules are corrected in place and missing rules are added | A complete Slovak salary structure of its own |
| Employment form chosen by | the **structure type** (one per form, all over one structure) | the **salary structure** (one per form, sharing one rule set) |
| Slovak fields shown on | the employee form, *Payroll* tab, group **Slovak Payroll (Data Dance)** | the employee form, *Payroll* tab, and the contract template form: groups **Slovak Payroll**, **Meal Allowance (Slovakia)**, **Agreement (Slovakia)**, **Garnishment (Slovakia)** |
| Absences reach the payslip through | work entry types (*DOVOLENKA*, *PN*, *OCR*, …) | the **Slovak Payroll Code** on the time-off type |
| Income tax on the payslip | two lines (19 % band and the higher bands) plus an *NČZD* line | one line, *Income Tax (advance)* |
| Statutory rates visible at | *Payroll → Configuration → Salary → Rule Parameters* | *Payroll → Configuration → Rule Parameters* (payroll managers) |
| Installs | automatically, when `l10n_sk_hr_payroll` is installed | on purpose |

The Enterprise overlay depends on Odoo's own module and fixes it rather than
replacing it: income tax is computed on the tax base instead of on gross pay,
the health insurance rates are dated, and the non-taxable part, the child tax
bonus, the ZŤP rates, the health minimum-premium top-up, progressive tax bands
and a meal allowance model are added.

## Legal background {#legal}

The figures the payslip uses come from these acts. Paragraph references below
were checked against the consolidated texts in force in October 2026.

- **Employment forms.** A dohoda o vykonaní práce may cover at most 350 hours
  in a calendar year
  ([§ 226 ods. 1 Zákonníka práce](law:sk/2001/311#paragraf-226.odsek-1)), a
  dohoda o pracovnej činnosti at most 10 hours a week
  ([§ 228a ods. 1](law:sk/2001/311#paragraf-228a.odsek-1)), a dohoda o
  brigádnickej práci študentov at most 20 hours a week on average
  ([§ 227 ods. 2](law:sk/2001/311#paragraf-227.odsek-2)).
- **Which funds apply.** Sickness and unemployment insurance cover a
  *zamestnanec* with a regular monthly income
  ([§ 4 ods. 1 zákona o sociálnom poistení](law:sk/2003/461#paragraf-4.odsek-1));
  irregular income is pension-insured only
  ([§ 4 ods. 2](law:sk/2003/461#paragraf-4.odsek-2)). A DoVP or DoPČ holder
  with a starobný, predčasný starobný, invalidný or (at pension age)
  výsluhový dôchodok is pension-insured only as well
  ([§ 4 ods. 1 písm. b)](law:sk/2003/461#paragraf-4.odsek-1.pismeno-b)).
  Unemployment insurance never covers a starobný, predčasný starobný or
  over-70 % invalidný pensioner
  ([§ 19 ods. 3](law:sk/2003/461#paragraf-19.odsek-3)), and after a
  starobný or predčasný starobný dôchodok neither side pays disability
  insurance ([§ 128 ods. 3](law:sk/2003/461#paragraf-128.odsek-3)). The
  short-time work contribution is paid for a pracovný pomer only
  ([§ 128 ods. 1 písm. g)](law:sk/2003/461#paragraf-128.odsek-1.pismeno-g));
  an employer who does not pay it pays unemployment insurance at 1 % instead
  of 0.5 % ([§ 136](law:sk/2003/461#paragraf-136)). A statutory body or its
  member with at least a 50 % share is not a *zamestnanec* for guarantee
  insurance ([§ 4 ods. 4](law:sk/2003/461#paragraf-4.odsek-4)).
- **Social insurance rates** are set in
  [§§ 130–137](law:sk/2003/461#paragraf-130); the assessment base is capped
  at 11 times one twelfth of the general assessment base of the year two
  years earlier, except for accident insurance
  ([§ 138 ods. 10](law:sk/2003/461#paragraf-138.odsek-10)). Each premium is
  rounded down to the cent
  ([§ 129 ods. 2](law:sk/2003/461#paragraf-129.odsek-2)). On an agreement
  with a pensioner or student the base is reduced by the
  *odvodová odpočítateľná položka* of 200 € a month
  ([§ 138a](law:sk/2003/461#paragraf-138a)).
- **Health insurance rates** are 5 % for the employee (2.5 % for a person with
  a disability) under
  [§ 12 ods. 1 zákona o zdravotnom poistení](law:sk/2004/580#paragraf-12.odsek-1),
  and 11 % for the employer (5.5 %) under the transitional provisions
  [§ 38ezg ods. 4](law:sk/2004/580#paragraf-38ezg.odsek-4) (2024–2025) and
  [§ 38ezk](law:sk/2004/580#paragraf-38ezk) (2026–2027). The monthly
  *odpočítateľná položka* is 380 €, reduced by twice the income above 380 €
  and nil from 570 €
  ([§ 16 ods. 16 and 17](law:sk/2004/580#paragraf-16.odsek-16)). The
  monthly *minimálny preddavok zamestnanca* is set in
  [§ 16a](law:sk/2004/580#paragraf-16a), the annual *minimálne poistné* in
  [§ 13b](law:sk/2004/580#paragraf-13b).
- **Income tax.** The monthly advance is computed from the taxable wage less
  the employee's insurance and one twelfth of the non-taxable part per
  taxpayer ([§ 35 ods. 1 zákona o dani z príjmov](law:sk/2003/595#paragraf-35.odsek-1));
  the non-taxable part is 21 times the subsistence minimum, reduced above a
  threshold — by a quarter of the tax base up to 2025 and by a third from
  2026 ([§ 11 ods. 2](law:sk/2003/595#paragraf-11.odsek-2)); the bands are in
  [§ 15](law:sk/2003/595#paragraf-15); the child tax bonus is 100 € a month
  for a child under 15 and 50 € from 15 to 18
  ([§ 33 ods. 1](law:sk/2003/595#paragraf-33.odsek-1)), limited to a
  percentage of the tax base ([§ 33 ods. 6](law:sk/2003/595#paragraf-33.odsek-6))
  and reduced for high earners ([§ 33 ods. 11](law:sk/2003/595#paragraf-33.odsek-11)).
  The annual reconciliation is [§ 38](law:sk/2003/595#paragraf-38).
- **Minimum wage.** The hourly minimum wage is 1/174 of the monthly one
  ([§ 2 ods. 2 zákona o minimálnej mzde](law:sk/2007/663#paragraf-2.odsek-2)).
- **Wage replacements and meals.** Average earnings use the previous calendar
  quarter, with probable earnings below 21 days or 168 hours
  ([§ 134 ods. 3 Zákonníka práce](law:sk/2001/311#paragraf-134.odsek-3)) and
  the minimum wage as a floor ([§ 134 ods. 5](law:sk/2001/311#paragraf-134.odsek-5));
  employer-side obstacles are paid at the rates of
  [§ 142](law:sk/2001/311#paragraf-142); the meal contribution follows
  [§ 152 ods. 3 and 4](law:sk/2001/311#paragraf-152.odsek-3); annual leave is
  [§ 103](law:sk/2001/311#paragraf-103).

## Setting it up {#setup}

1. Install the engine module: on Enterprise, [module:l10n_sk_hr_payroll_ee](module:l10n_sk_hr_payroll_ee)
   installs itself together with Odoo's *Slovakia - Payroll*; on Community,
   install [module:l10n_sk_hr_payroll_oca](module:l10n_sk_hr_payroll_oca).
   Add the accounting bridge if payslips should be posted (see
   [Posting to the general ledger](#accounting)).
2. The company must be in Slovakia. The Slovak time-off types are visible only
   to Slovak companies, and on the Enterprise engine so are the Slovak
   employee fields.
3. Choose the **employment form** on each contract by its structure type
   (Enterprise) or salary structure (OCA):

   | Employment form | Enterprise structure type | OCA salary structure |
   |---|---|---|
   | pracovný pomer | *Slovakia: Employee* | *Slovakia: Regular Pay* |
   | dohoda o vykonaní práce (DoVP) | *Slovakia: DoVP (agreement to perform work)* | *Slovakia: DoVP (agreement to perform work)* |
   | dohoda o pracovnej činnosti (DoPČ) | *Slovakia: DoPČ (agreement on work activity)* | *Slovakia: DoPČ (agreement on work activity)* |
   | dohoda o brigádnickej práci študentov (DoBPŠ) | *Slovakia: DoBPŠ (student work agreement)* | *Slovakia: DoBPŠ (student work agreement)* |

   The **Agreement Type** field follows the choice. A contract may not claim a
   different agreement type than its structure (type); Odoo refuses to save it
   and tells you to change the structure instead.
4. Fill in the employee's Slovak data, described below.

## Employee and contract data {#employees}

| Field | What it does |
|---|---|
| Tax Declaration Signed | The employee signed the *vyhlásenie* with this employer: the monthly non-taxable part and the child tax bonus are applied. Only one employer at a time may apply them. |
| Children < 15y (tax bonus), Children 15–17y (tax bonus) | Number of children for the child tax bonus. |
| ZŤP / Disabled | Halves the health insurance rates (employee and employer). |
| Claim Health OOP | Claims the health *odpočítateľná položka* for a low earner. Shown only for a pracovný pomer. |
| Agreement Type | Set by the structure (type); see [Setting it up](#setup). |
| Regular monthly income | Shown on agreements. Decides the social insurance funds: without a regular income only old-age and disability insurance are paid. Defaults to *off* for a DoVP and *on* for a DoPČ and DoBPŠ; change it to match the agreement. A DoBPŠ never pays sickness or unemployment insurance, whatever this says. |
| Agreement Hours Warning | Appears when the contract's working calendar exceeds the ceiling for the agreement: 350 hours a year for a DoVP (estimated as weekly hours × 52), 10 hours a week for a DoPČ, 20 for a DoBPŠ. |
| Hourly Wage (SK) | OCA engine only: pays the basic wage as worked hours × this rate instead of the monthly wage. The Enterprise engine uses Odoo's own *Wage Type: Hourly* and *Hourly Wage*. |
| Agreement Wage Warning | Appears when the hourly rate of a dohoda is below the minimum hourly wage in force today ([§ 119 ods. 1](law:sk/2001/311#paragraf-119.odsek-1), extended to dohody by [§ 223 ods. 2](law:sk/2001/311#paragraf-223.odsek-2)). A warning only; the payslip is not topped up. |
| Pension granted (SK) | The dôchodok the worker has been granted, if any. A DoVP/DoPČ holder with any of them pays no sickness or unemployment insurance; a starobný, predčasný starobný or over-70 % invalidný pensioner pays no unemployment insurance on any form; after a starobný, predčasný starobný or (at pension age) výsluhový dôchodok neither side pays disability insurance. Survivors' pensions are not listed: they change nothing. |
| OOP Agreement (student/pensioner) | Reduces the old-age, disability and reserve fund base by up to 200 € on an agreement with an eligible pensioner or student. |
| Health-insurance exempt (štátny poistenec) | On an agreement: no health insurance at all, for a student or pensioner insured by the state. |
| Guarantee-insurance exempt (≥50% statutory owner) | No guarantee insurance for a statutory body with at least a 50 % share. |
| Meal Allowance Type, Meal Days / Month | *None*, *Meal voucher* or *Financial contribution*, and the number of days (0 = the worked days of the payslip). |
| Garnishment Dependents | Dependants raising the non-seizable amount of a wage garnishment. |

On the OCA engine the contract additionally carries per-day overrides of the
meal amounts. The Enterprise engine reuses Odoo's own meal voucher amounts for
that purpose.

## How the payslip is computed {#payslip}

In the order the rules run:

1. **Basic wage.** The contract wage, reduced in proportion to the hours of
   absence in the period.
2. **Wage replacements** at average earnings: *Holiday Pay* for leave hours
   (pracovný pomer only), *Paid Work Obstacle Pay* for § 141 obstacles and
   *Employer Work Obstacle Pay (§ 142)* at 100 %, 50 %, 100 % or 60 % for the
   four employer-side reasons. Average hourly earnings are taken from the
   validated payslips of the previous calendar quarter; with fewer than 168
   hours worked there the module uses the contract wage over the period's
   scheduled hours, and never less than the minimum hourly wage.
3. **Wage surcharges and the minimum wage top-up**, when
   [module:l10n_sk_hr_payroll_surcharges](module:l10n_sk_hr_payroll_surcharges)
   is installed.
4. **Gross pay.**
5. **Social insurance**, employee and employer, each fund on the capped base
   and rounded down to the cent. Sickness and unemployment insurance apply
   only with a regular income, and the *Pension granted* field takes them
   (and the disability premium) away where the law does — see
   [What it is for](#purpose). The short-time work contribution is paid for
   a pracovný pomer only; on a dohoda the employer's unemployment rate is
   1 % instead. Accident insurance is uncapped. For a partial employment
   month, the employee limit uses the monthly maximum divided by the month's
   calendar days, rounded down to cents, then multiplied by insured days
   ([§ 138(13)](law:sk/2003/461#paragraf-138.odsek-13)). For five days in March
   2026: 16,764 / 31 → 540.77 per day → 2,703.85. A full month keeps the whole
   monthly limit; the employer's limit is not prorated by this provision.
6. **Health insurance** on the full gross pay, at the standard or ZŤP rate,
   with the *odpočítateľná položka* if claimed. A state-insured agreement
   worker pays none.
7. **Health Insurance Minimum Top-up**: if employee and employer premium
   together fall below the premium on the subsistence minimum (the *minimálny
   preddavok*), the difference is deducted from the employee. There is none
   for a ZŤP employee or a student on a DoBPŠ, and the minimum is reduced in
   proportion to the days of sick leave (the *PN days* input, or else the
   days of the sick leave) and the days outside the contract.
8. **Income Tax Base** = gross pay − employee social and health insurance.
9. **Non-taxable part** (NČZD): the full monthly amount when the declaration
   is signed. The reduction for high incomes is left to the annual
   reconciliation, as § 35 ods. 1 prescribes.
10. **Income tax advance** by the progressive bands of the period.
11. **Child Tax Bonus**: per child by age, each child's bonus reduced above
    the monthly threshold, then limited to the percentage of the tax base for
    the number of children.
12. **Wage Garnishment**, **Sickness Income Compensation** and the **Annual
    Tax Settlement**, when present (see below).
13. **Meal allowance**: the employer contribution and, for vouchers, the
    employee's share.
14. **Net pay.**

**Sickness.** *Sickness Income Compensation* pays the employer's part of sick
leave: 25 % of the daily assessment base for days 1–3 and 55 % from day 4, up
to day 10 in 2025 and day 14 from 2026, with the base capped. The sick days come
from the PN leave or the *Sick-leave days (PN)* input; the daily base must be
entered as the *Sick-leave daily assessment base (DVZ)* input.

**Garnishment.** With
[module:l10n_cssk_hr_payroll_garnishment_base](module:l10n_cssk_hr_payroll_garnishment_base)
and an order on file, the order register computes the deduction. Otherwise
enter the outstanding debt as the *Wage Garnishment (ordinary claim)* or
*Wage Garnishment (priority claim)* input: one claim per payslip, one third
(ordinary) or two thirds (priority) of the net wage above the non-seizable
amount, and everything above three times the basic non-seizable amount.

**Meals.** The employer contribution per day is 55 % of the meal allowance for
a 5–12 hour business trip, rounded up to the cent — the most
§ 152 ods. 3 allows per meal. With *Meal voucher* the employee pays the rest of
a voucher worth 75 % of that allowance, the minimum voucher value under
§ 152 ods. 4. With *Financial contribution* the contribution is paid out with
the net wage.

## Statutory figures {#rates}

All rates and amounts are dated values, so a payslip uses the figure in force
on its date. The values shipped:

| Figure | 2025 | 2026 |
|---|---|---|
| Social insurance, employee | sickness 1.4 %, old-age 4 %, disability 3 %, unemployment 1 % | same |
| Social insurance, employer | sickness 1.4 %, old-age 14 %, disability 3 %, unemployment 0.5 % (1 % on a dohoda), short-time work 0.5 % (pracovný pomer only), guarantee 0.25 %, accident 0.8 %, reserve fund 4.75 % | same |
| Maximum monthly assessment base | 15 730 € | 16 764 € |
| Health insurance, employee (ZŤP) | 4 % (2 %) | 5 % (2.5 %) |
| Health insurance, employer (ZŤP) | 11 % (5.5 %) | 11 % (5.5 %) |
| Health *odpočítateľná položka* | 380 €, nil from 570 € | same |
| Health minimum base (monthly) | 273.99 € | 284.13 € |
| Non-taxable part per taxpayer, monthly / annual | 479.48 € / 5 753.79 € | 497.23 € / 5 966.73 € |
| Tax bands (annual tax base) | 19 % up to 48 441.43 €, 25 % above | 19 % up to 43 983.36 €, 25 % up to 60 349.20 €, 30 % up to 75 010.32 €, 35 % above |
| Child tax bonus per month | 100 € under 15, 50 € from 15 to 18 | same |
| Child tax bonus limit (1 … 6+ children) | 29 / 36 / 43 / 50 / 57 / 64 % of the tax base | same |
| Child tax bonus reduced above (annual tax base) | 25 740 € | 27 432 € |
| Minimum wage, monthly / hourly | 816 € / 4.690 € | 915 € / 5.259 € |
| Meal allowance 5–12 h | 8.30 € | 9.30 € |
| Employer-paid sick leave | days 1–10 | days 1–14 |

To roll a figure forward you add a new dated value under
*Payroll → Configuration → Salary → Rule Parameters* (Enterprise) or
*Payroll → Configuration → Rule Parameters* (OCA). The annual NČZD taper and the annual bands are separate parameters
used only by the annual reconciliation.

## Time off {#leave}

The engine modules ship Slovak time-off types, each tied to the payroll code
that decides how the payslip treats it:

| Payroll code | Time-off types | On the payslip |
|---|---|---|
| DOVOLENKA | Holiday | paid at average earnings |
| PN | Sick Leave (PN), Quarantine / Isolation (karanténa) | drives the employer's sick pay |
| OCR | Family Care (OČR) | unpaid by the employer |
| NEPLATENE | Unpaid Leave, Study Leave, unpaid | unpaid |
| OBSTACLE | Paid Work Obstacle, Blood Donation, Study Leave (paid), Public Office, Civic Duty, and three capped obstacles | paid at average earnings |
| PREKAZKA_* | four employer-side obstacles under § 142 | paid at the § 142 percentage |
| MATERSKA, RODICOVSKA, OTCOVSKA | Maternity, Parental, Paternity Leave | unpaid by the employer |

On the OCA engine you can also map your own time-off types by setting their
**Slovak Payroll Code**.

**Annual leave accrual plans.** Three plans accrue leave monthly at 1/12 of
the year: *Statutory annual leave — 4 weeks (20 days)*,
*Annual leave — 5 weeks (25 days), age 33+ / parent* and
*Annual leave — 8 weeks (40 days), teaching staff*. Which one applies is a
legal fact the module cannot derive; assign it per employee through an
allocation (*Time Off → Allocations*). Three alternative plans granting the
whole year on 1 January ship archived.

**Capped leave.** *Short-term family care (OČR) — 14 days/year limit* and three
paid obstacles that require an allocation — medical examination (7 days a
year), accompanying a family member (7 days) and accompanying a disabled child
(10 days) — enforce their annual caps when the leave is booked.

## Annual tax reconciliation {#tax-reconciliation}

*Payroll → Payslips → SK Annual Tax Reconciliation* (on the OCA engine
directly under *Payroll*) holds one record per employee and tax year for the
*ročné zúčtovanie preddavkov na daň*.

1. Create the record for the employee and year. With **Gather from Payslips**
   ticked, **Compute** sums the year's tax bases, withheld advances and paid
   child bonus from the payslips; untick it to enter those totals by hand.
2. Enter what only the employee's documents show: **Spouse Non-taxable Part
   (NČZD)** (the eligible amount, already reduced), **Supplementary Pension
   Contributions (DDS, 3rd pillar)** (capped at 180 €) and **Employee
   Premium**.
3. The record computes the annual non-taxable part with its reduction for high
   incomes, the annual tax by the annual bands, the annual child bonus
   entitlement, and the **Overpayment (+) / Underpayment (−)**.
4. Choose the **Settlement Payslip** — the payslip of the month in which the
   result is settled — and click **Post Settlement**. The result is added to
   that payslip as the *Annual tax reconciliation* input and the payslip is
   recomputed; an overpayment raises the net pay, an underpayment lowers it.

The employee must ask for the reconciliation by 15 February, and the employer
performs it by 31 March and settles it no later than with the April wage
([§ 38 ods. 1](law:sk/2003/595#paragraf-38.odsek-1),
[ods. 6](law:sk/2003/595#paragraf-38.odsek-6)). The module does not track
these dates. The annual health insurance reconciliation is done by the
health insurer, not by the employer, and is not part of the module.

## Posting to the general ledger {#accounting}

[module:l10n_sk_hr_payroll_account_ee](module:l10n_sk_hr_payroll_account_ee)
(Enterprise) and
[module:l10n_sk_hr_payroll_account_oca](module:l10n_sk_hr_payroll_account_oca)
(OCA) wire the Slovak salary rules to the Slovak chart of accounts, so that a
validated payslip posts a balanced journal entry:

| Account | Lines |
|---|---|
| 521000 Mzdové náklady | basic wage, holiday and obstacle pay (employee- and employer-side), reimbursements, and — when the surcharges are installed — the wage surcharges and the minimum-wage top-up (debit) |
| 331000 Zamestnanci | net pay (credit) |
| 336000 Zúčtovanie s orgánmi SP a ZP | employee social and health insurance, the health top-up, and the credit side of every employer contribution |
| 524000 Zákonné sociálne poistenie | employer contributions (debit) |
| 342000 Ostatné priame dane | income tax withheld; the child tax bonus and the annual settlement against it |
| 379000 Iné záväzky | garnishments and other statutory deductions |
| 527000 Zákonné sociálne náklady / 333000 | employer meal contribution against the payable to employees; employer sick pay on 527000 |

- **Enterprise.** Odoo's own `l10n_sk_hr_payroll_account` ships with an empty
  mapping, so on its own it posts nothing. The bridge replaces that mapping;
  Odoo then assigns the accounts per company and creates the salary journal.
  It installs itself when both Odoo's module and the Enterprise overlay are
  installed.
- **OCA.** The accounts are set per company on the salary rules when the
  module is installed, for every company already on the Slovak chart, and
  later whenever a company loads the Slovak chart. Install it on purpose; it
  needs the OCA `payroll_account` module. Choose the **Salary Journal** on the
  contract.
- **Surcharges.** The surcharge rules belong to a module the bridges do not
  depend on. They are mapped when a company is configured, and the
  surcharges module maps them itself when it is installed after the bridge,
  touching no other rule.

## Reports to the authorities {#declarations}

The filings are separate modules built on
[module:l10n_cssk_payroll_declaration_base](module:l10n_cssk_payroll_declaration_base)
and work with either engine:

| Module | Report | Filed to |
|---|---|---|
| [module:l10n_sk_hr_payroll_mvp](module:l10n_sk_hr_payroll_mvp) | Mesačný výkaz poistného a príspevkov | Sociálna poisťovňa |
| [module:l10n_sk_hr_payroll_vpp](module:l10n_sk_hr_payroll_vpp) | Výkaz poistného a príspevkov for irregular income (dohody) | Sociálna poisťovňa |
| [module:l10n_sk_hr_payroll_rlfo](module:l10n_sk_hr_payroll_rlfo) | Registration and deregistration of employees | Sociálna poisťovňa |
| [module:l10n_sk_hr_payroll_eldp](module:l10n_sk_hr_payroll_eldp) | Evidenčný list dôchodkového poistenia | Sociálna poisťovňa |
| [module:l10n_sk_hr_payroll_health](module:l10n_sk_hr_payroll_health) | Mesačný výkaz preddavkov na poistné | health insurers |
| [module:l10n_sk_hr_payroll_monthly_tax_overview](module:l10n_sk_hr_payroll_monthly_tax_overview) | Prehľad o zrazených a odvedených preddavkoch | Finančná správa |
| [module:l10n_sk_hr_payroll_annual_tax_report](module:l10n_sk_hr_payroll_annual_tax_report) | Hlásenie o vyúčtovaní dane | Finančná správa |

## Limitations {#limitations}

- **Minimum hourly wage on a dohoda** is checked only for an hourly rate
  (the OCA *Hourly Wage (SK)*, or the Enterprise hourly wage type), against
  the 40-hour figure; a lump-sum remuneration and the higher floor of an
  employer with a shorter established working week are not checked.
- **Health minimum preddavok.** It is reduced only for ZŤP, a DoBPŠ, sick
  leave and days outside the contract. Other days on which the employee is
  insured by the state (maternity, parental allowance, a pensioner) are not
  known to the module, the sick leave's working days stand in for calendar
  days when no *PN days* input is given, and the choice of an employee with
  several employers not to apply the minimum
  ([§ 16a ods. 5](law:sk/2004/580#paragraf-16a.odsek-5)) is not modelled.
- **Health *odpočítateľná položka*** is not prorated for a partial month and
  reduces only the employee's base.
- **Sick pay** is not taxed on the payslip, the daily assessment base must be
  entered by hand, and the leave's working days stand in for the calendar
  days the law counts.
- **Average earnings** count gross pay less the module's wage replacement
  lines, and test only the 168-hour condition, not the 21-day one.
- **Annual leave.** Unused leave is carried over without limit and never
  lapses ([§ 113](law:sk/2001/311#paragraf-113)); planning when it is taken
  is up to the employer. Until version 19.0.1.18.3 (OCA) / 19.0.1.17.5
  (Enterprise) the plans forfeited it after a year. The upgrade clears a
  pending expiry on existing allocations, but days already forfeited are not
  restored — check them. The
  § 105 entitlement for fewer than 60 worked days is not modelled.
- **Seasonal DoPČ.** The higher deduction for seasonal work is in the data but
  there is no field to mark a seasonal agreement.
- **Both engines.** The second-pillar share of the employer's old-age
  contribution is not shown separately on the payslip.
- **Enterprise overlay.** It replaces the code of Odoo's Slovak rules; after an
  Odoo upgrade, check that nothing new was added upstream.
- The figures are shipped for 2024–2026. Check them against the law before
  using a later period.

## Insurance bases kept with payroll {#recorded-funds}

Each new payslip calculation keeps the insurance bases and charges it used,
including zero charges. Older payslips are not recalculated to fill in missing
information. When an insurance declaration uses an older calculation, its
warning names the affected payslips in the form and in the chatter.

Review that warning before filing. An original declaration can use the previous
gross-based calculation. A correction first requires precise records; for older
payroll you can review the archived payroll, enter a reason and explicitly
confirm the previous calculation on the correction. The form records who
confirmed it and when. Do not recalculate filed payroll just to create records.
Systems that do not yet keep these records continue their existing workflow.

## Reviewed health calendars {#health-calendars}

Before new payroll is calculated, the reviewed calendar must explain the ordinary contract dates effective in that month. Record employment as 2/2P or an actual no-income exclusion as 2N. An empty review does not end a signed ordinary contract. Benefit days may reduce premium days to zero while the registration continues. A missing or conflicting period names the employee and asks for calendar review; the program does not insert days or wages. Agreement and post-employment registrations continue to use their actual 2D/2Y dates.

An HR manager opens an employee's **Health calendars** tab, creates a month,
records the dated source intervals and retains their documentary reference.
Confirm **Entire month reviewed** only when all days and relevant exceptions
are covered. An empty calendar can record no actual agreement registration;
an ordinary contract still needs employment facts or an explicit 2N exclusion.
Intervals stay inside that month; 2Y identifies one actual day. Actual agreement
work/rest-day registration facts must be supplied, rather than inferred from
contract duration or a working-hours schedule.

Confirm review to freeze the source. Use **Create revision** for a change:
the original rows remain, while the new draft needs a complete new review.
The shared reader refuses that unfinished replacement. A calendar is a factual
source, not proof that a registration notice was sent or accepted.

2P records the employment relationship with another employment reason at the
same employer. It does not prove concurrent employers for the section 16a(5)
minimum opt-out. That opt-out needs both the employee's written notice and
reviewed facts about another employer. State-insured status and disability
are separate facts. A partial-month disability fact is retained even if the
employment version was not marked disabled at the start of the month; an
explicit disabled profile cannot silently become a wholly non-disabled month.

2S retains strike participation and requires a corresponding employment span.
It does not by itself establish absence of all income/benefit under section
11(3). Record any reviewed no-income 2N and benefit periods separately; consumers
must not manufacture those day effects merely from the strike notification.

This contribution provides factual day counts and sources. It changes neither
premium formulas nor monthly/registration wire formats. Their adapters use the
same reviewed facts in separate contributions. References: [580/2004 sections
11, 13a and 16a](https://static.slov-lex.sk/static/SK/ZZ/2004/580/20261231.html),
[UDZS 1/2026, guidance 12/14/2014 points 5d/e](https://www.udzs-sk.sk/wp-content/uploads/2026/01/VE_1_2026_sv.pdf).

## Health income exclusions {#health-exclusions}

DoBPS student-agreement income and statutory pensioner DoVP/DoPC receipts are
excluded under section 10b(1)(a) of Act 580/2004. The supported pension profile
`service_at_age` includes the reviewed retirement-age condition; it does not
mean every service pension at any age. An ordinary employment pensioner still
pays employee and employer health premiums, with separate state-insuree relief
from the minimum top-up under sections 11(7)(b) and 16a(2).

Select an individual exemption only for another reviewed legal basis, such as
applicable foreign coverage, and retain its basis/reference on the dated
employment version. A state-insuree label alone cannot exempt ordinary
employment income. Existing manual flags are not automatically invented as
foreign-coverage evidence. New calculations need that review; posted history
must be handled through the separate correction workflow.

Recognised invalidity under section 12(2), footnote 48 (Acts 461/2003 and
328/2002), also establishes the reduced health rate without a second ZTP-card
checkbox. The dated invalidity profile remains distinct from ordinary old-age
or service-at-retirement-age pensions. The calculation does not overwrite the
manual disability field.

The shared base supplies these eligibility decisions to both engines. The
OCA rules apply them without changing OP rounding, premium rates, social OOP
or calendar proration. Other day exceptions and output formats remain separate
contributions. [Act 580/2004 sections 10b, 11 and 16a](https://static.slov-lex.sk/static/SK/ZZ/2004/580/20261231.html).

## Reviewed monthly calculation {#health-calculation}

The payroll rules use the reviewed calendar for OP employment days, concurrent
employer/SZCO facts, monthly disability rates and minimum days. Benefit days do
not shorten OP employment; no-income 2N days do. A written minimum opt-out needs
reviewed concurrent-employer dates. Without a calendar, the existing native PN
minimum workflow remains in use. Disability recognised on one day changes both
monthly rates and removes that month's minimum; recognised pension invalidity
is checked against the calendar just like a manually recorded disability.

The shared OP helper caps the allowance by eligible income, prorates once and
rounds upward to cents, following the insurer's published guidance. Other
same-employer income can affect phase-out without receiving OP. The current
native single-source hook passes its employment income; consolidating separate
remunerations/versions needs their explicit income allocation. It must not
silently treat an executive fee as OP-eligible employment income. This is not
an implementation of those additional multi-source workflows.

The existing premium rounding and other twelve fund formulas remain unchanged.
Concurrent-employer minimum notices also apply to reviewed insured agreements;
they do not grant OP eligibility. The derived minimum-only guard is excluded
from the retained payroll-profile shape so sources posted before this addition
remain exact monthly predecessors. Older payslips and their evidence are not
rewritten to achieve compatibility.
The charging rule retains actual OP/base facts and the bridge retains one
shared health/calendar profile without birth numbers. Declaration consumers
must use the same facts; this contribution does not implement the 514/601 codec.
References: [Act 580/2004 sections 16 and 16a](https://static.slov-lex.sk/static/SK/ZZ/2004/580/20261231.html),
[Dôvera OP, including upward rounding](https://www.dovera.sk/platitel/zamestnavatel/tema-legislativne-informacie/odpocitatelna-polozka).
