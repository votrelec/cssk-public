# Copyright 2026 Data Dance s.r.o.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""SK MVP / MVPP — Mesačný výkaz poistného a príspevkov (monthly social).

Filed to the Sociálna poisťovňa (ns http://socpoist.sk/xsd/mvpp2026). Unlike the
CZ PVPOJ, MVPP is BOTH an employer-aggregate summary (``poistne``) AND a full
per-employee annex (``priloha/poistneZamestnancov/poistneZamestnanca``, one row
per employee) — which maps directly onto ``cssk.payroll.employee.declaration``.

Fund → rule-code mapping (from ``l10n_sk_hr_payroll_oca`` /
``l10n_sk_hr_payroll_ee``), employer = ``*Zamtel``, employee = ``*Zamnec``:

======  ================================  =====================  ==================
Fund    Meaning                           Employer (Zamtel)      Employee (Zamnec)
======  ================================  =====================  ==================
np      nemocenské (sickness)             SICKEMPLOYER           SICK
sp      starobné + SDS (old-age)          PENSIONEMPLOYER        PENSION
ip      invalidné (disability)            DISABILITYEMPLOYER     DISABILITY
pvn     v nezamestnanosti (unemployment)  UNEMPLOYMENTEMPLOYER   UNEMPLOYMENT
up      úrazové (accident)                ACCIDENT               — (unused)
gp      garančné (guarantee)              GUARANTEEEMPLOYER      — (unused)
rfs     rezervný fond solidarity          RESERVEFUNDEMPLOYER    — (unused)
pfp     skrátená práca (kurzarbeit)       SHORTTIMEEMPLOYER      — (n/a)
======  ================================  =====================  ==================

``spoluPoistne`` ← ``SOCIALEMPLOYERTOTAL`` + ``SOCIALEMPLOYEETOTAL``.
"""
from decimal import ROUND_DOWN, Decimal

from odoo import _, fields, models
from odoo.exceptions import UserError

# fund element -> (employer rule code, employee rule code or None)
FUND_MAP = [
    ("np", "SICKEMPLOYER", "SICK"),
    ("sp", "PENSIONEMPLOYER", "PENSION"),
    ("ip", "DISABILITYEMPLOYER", "DISABILITY"),
    ("pvn", "UNEMPLOYMENTEMPLOYER", "UNEMPLOYMENT"),
    ("up", "ACCIDENT", None),
    ("gp", "GUARANTEEEMPLOYER", None),
    ("rfs", "RESERVEFUNDEMPLOYER", None),
]

# Wire fields belong to this form; the shared adapter validates and reads the
# actual bases. A legally absent rule is zero, a present rule without its
# recorded base is missing evidence and follows the framework's legacy policy.
FUND_BASE_MAP = {
    ("sickness", "employer"): ("vzNp", "SICKEMPLOYER"),
    ("pension", "employer"): ("vzSp", "PENSIONEMPLOYER"),
    ("disability", "employer"): ("vzIp", "DISABILITYEMPLOYER"),
    ("unemployment", "employer"): ("vzPvn", "UNEMPLOYMENTEMPLOYER"),
    ("accident", "employer"): ("vzUp", "ACCIDENT"),
    ("guarantee", "employer"): ("vzGp", "GUARANTEEEMPLOYER"),
    ("reserve", "employer"): ("vzRfs", "RESERVEFUNDEMPLOYER"),
    ("sickness", "employee"): ("vzZecNp", "SICK"),
    ("pension", "employee"): ("vzZecSp", "PENSION"),
    ("disability", "employee"): ("vzZecIp", "DISABILITY"),
    ("unemployment", "employee"): ("vzZecPvn", "UNEMPLOYMENT"),
    ("shorttime", "employer"): ("vzPfp", "SHORTTIMEEMPLOYER"),
}

# Dohoda agreement types. Their payslips belong here only with REGULAR income;
# irregular-income dohody are reported on the VPP. l10n_sk_hr_payroll_vpp holds
# the mirror of this predicate, and the two must stay complements: a payslip on
# both forms is reported twice.
AGREEMENTS = ("dovp", "dopc", "dobps")

# employment form -> MVP typZec relationship code (pravidelný príjem).
TYP_ZEC = {
    "none": "ZEC",     # zamestnanec v pracovnom pomere
    "dovp": "ZECD1",   # DoVP - pravidelný príjem
    "dopc": "ZECD2",   # DoPČ - pravidelný príjem
    "dobps": "ZECD3",  # DoBPŠ - pravidelný príjem
}


class L10nSkMvp(models.Model):
    _name = "l10n.sk.mvp"
    _inherit = ["cssk.payroll.declaration.mixin", "mail.thread",
                "mail.activity.mixin"]
    _description = "SK MVP monthly social-insurance statement"
    _order = "date_from desc, id desc"

    _report_code = "sk_mvp"
    _country_code = "SK"
    _xml_name_fallback = "mvpp"

    # The company field is required for every Sociálna poisťovňa filing but
    # appears on no company form (several modules declare it, and one view
    # per module would show the input several times). Edit it here instead.
    sp_vs = fields.Char(
        related="company_id.l10n_sk_sp_vs", readonly=False,
        string="Sociálna poisťovňa variable symbol",
        help="10-digit number the Sociálna poisťovňa assigned to the "
        "company. It is stored on the company and shared by every Sociálna "
        "poisťovňa filing (MVP, VPP, ELDP, RLFO).")

    # ------------------------------------------------------------------
    # Scope: everything except dohody with irregular income (those are VPP).
    # ------------------------------------------------------------------
    def _l10n_sk_relationship(self, payslip):
        """``(agreement type, regular income)`` of the contract *payslip* was
        computed on — its own version, not the employee's current one, so a
        later edit of the employee card does not reclassify a past period."""
        version = self._payslip_version(payslip)
        if not version or "l10n_sk_agreement_type" not in version._fields:
            return "none", True
        version = version.sudo()
        agreement = version.l10n_sk_agreement_type or "none"
        if agreement not in AGREEMENTS:
            return "none", True
        if "l10n_sk_income_regular" not in version._fields:
            return agreement, True
        return agreement, bool(version.l10n_sk_income_regular)

    def _l10n_sk_reports_on_mvp(self, payslip):
        agreement, regular = self._l10n_sk_relationship(payslip)
        return agreement not in AGREEMENTS or regular

    def _get_period_payslips(self):
        slips = super()._get_period_payslips()
        if not slips:
            return slips
        return self._effective_fund_payslips(slips).filtered(
            self._l10n_sk_reports_on_mvp
        )

    def _payslip_fund_records(self, slips):
        recorded, missing = super()._payslip_fund_records(slips)
        for slip in slips:
            if not recorded[slip.id]:
                continue
            charged_codes = set(slip.line_ids.mapped("code"))
            required = {
                key for key, (_field, code) in FUND_BASE_MAP.items()
                if code in charged_codes
            }
            present = {(row["fund"], row["side"]) for row in recorded[slip.id]}
            if not required.issubset(present):
                recorded[slip.id] = False
                missing |= slip
        return recorded, missing

    def _mvp_employee_fund_bases(self, slips):
        """Sum actual bases, never derive a cap or OOP from gross or premiums.

        The common framework owns missing evidence and correction review. Keep
        exact known fragments even when another fragment needs its disclosed
        historical gross fallback. Native refund direction is bridge-owned.
        """
        if slips is None:
            # Rendering retained sheet lines without an installed engine keeps
            # their original gross-based data; there is no live source to read.
            return None
        mapping = {key: field for key, (field, _code) in FUND_BASE_MAP.items()}
        recorded = self._collect_payslip_fund_bases(slips)
        totals = {}
        for slip in slips:
            bucket = totals.setdefault(
                slip.employee_id.id,
                {field: Decimal(0) for field in mapping.values()},
            )
            bases = self._sum_recorded_fund_bases(slip, recorded, mapping)
            if bases is False:
                direction_hook = getattr(slip, "_cssk_fund_record_direction", None)
                direction = direction_hook() if direction_hook else 1
                gross = sum(
                    (Decimal(str(line.total)) for line in slip.line_ids
                     if line.code == "GROSS"),
                    Decimal(0),
                )
                bases = {field: direction * gross for field in mapping.values()}
            for field, base in bases.items():
                bucket[field] += base
        return {
            employee: {
                field: format(
                    abs(value).quantize(Decimal(".01"), rounding=ROUND_DOWN), ".2f"
                )
                for field, value in values.items()
            }
            for employee, values in totals.items()
        }

    def _preflight(self):
        super()._preflight()
        for rec in self:
            company = rec.company_id
            vs = (company.l10n_sk_sp_vs or "").strip()
            if not (vs.isdigit() and len(vs) == 10):
                raise UserError(_(
                    "Company '%(company)s' needs a 10-digit Sociálna poisťovňa "
                    "variable symbol for the MVP <variabilnySymbol> element. "
                    "Fill in 'Sociálna poisťovňa variable symbol' on this "
                    "form.",
                    company=company.display_name))
            if not rec._company_ico(company):
                raise UserError(_(
                    "Company '%(company)s' needs an 8-12 digit IČO "
                    "(Company Registry) for the MVP <identifikator> element.",
                    company=company.display_name))
        return True

    @staticmethod
    def _digits(value):
        return "".join(ch for ch in (value or "") if ch.isdigit())

    def _company_ico(self, company):
        ico = self._digits(company.company_registry)
        return ico if 8 <= len(ico) <= 12 else False

    def _fo_osoba(self):
        """The natural person fulfilling SP obligations (mzdová účtovníčka)."""
        user = self.env.user
        parts = (user.name or "Payroll Odoo").split()
        meno = parts[0] if parts else "Odoo"
        priezvisko = parts[-1] if len(parts) > 1 else "Payroll"
        return {
            "priezvisko": priezvisko[:36] or "Payroll",
            "meno": meno[:24] or "Odoo",
            "tel": (self.company_id.phone or "")[:50],
            "mail": (self.company_id.email or user.email or "")[:255],
            "zostavil": (user.name or "Odoo")[:30],
        }

    def _declaration_render_context(self, data):
        self.ensure_one()
        agg = data["aggregate"]

        def a(code):
            return abs(round(agg.get(code, 0.0), 2))

        funds = {}
        for elem, er_code, ee_code in FUND_MAP:
            funds[elem] = {
                "zamtel": "%.2f" % a(er_code),
                "zamnec": ("%.2f" % a(ee_code)) if ee_code else None,
            }
        pfp_amount = a("SHORTTIMEEMPLOYER")
        pfp = "%.2f" % pfp_amount
        # Sum the fund rows this form actually reports, NOT the payslip's
        # SOCIALEMPLOYERTOTAL / SOCIALEMPLOYEETOTAL categories. Those
        # categories carry the HEALTH premiums too — HEALTH and HEALTHDOPLATOK
        # sit in SOCIALEMPLOYEE, HEALTHEMPLOYER in SOCIALEMPLOYER — and health
        # insurance is owed to the health insurers, reported separately on
        # dávka 514. Including it here over-stated the premium due to the
        # Sociálna poisťovňa and left the form internally inconsistent, with
        # spoluPoistne exceeding the sum of its own fund rows.
        spolu_amount = pfp_amount + sum(
            a(er_code) + (a(ee_code) if ee_code else 0.0)
            for _elem, er_code, ee_code in FUND_MAP
        )
        spolu = "%.2f" % round(spolu_amount, 2)

        annex = self._build_annex()
        fo = self._fo_osoba()
        payment = self.payment_date or self.date_to
        return {
            "typ_doc": "MVP00001",
            "obdobie": "%02d%04d" % (int(self.month), int(self.year)),
            "den_vyplaty": payment.strftime("%d.%m.%Y"),
            "typ_vykazu": "R",
            "variabilny_symbol": self.company_id.l10n_sk_sp_vs,
            "ico": self._company_ico(self.company_id),
            "nazov": (self.company_id.name or "")[:144],
            "funds": funds,
            "pfp": pfp,
            "spolu_poistne": spolu,
            "annex": annex,
            "fo": fo,
            "datum_vystavenia": fields.Date.context_today(self).strftime(
                "%d.%m.%Y"),
        }

    def _build_annex(self):
        """Per-employee annex rows (pre-formatted for the QWeb template)."""
        self.ensure_one()
        payslips = self._get_period_payslips()
        bases_by_employee = self._mvp_employee_fund_bases(payslips)
        agreement_by_employee = {
            slip.employee_id.id: self._l10n_sk_relationship(slip)[0]
            for slip in payslips or []
        }
        rows = []
        pc = 0
        for line in self._sheet_lines().sorted("sequence"):
            pc += 1
            employee = line.employee_id
            rc = self._digits(employee.identification_id)
            if not (9 <= len(rc) <= 10):
                raise UserError(_(
                    "Employee '%(name)s' needs a 9-10 digit birth number "
                    "in the Identification No. field for the MVP "
                    "per-employee annex.", name=employee.display_name))
            totals = line.values_json or {}

            def t(code):
                return "%.2f" % abs(round(totals.get(code, 0.0), 2))

            bases = bases_by_employee[employee.id] if bases_by_employee is not None else {
                field: "%.2f" % abs(round(line.vz_base, 2))
                for field, _code in FUND_BASE_MAP.values()
            }
            rows.append({
                "pc": pc,
                "rc": rc,
                "poc_dni": line.insured_days,
                "typ_zec": TYP_ZEC.get(
                    agreement_by_employee.get(employee.id), "ZEC"),
                "vynimka_vz": "0",
                "bases": bases,
                "poc_hodin": "%.2f" % abs(round(line.worked_hours, 2)),
                "np_zamtel": t("SICKEMPLOYER"),
                "np_zamnec": t("SICK"),
                "sp_zamtel": t("PENSIONEMPLOYER"),
                "sp_zamnec": t("PENSION"),
                "ip_zamtel": t("DISABILITYEMPLOYER"),
                "ip_zamnec": t("DISABILITY"),
                "pvn_zamtel": t("UNEMPLOYMENTEMPLOYER"),
                "pvn_zamnec": t("UNEMPLOYMENT"),
                "up_zamtel": t("ACCIDENT"),
                "gp_zamtel": t("GUARANTEEEMPLOYER"),
                "rfs_zamtel": t("RESERVEFUNDEMPLOYER"),
            })
        return rows
