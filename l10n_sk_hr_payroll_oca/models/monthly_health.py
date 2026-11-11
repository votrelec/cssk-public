# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Health-only monthly differences before the native categories and tax base."""
from calendar import monthrange
from copy import deepcopy

from odoo import models

from odoo.addons.l10n_sk_hr_payroll_base.fund_assessment import (
    fund_assessment,
    index_assessments,
)
from odoo.addons.l10n_sk_hr_payroll_base.monthly_health import (
    health_policy,
    health_total,
    monthly_health,
    number,
)

HEALTH_CODES = frozenset({"HEALTH", "HEALTHEMPLOYER", "HEALTHDOPLATOK"})
COMPONENTS = {
    "HEALTH": "employee", "HEALTHEMPLOYER": "employer", "HEALTHDOPLATOK": "topup",
}


class MonthlyHealthPayslip(models.Model):
    _inherit = "hr.payslip"

    def l10n_sk_monthly_health_facts(self, version, inputs, worked_days):
        """Explicit current policy; no old premium is inverted into an income."""
        self.ensure_one()
        day = self.date_from
        calendar = version._l10n_sk_health_calendar_context(day)
        month_days = monthrange(day.year, day.month)[1]
        days = version._l10n_sk_month_employed_days(day)
        minimum_days = calendar["minimum_days"] if calendar else days
        if not calendar:
            if "PN_DAYS" in inputs.dict:
                pn = inputs.PN_DAYS.amount
            elif "PN" in worked_days.dict:
                split = self.l10n_sk_pn_split(0, 0)
                pn = split[2] if split else abs(worked_days.dict["PN"].number_of_days)
            else:
                pn = 0
            if pn != int(pn):
                return None
            minimum_days = max(0, days - int(pn))
        disabled = version.l10n_sk_health_is_disabled(day)
        exempt = version.l10n_sk_health_is_exempt()
        suffix = "_ztp" if disabled else ""
        policy = health_policy(
            employee_rate=self.rule_parameter("l10n_sk_health_rate_employee" + suffix),
            employer_rate=self.rule_parameter("l10n_sk_health_rate_employer" + suffix),
            op_maximum=self.rule_parameter("l10n_sk_health_oop_max"),
            op_phaseout_end=self.rule_parameter("l10n_sk_health_oop_phaseout_end"),
            op_days=calendar["op_employment_days"] if calendar else days,
            month_days=month_days,
            minimum_base=self.rule_parameter("l10n_sk_health_min_base"),
            minimum_days=minimum_days,
            apply_op=bool(
                version.l10n_sk_health_oop_claim
                and version.l10n_sk_employment_form() == "none" and not exempt
                and not (calendar and (
                    calendar["concurrent_other_employment"]
                    or calendar["concurrent_self_employment"]
                ))
            ),
            minimum_exempt=bool(
                version.l10n_sk_health_minimum_is_exempt()
                or version.l10n_sk_health_minimum_is_opted_out()
            ),
            exempt=bool(exempt),
        )
        return {"schema": 1, "policy": policy}

    def _monthly_health_sources(self, policy):
        self.ensure_one()
        profile = self._l10n_sk_fund_profile()
        keys = ("version", "contract_period", "agreement", "pension", "regular",
                "oop", "guarantee_exempt", "health")
        previous, missing, ids = [], [], []
        for peer in self._l10n_sk_monthly_predecessors()._cssk_effective_fund_payslips():
            retained = peer._cssk_recorded_fund_profile()
            records = peer._cssk_recorded_fund_bases()
            if (not retained or not records or any(
                    retained.get(key) != profile.get(key) for key in keys)
                    or not profile.get("version") or peer.credit_note):
                missing.append(peer.id)
                continue
            indexed = index_assessments(records)
            ee = indexed.get(("health", "employee"))
            er = indexed.get(("health", "employer"))
            if not ee or not er:
                missing.append(peer.id)
                continue
            sources = [row["facts"].get("monthly_health") for row in (ee, er)]
            if any(row["facts"].get("monthly_unverified") for row in (ee, er)) or any(
                not isinstance(source, dict) or source.get("schema") != 1
                or source.get("policy") != policy for source in sources
            ):
                missing.append(peer.id)
                continue
            try:
                income = ee["facts"]["income"]
                if number(income) != number(er["facts"]["income"]):
                    raise ValueError("Different health income facts")
                topup = ee["facts"]["topup"]
                previous.append({
                    "income": income, "base": ee["base"], "employer_base": er["base"],
                    "employee": number(ee["amount"]) - number(topup),
                    "employer": er["amount"], "op": ee["facts"]["op"], "topup": topup,
                })
                ids.append(peer.id)
            except (KeyError, ValueError):
                missing.append(peer.id)
        return previous, missing, ids


