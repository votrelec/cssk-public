# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Medical PN identity and reviewed daily bases on native absence records."""

from collections import defaultdict
from datetime import timedelta
from math import isfinite

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.addons.l10n_sk_hr_payroll_base.sick_pay import (
    merge_spans,
    round_sick_pay,
    sick_pay_amount,
    split_sick_days,
)

PN_SOURCE_FIELDS = {
    "employee_id",
    "company_id",
    "state",
    "holiday_status_id",
    "request_date_from",
    "request_date_to",
    "date_from",
    "date_to",
    "l10n_sk_pn_case_reference",
    "l10n_sk_pn_daily_base",
    "l10n_sk_pn_base_reviewed",
    "l10n_sk_pn_base_reference",
}


class Leave(models.Model):
    _inherit = "hr.leave"

    l10n_sk_leave_payroll_code = fields.Selection(
        related="holiday_status_id.l10n_sk_payroll_code", string="Slovak absence code"
    )

    l10n_sk_pn_case_reference = fields.Char(
        string="PN medical case reference",
        copy=False,
        index=True,
        help="Use the same medical reference for continuation and a different reference for a new PN.",
    )
    l10n_sk_pn_daily_base = fields.Float(
        string="Reviewed PN daily base", digits=(16, 4), copy=False
    )
    l10n_sk_pn_base_reviewed = fields.Boolean(
        string="PN daily base reviewed", copy=False
    )
    l10n_sk_pn_base_reference = fields.Char(string="PN daily-base evidence", copy=False)

    def _get_leaves_on_public_holiday(self):
        # PN is a calendar event and may begin and end entirely on rest days.
        # Keep the native no-working-time guard for every other absence type.
        return (
            super()
            ._get_leaves_on_public_holiday()
            .filtered(
                lambda leave: not (
                    leave.company_id.country_id.code == "SK"
                    and leave.holiday_status_id.l10n_sk_payroll_code == "PN"
                )
            )
        )

    @api.constrains(
        "l10n_sk_pn_daily_base", "l10n_sk_pn_base_reviewed", "l10n_sk_pn_base_reference"
    )
    def _check_pn_daily_base(self):
        for leave in self.filtered("l10n_sk_pn_base_reviewed"):
            if (
                not isfinite(leave.l10n_sk_pn_daily_base)
                or leave.l10n_sk_pn_daily_base < 0
                or not (leave.l10n_sk_pn_base_reference or "").strip()
            ):
                raise ValidationError(
                    _(
                        "A reviewed PN daily base needs a finite nonnegative amount and its evidence."
                    )
                )

    def _l10n_sk_lock_pn_employees(self, extra_employees=None):
        employees = self.employee_id | (extra_employees or self.env["hr.employee"])
        locker = getattr(employees, "_l10n_sk_lock_social_source", None)
        if locker:
            locker()

    @api.model_create_multi
    def create(self, values_list):
        defaults = self.default_get(["employee_id"])
        employee_ids = {
            values.get("employee_id", defaults.get("employee_id"))
            for values in values_list
        }
        self._l10n_sk_lock_pn_employees(
            self.env["hr.employee"].browse([ident for ident in employee_ids if ident])
        )
        return super().create(values_list)

    def write(self, values):
        if PN_SOURCE_FIELDS & values.keys():
            self.check_access("write")
            extra = self.env["hr.employee"].browse(values.get("employee_id") or [])
            self._l10n_sk_lock_pn_employees(extra)
        return super().write(values)

    def unlink(self):
        self.check_access("unlink")
        self._l10n_sk_lock_pn_employees()
        return super().unlink()


