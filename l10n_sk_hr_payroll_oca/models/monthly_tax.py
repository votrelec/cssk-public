# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Reuse native tax formulae on retained monthly bases, once per month.

No second tax ledger: the existing immutable payroll snapshot retains actual
lines and the dated configuration used by this cooperative calculation.
"""
import json
from math import isfinite

from odoo import api, fields, models


_CODES = ("INCOMETAX", "CHILD_BONUS")
_PARAMETERS = {
    "l10n_sk_nczd_monthly", "l10n_sk_income_tax_bands",
    "l10n_sk_child_bonus_under_15", "l10n_sk_child_bonus_15_18",
    "l10n_sk_child_bonus_taper_threshold", "l10n_sk_child_bonus_taper_coeff",
    "l10n_sk_child_bonus_pct_caps",
}


class _TaxCalculation:
    """In-process capability, never an RPC-provided context flag."""

    def __init__(self):
        self.slips = {}


class MonthlyTaxPayslip(models.Model):
    _inherit = "hr.payslip"

    l10n_sk_monthly_tax_warning = fields.Boolean(
        string="Unverified monthly tax sources", compute="_compute_monthly_tax_warning",
    )

    @api.depends("l10n_sk_fund_assessment")
    def _compute_monthly_tax_warning(self):
        for slip in self:
            evidence = slip.l10n_sk_fund_assessment
            profile = evidence.get("profile", {}) if isinstance(evidence, dict) else {}
            tax = profile.get("monthly_tax", {}) if isinstance(profile, dict) else {}
            slip.l10n_sk_monthly_tax_warning = bool(
                tax and (not isinstance(tax, dict) or tax.get("complete") is not True)
            )

    def _monthly_tax_configuration(self):
        version = self._l10n_sk_version()
        return json.loads(json.dumps({
            "version": version.id,
            "signed": version.l10n_sk_tax_declaration_signed,
            "children": [version.l10n_sk_children_under_15, version.l10n_sk_children_15_18],
            "nczd": self.l10n_sk_monthly_nczd(version),
            "parameters": {code: self.rule_parameter(code) for code in sorted(_PARAMETERS)},
        }))

    def _monthly_tax_preflight(self):
        """Read access and historical-source checks outside salary safe_eval."""
        rules = self._get_salary_rules().filtered(lambda rule: rule.code in _CODES)
        canonical = len(rules) == 2 and set(rules.mapped("code")) == set(_CODES) and all(
            rule._l10n_sk_is_canonical_fund_rule() for rule in rules
        )
        config = self._monthly_tax_configuration()
        previous, missing = [], []
        for peer in self._monthly_confirmed_candidates()._cssk_effective_fund_payslips():
            profile = peer._cssk_recorded_fund_profile()
            tax = profile.get("monthly_tax") if isinstance(profile, dict) else None
            lines = peer._monthly_tax_retained_lines(tax)
            if (peer.credit_note or lines is None or tax.get("configuration") != config):
                missing.append(peer.id)
            else:
                previous.append(lines)
        return {"configuration": config, "previous": previous,
                "missing": missing, "canonical": canonical, "expected": {}}

    def _monthly_tax_retained_lines(self, tax):
        """Unknown custom/legacy shapes are missing evidence, not arithmetic."""
        self.ensure_one()
        if not isinstance(tax, dict) or tax.get("complete") is not True:
            return None
        lines = tax.get("lines")
        if not isinstance(lines, dict) or set(lines) != {"TAXBASE", *_CODES}:
            return None
        for code, amount in lines.items():
            if type(amount) not in (int, float) or not isfinite(amount):
                return None
            actual = self.line_ids.filtered(lambda line: line.code == code)
            if len(actual) != 1 or actual.total != amount:
                return None
        return dict(lines)

    def compute_sheet(self):
        lock = getattr(self, "_l10n_sk_lock_fund_payslips", None)
        if lock:
            lock()
        capture = _TaxCalculation()
        for slip in self:
            if slip.struct_id.country_id.code == "SK" and slip._l10n_sk_can_record_funds() and not slip.credit_note:
                capture.slips[slip.id] = slip._monthly_tax_preflight()
        return super(MonthlyTaxPayslip, self.with_context(_l10n_sk_monthly_tax=capture)).compute_sheet()

    def _l10n_sk_fund_source_facts(self):
        facts = super()._l10n_sk_fund_source_facts()
        # Retained output evidence is not a live calculation input. This must
        # produce the same source signature inside and outside compute context.
        if isinstance(facts.get("profile"), dict):
            facts["profile"].pop("monthly_tax", None)
        facts["monthly_tax_configuration"] = self._monthly_tax_configuration()
        return facts

    def _monthly_tax_state(self):
        self.ensure_one()
        capture = self.env.context.get("_l10n_sk_monthly_tax")
        return capture.slips.get(self.id) if isinstance(capture, _TaxCalculation) else None

    def _l10n_sk_monthly_tax_base(self, current):
        state = self._monthly_tax_state()
        if not state or not state["canonical"] or state["missing"]:
            return current
        return current + sum(prior["TAXBASE"] for prior in state["previous"])

    def _l10n_sk_monthly_tax_amount(self, amount, code):
        state = self._monthly_tax_state()
        if not state or not state["canonical"] or state["missing"] or code not in _CODES:
            return amount
        # Section 47 ZDP: mathematical cents, also when calculating an advance.
        # Round the cumulative native result before subtracting actual advances.
        amount = self.company_id.currency_id.round(amount) - sum(
            prior[code] for prior in state["previous"]
        )
        amount = self.company_id.currency_id.round(amount)
        state["expected"][code] = amount
        return amount

    def _l10n_sk_fund_profile(self):
        profile = super()._l10n_sk_fund_profile()
        state = self._monthly_tax_state()
        if not state:
            return profile
        lines = {code: self.line_ids.filtered(lambda line: line.code == code) for code in ("TAXBASE",) + _CODES}
        actual = {code: rows.total if len(rows) == 1 else None for code, rows in lines.items()}
        complete = bool(state["canonical"] and not state["missing"]
                        and all(value is not None for value in actual.values())
                        and all(code in state["expected"] and not self.company_id.currency_id.compare_amounts(
                            actual[code], state["expected"][code]) for code in _CODES))
        profile["monthly_tax"] = {
            "configuration": state["configuration"], "lines": actual,
            "complete": complete, "missing": state["missing"],
        }
        return profile


class MonthlyTaxStructure(models.Model):
    _inherit = "hr.payroll.structure"

    def _l10n_sk_fund_parameter_codes(self):
        parent = getattr(super(), "_l10n_sk_fund_parameter_codes", None)
        codes = parent() if parent else set()
        rules = self.get_structure_with_parents().get_all_rules()
        if any(rule.code in _CODES and rule._l10n_sk_is_canonical_fund_rule() for rule in rules):
            codes |= _PARAMETERS
        return codes
