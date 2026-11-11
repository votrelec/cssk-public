# Copyright 2026 Data Dance s.r.o., votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Apply retained monthly assessments before the native category/NET pipeline."""
from calendar import monthrange
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from odoo import api, fields, models

from odoo.addons.l10n_sk_hr_payroll_base.fund_assessment import (
    fund_assessment, index_assessments,
)
from odoo.addons.l10n_sk_hr_payroll_base.fund_codes import SOCIAL_FUNDS
from odoo.addons.l10n_sk_hr_payroll_base.monthly_assessment import monthly_assessment


class MonthlyFundPayslip(models.Model):
    _inherit = "hr.payslip"

    l10n_sk_monthly_fund_warning = fields.Boolean(
        string="Unverified monthly fund sources",
        compute="_compute_monthly_fund_warning",
    )

    @api.depends("l10n_sk_fund_assessment")
    def _compute_monthly_fund_warning(self):
        for slip in self:
            evidence = slip.l10n_sk_fund_assessment
            evidence = evidence if isinstance(evidence, dict) else {}
            records = evidence.get("records", [])
            records = records if isinstance(records, list) else []
            slip.l10n_sk_monthly_fund_warning = any(
                isinstance(row, dict) and isinstance(row.get("facts"), dict)
                and row["facts"].get("monthly_unverified") for row in records
            )

    def _monthly_confirmed_candidates(self):
        """Raw sources; consumers decide effective pairs and eligible profiles."""
        self.ensure_one()
        reader = getattr(self, "_l10n_sk_monthly_predecessors", None)
        if reader:
            return reader()
        first = self.date_from.replace(day=1)
        last = first.replace(day=monthrange(first.year, first.month)[1])
        return self.search([
            ("id", "!=", self.id), ("company_id", "=", self.company_id.id),
            ("employee_id", "=", self.employee_id.id),
            ("date_to", ">=", first), ("date_to", "<=", last),
            ("state", "in", ("done", "paid")),
        ], order="id")

    def _monthly_social_sources(self, record):
        """Exact same native relationship only; broader allocation is separate.

        Do not consume unrelated draft calculations or reconstruct old income
        from premiums. Native complete refund pairs are removed by the engine.
        """
        self.ensure_one()
        peers = self._monthly_confirmed_candidates()._cssk_effective_fund_payslips()
        rows, missing = [], []
        current_profile = self._l10n_sk_fund_profile()
        keys = ("agreement", "pension", "regular", "oop", "guarantee_exempt")
        for peer in peers:
            records = peer._cssk_recorded_fund_bases()
            profile = peer._cssk_recorded_fund_profile()
            if not records or not profile or profile.get("version") != current_profile["version"] or any(
                profile.get(key) != current_profile.get(key) for key in keys
            ):
                missing.append(peer.id)
                continue
            indexed = index_assessments(records)
            prior = indexed.get((record["fund"], record["side"]))
            source = prior.get("facts", {}).get("monthly") if prior else None
            if (not isinstance(source, dict) or source.get("income") is None
                    or any(source.get(key) != record["facts"]["monthly"].get(key)
                           for key in ("maximum", "deduction"))
                    or prior["facts"].get("monthly_unverified") or peer.credit_note):
                missing.append(peer.id)
                continue
            rows.append({"income": source["income"], "base": prior["base"],
                         "rate": prior["rate"], "amount": prior["amount"]})
        return rows, missing

class MonthlyFundSalaryRule(models.Model):
    _inherit = "hr.salary.rule"

    def _compute_rule(self, localdict):
        values = super()._compute_rule(localdict)
        slip = localdict.get("payslip")
        record = localdict.get("l10n_sk_fund_record")
        if not slip or not isinstance(record, dict) or slip.credit_note:
            return values
        try:
            index_assessments([record])
        except ValueError:
            # Preserve the native custom calculation and the recorder's own
            # missing-metadata policy; never turn it into a monthly opt-in.
            return values
        if (record.get("fund"), record.get("side")) not in SOCIAL_FUNDS.values():
            return values
        if not self._l10n_sk_is_canonical_fund_rule():
            return values
        source = record["facts"].get("monthly")
        if not isinstance(source, dict) or set(source) != {"income", "maximum", "deduction"}:
            return values
        if values["quantity"] != 1 or values["rate"] != 100:
            return values
        native_charge = -values["amount"] if record["side"] == "employee" else values["amount"]
        if slip.company_id.currency_id.compare_amounts(float(record["amount"]), native_charge):
            # This check must precede the override: otherwise changing both
            # values and metadata would hide a custom charge from the recorder.
            return values
        previous, missing = slip._monthly_social_sources(record)
        facts = deepcopy(record["facts"])
        if not missing and source["deduction"]:
            try:
                income = Decimal(str(source["income"]))
                prior_income = sum((Decimal(str(row["income"])) for row in previous), Decimal(0))
                deduction = Decimal(str(source["deduction"]))
                if income >= 0 and prior_income >= 0 and deduction >= 0:
                    facts["monthly"]["used"] = str(
                        min(prior_income + income, deduction) - min(prior_income, deduction)
                    )
            except (InvalidOperation, ValueError, TypeError):
                missing = True
        if missing:
            facts["monthly_unverified"] = missing
        elif previous:
            try:
                assessed = monthly_assessment(
                    income=source["income"], rate=record["rate"],
                    maximum=source["maximum"], deduction=source["deduction"],
                    previous=previous,
                )
            except ValueError:
                facts["monthly_unverified"] = True
            else:
                sign = -1 if record["side"] == "employee" else 1
                values = dict(values, amount=sign * float(assessed["amount"]))
                record = dict(record, **assessed)
        localdict["l10n_sk_fund_record"] = fund_assessment(
            fund=record["fund"], side=record["side"], base=record["base"],
            rate=record["rate"], amount=record["amount"], facts=facts,
        )
        return values