class Payslip(models.Model):
    _inherit = "hr.payslip"

    def compute_sheet(self):
        # Validate medical evidence before salary-rule safe_eval turns a
        # business UserError into an unreadable Python traceback.
        for slip in self.filtered(lambda row: row.state != "done"):
            version = slip._l10n_sk_version()
            if (
                slip.struct_id.country_id.code == "SK"
                and len(version) == 1
                and version.l10n_sk_applies("SICKNESS_COMPENSATION")
            ):
                daily_input = slip.input_line_ids.filtered(
                    lambda row: row.code == "PN_DVZ"
                )[-1:]
                daily_base = daily_input.amount if daily_input else None
                episodes = slip._l10n_sk_pn_episodes(daily_base)
                manual_days = slip.worked_days_line_ids.filtered(
                    lambda row: row.code == "PN" and row.number_of_days
                ) or slip.input_line_ids.filtered(
                    lambda row: row.code == "PN_DAYS" and row.amount
                )
                if not episodes and manual_days:
                    slip._l10n_sk_pn_checked_manual_base(daily_base)
        return super().compute_sheet()

    def _l10n_sk_pn_checked_manual_base(self, daily_base):
        """An unfilled zero is not a reviewed basis for manual compensation."""
        if daily_base is None or not isfinite(daily_base) or daily_base <= 0:
            raise UserError(
                _(
                    "Record the reviewed daily base and its evidence for each PN medical case."
                )
            )
        return daily_base

    def _l10n_sk_pn_episodes(self, fallback_daily_base=None):
        """Separate new illnesses; join explicitly identified continuations."""
        self.ensure_one()
        leaves = self._l10n_sk_pn_leaves().sorted("request_date_from")
        references = {
            leave.id: (leave.l10n_sk_pn_case_reference or "").strip()
            for leave in leaves
        }
        groups = defaultdict(lambda: self.env["hr.leave"])
        for leave in leaves:
            reference = references[leave.id]
            key = ("reference", reference) if reference else ("leave", leave.id)
            groups[key] |= leave
        groups = {
            key: rows
            for key, rows in groups.items()
            if any(
                row.request_date_from <= self.date_to
                and row.request_date_to >= self.date_from
                for row in rows
            )
        }
        relevant = (
            self.env["hr.leave"].concat(*groups.values())
            if groups
            else self.env["hr.leave"]
        )
        for previous, following in zip(leaves, leaves[1:]):
            if (
                following.request_date_from <= previous.request_date_to
                and (previous in relevant or following in relevant)
                and references[previous.id] != references[following.id]
            ):
                raise UserError(
                    _("Review overlapping dates assigned to distinct PN medical cases.")
                )
            adjoining = (
                following.request_date_from
                == previous.request_date_to + timedelta(days=1)
            )
            if (
                adjoining
                and (previous in relevant or following in relevant)
                and not (references[previous.id] and references[following.id])
            ):
                raise UserError(
                    _(
                        "Identify adjoining PN records as continuation of one medical case or as separate illnesses."
                    )
                )
        episodes = []
        for key, rows in groups.items():
            spans = merge_spans(
                [(row.request_date_from, row.request_date_to) for row in rows]
            )
            if len(spans) != 1:
                raise UserError(
                    _(
                        "Review missing dates within the same PN medical case; do not invent an unrecorded continuation."
                    )
                )
            bases = set(
                rows.filtered("l10n_sk_pn_base_reviewed").mapped(
                    "l10n_sk_pn_daily_base"
                )
            )
            if len(bases) > 1:
                raise UserError(
                    _(
                        "Continuation of one PN must retain one consistent reviewed daily base."
                    )
                )
            if bases:
                daily_base = bases.pop()
            elif (
                fallback_daily_base is not None
                and isfinite(fallback_daily_base)
                and fallback_daily_base > 0
                and len(groups) == 1
            ):
                daily_base = fallback_daily_base
            else:
                raise UserError(
                    _(
                        "Record the reviewed daily base and its evidence for each PN medical case."
                    )
                )
            episodes.append(
                {
                    "reference": key,
                    "start": spans[0][0],
                    "end": spans[0][1],
                    "daily_base": daily_base,
                }
            )
        return episodes

    def l10n_sk_pn_compensation(self, daily_base=None):
        episodes = self._l10n_sk_pn_episodes(daily_base)
        if not episodes:
            return False
        first, last = self._l10n_sk_pn_payment_period()
        total = 0
        for episode in episodes:
            start, end = episode["start"], episode["end"]
            if start > last or end < first:
                continue
            parameter = self.env["hr.rule.parameter"]._get_parameter_value
            tier1, tier2, _days = split_sick_days(
                [(start, end)],
                first,
                last,
                parameter("l10n_sk_pn_tier1_days", start),
                parameter("l10n_sk_pn_employer_days", start),
            )
            capped_base = min(
                episode["daily_base"], parameter("l10n_sk_pn_max_dvz", start)
            )
            total += sick_pay_amount(
                capped_base,
                tier1,
                tier2,
                parameter("l10n_sk_pn_rate_tier1", start) / 100,
                parameter("l10n_sk_pn_rate_tier2", start) / 100,
            )
        return round_sick_pay(total)

    def l10n_sk_sickness_compensation(self, worked_days, inputs):
        """One monetary path for native cases and the existing manual fallback."""
        daily_input = inputs.dict.get("PN_DVZ")
        daily_base = daily_input.amount if daily_input else None
        native = self.l10n_sk_pn_compensation(daily_base)
        if native is not False:
            return native
        days = (
            abs(worked_days.dict["PN"].number_of_days)
            if "PN" in worked_days.dict
            else inputs.PN_DAYS.amount
        )
        if not days:
            return 0.0
        daily_base = self._l10n_sk_pn_checked_manual_base(daily_base)
        parameter = self.rule_parameter
        paid = min(days, parameter("l10n_sk_pn_employer_days"))
        tier1 = min(paid, parameter("l10n_sk_pn_tier1_days"))
        return self.l10n_sk_pn_manual_compensation(
            min(daily_base, parameter("l10n_sk_pn_max_dvz")),
            tier1,
            max(0, paid - tier1),
            parameter("l10n_sk_pn_rate_tier1") / 100,
            parameter("l10n_sk_pn_rate_tier2") / 100,
        )

    def _l10n_sk_payroll_extra_source_facts(self):
        parent = getattr(super(), "_l10n_sk_payroll_extra_source_facts", None)
        facts = parent() if parent else {}
        return dict(facts, pn_cases=self._l10n_sk_pn_source_facts())

    def _l10n_sk_fund_source_facts(self):
        # The shared per-fund recorder replaced the older social-only hook.
        # Both protocols consume the same native leave facts; the old hook
        # remains available for installations retaining that earlier recorder.
        facts = super()._l10n_sk_fund_source_facts()
        return dict(facts, pn_cases=self._l10n_sk_pn_source_facts())

    def _l10n_sk_fund_capture_metadata(self):
        metadata = super()._l10n_sk_fund_capture_metadata()
        return dict(metadata, pn_cases=self._l10n_sk_pn_source_facts())

    def _l10n_sk_pn_source_facts(self):
        leaves = self._l10n_sk_pn_leaves()
        selected = leaves.filtered(
            lambda row: row.request_date_from <= self.date_to
            and row.request_date_to >= self.date_from
        )
        # Earlier continuation pieces matter; unrelated old medical records do
        # not become inputs to every later month's calculation.
        previous_count = -1
        while previous_count != len(selected):
            previous_count = len(selected)
            for row in leaves - selected:
                reference = (row.l10n_sk_pn_case_reference or "").strip()
                for current in selected:
                    current_reference = (
                        current.l10n_sk_pn_case_reference or ""
                    ).strip()
                    same_case = bool(reference and reference == current_reference)
                    touching = (
                        row.request_date_from
                        <= current.request_date_to + timedelta(days=1)
                        and row.request_date_to
                        >= current.request_date_from - timedelta(days=1)
                    )
                    ambiguous_touch = touching and not (
                        reference
                        and current_reference
                        and reference != current_reference
                    )
                    if same_case or ambiguous_touch:
                        selected |= row
                        break
        return [
            {
                "id": row.id,
                "employee": row.employee_id.id,
                "company": row.company_id.id,
                "state": row.state,
                "start": str(row.request_date_from),
                "end": str(row.request_date_to),
                "case": row.l10n_sk_pn_case_reference or "",
                "daily_base": row.l10n_sk_pn_daily_base,
                "reviewed": row.l10n_sk_pn_base_reviewed,
                "evidence": row.l10n_sk_pn_base_reference or "",
            }
            for row in selected.sorted("id")
        ]


class SicknessStructure(models.Model):
    _inherit = "hr.payroll.structure"

    def _l10n_sk_fund_parameter_codes(self):
        codes = super()._l10n_sk_fund_parameter_codes()
        if "SICK_COMP" in self.get_structure_with_parents().get_all_rules().mapped(
            "code"
        ):
            codes |= {
                "l10n_sk_pn_tier1_days",
                "l10n_sk_pn_employer_days",
                "l10n_sk_pn_max_dvz",
                "l10n_sk_pn_rate_tier1",
                "l10n_sk_pn_rate_tier2",
            }
        return codes