class MonthlyHealthRule(models.Model):
    _inherit = "hr.salary.rule"

    def _compute_rule(self, localdict):
        localdict.pop("l10n_sk_health_minimum_record", None)
        values = super()._compute_rule(localdict)
        slip = localdict.get("payslip")
        if (not slip or self.code not in HEALTH_CODES
                or not slip._l10n_sk_is_recording_funds() or slip.credit_note):
            return values
        native = -values["amount"] if self.code != "HEALTHEMPLOYER" else values["amount"]
        if self.code in {"HEALTH", "HEALTHEMPLOYER"}:
            localdict["l10n_sk_health_native_" + COMPONENTS[self.code]] = native
        record = localdict.get(
            "l10n_sk_fund_record" if self.code != "HEALTHDOPLATOK"
            else "l10n_sk_health_minimum_record"
        )
        if not isinstance(record, dict):
            return values
        source = record.get("facts", {}).get("monthly_health")
        if not isinstance(source, dict) or not isinstance(source.get("policy"), dict):
            self._monthly_health_unverified(localdict, record, True)
            return values
        policy = source["policy"]
        previous, missing, ids = slip._monthly_health_sources(policy)
        # Verify the entire health set before the first component is changed.
        rules = slip.struct_id.get_all_rules().filtered(lambda row: row.code in HEALTH_CODES)
        canonical = len(rules) == 3 and all(
            rule._l10n_sk_is_canonical_fund_rule() for rule in rules
        )
        try:
            standalone = health_total(record["facts"]["income"], policy)
            expected = standalone[COMPONENTS[self.code]]
            if (not canonical or values["quantity"] != 1
                    or values["rate"] != 100 or number(native) != expected):
                raise ValueError("Native health rule is not canonical")
            if self.code != "HEALTHDOPLATOK":
                index_assessments([record])
                if number(record["amount"]) != number(native):
                    raise ValueError("Native health amount differs from its recorder")
            if missing:
                raise ValueError("Unverified prior health remuneration")
            assessed = monthly_health(
                income=record["facts"]["income"], policy=policy, previous=previous,
            )
        except ValueError:
            self._monthly_health_unverified(localdict, record, missing or True)
            return values
        source["source_ids"] = ids
        if self.code == "HEALTHDOPLATOK":
            return dict(values, amount=-float(assessed["topup"]))
        facts = deepcopy(record["facts"])
        employee = self.code == "HEALTH"
        if employee:
            facts["op"] = str(assessed["op"])
        amount = assessed["employee" if employee else "employer"]
        localdict["l10n_sk_fund_record"] = fund_assessment(
            fund="health", side="employee" if employee else "employer",
            base=assessed["base" if employee else "employer_base"],
            rate=record["rate"], amount=amount, facts=facts,
        )
        return dict(values, amount=float(amount) * (-1 if employee else 1))

    def _monthly_health_unverified(self, localdict, record, missing):
        if self.code != "HEALTHDOPLATOK":
            record["facts"]["monthly_unverified"] = missing
        else:
            for row in localdict.get("l10n_sk_fund_records", {}).values():
                if row["fund"] == "health":
                    row["facts"]["monthly_unverified"] = missing
