# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Source validation around native payroll; no alternate calculation ledger."""

from odoo import api, fields, models
from odoo.addons.l10n_sk_hr_payroll_base.fund_sources import (
    source_fingerprint as _digest,
)
from odoo.exceptions import UserError

GENERATED = {
    "l10n_sk_fund_confirmed_at",
    "l10n_sk_fund_source_signature",
    "l10n_sk_fund_refund_original_id",
}
IDENTITY = {
    "employee_id",
    "company_id",
    "contract_id",
    "date_from",
    "date_to",
    "struct_id",
    "credit_note",
    "line_ids",
    "input_line_ids",
    "worked_days_line_ids",
}


class FundLifecyclePayslip(models.Model):
    _inherit = "hr.payslip"

    l10n_sk_fund_confirmed_at = fields.Datetime(
        string="Payroll sources confirmed at", readonly=True, copy=False
    )
    l10n_sk_fund_source_signature = fields.Char(
        string="Payroll calculation source signature", readonly=True, copy=False
    )
    l10n_sk_fund_refund_original_id = fields.Many2one(
        "hr.payslip",
        string="Original full-refund payroll source",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )
    refunded_id = fields.Many2one(copy=False)

    def _l10n_sk_fund_is_relevant(self):
        self.ensure_one()
        return self.struct_id.country_id.code == "SK"

    def _l10n_sk_fund_is_protected(self):
        self.ensure_one()
        return bool(
            self.l10n_sk_fund_confirmed_at
            or (self._l10n_sk_fund_is_relevant() and self.state in {"done", "paid"})
        )

    def _l10n_sk_lock_fund_payslips(self):
        """Employee first, then parents, before child/deferred FK writes.

        The actual non-key employee UPDATE forces a stale REPEATABLE READ
        transaction to retry, including a concurrent insertion of a new peer.
        Non-request callers must retry the entire transaction themselves.
        """
        self.check_access("write")
        relevant = self.filtered(lambda slip: slip._l10n_sk_fund_is_relevant())
        relevant.employee_id._l10n_sk_lock_fund_source()
        if relevant:
            relevant.flush_recordset()
            self.env.cr.execute(
                "SELECT id FROM hr_payslip WHERE id = ANY(%s) "
                "ORDER BY id FOR NO KEY UPDATE",
                [sorted(relevant.ids)],
            )
            relevant.invalidate_recordset()
            relevant.check_access("write")

    def _l10n_sk_monthly_predecessors(self):
        """Raw confirmed company/person/end-month peers, before fund policy.

        Keep unsupported straddling sources: consumers must explicitly decide
        their policy instead of silently dropping them from the signature.
        """
        self.ensure_one()
        return self.search(
            [
                ("id", "!=", self.id),
                ("company_id", "=", self.company_id.id),
                ("employee_id", "=", self.employee_id.id),
                ("date_to", ">=", self.date_to.replace(day=1)),
                ("date_to", "<=", fields.Date.end_of(self.date_to, "month")),
                ("state", "in", ("done", "paid")),
            ],
            order="id",
        )

    def _l10n_sk_fund_source_facts(self):
        """Cooperative current calculation sources; never used by filed reads.

        Only compact digests of predecessors are retained, avoiding recursive
        snapshots. Additional rule providers extend this dict with their facts.
        """
        self.ensure_one()
        version = self.contract_id or self._get_employee_contracts()
        names = self.env["hr.version"]._l10n_sk_fund_source_field_names()
        names = sorted(name for name in names if name in version._fields)
        rules = self.struct_id.get_structure_with_parents().get_all_rules()
        rule_names = [
            name
            for name, field in rules._fields.items()
            if field.store
            and not field.translate
            and field.type
            in {"char", "text", "float", "integer", "boolean", "selection", "many2one"}
            and name not in {"create_uid", "write_uid", "display_name"}
        ]
        parameters = self.env["hr.rule.parameter"].search(
            ["|", ("country_id", "=", False), ("country_id.code", "=", "SK")]
        )
        parameter_codes = self.struct_id._l10n_sk_fund_parameter_codes()
        parameters = parameters.filtered(
            lambda parameter: parameter.code in parameter_codes
        )
        values = self.env["hr.rule.parameter.value"].search(
            [
                ("rule_parameter_id", "in", parameters.ids),
                ("date_from", "<=", self.date_to),
            ],
            order="id",
        )
        calendars = version.resource_calendar_id
        return {
            "identity": self._l10n_sk_fund_identity(),
            "salary": self._l10n_sk_fund_salary_facts(),
            "versions": version.read(names, load=False),
            "profile": self._l10n_sk_fund_profile() if len(version) == 1 else None,
            "rules": rules.sorted("id").read(sorted(rule_names), load=False),
            "parameters": parameters.read(["code", "country_id"], load=False),
            "values": values.read(
                ["rule_parameter_id", "date_from", "parameter_value"], load=False
            ),
            "calendars": calendars.read(
                ["hours_per_day", "tz", "two_weeks_calendar"], load=False
            ),
            "attendance": calendars.attendance_ids.sorted("id").read(
                [
                    "calendar_id",
                    "dayofweek",
                    "hour_from",
                    "hour_to",
                    "week_type",
                    "day_period",
                ],
                load=False,
            ),
            "inputs": sorted(
                [line.code, line.contract_id.id, line.amount, line.sequence]
                for line in self.input_line_ids
            ),
            "worked_days": sorted(
                [
                    line.code,
                    line.contract_id.id,
                    line.number_of_days,
                    line.number_of_hours,
                ]
                for line in self.worked_days_line_ids
            ),
            "leaves": self.env["hr.leave"]
            .search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("date_from", "<=", self.date_to),
                ],
                order="id",
            )
            .read(["date_from", "date_to", "state", "holiday_status_id"], load=False),
            "predecessors": [
                [
                    peer.id,
                    peer.refunded_id.id,
                    _digest(
                        [
                            peer._l10n_sk_fund_identity(),
                            peer._l10n_sk_fund_salary_facts(),
                            peer.l10n_sk_fund_assessment,
                        ]
                    ),
                ]
                for peer in self._l10n_sk_monthly_predecessors()
            ],
        }

    def _l10n_sk_fund_capture_metadata(self):
        result = super()._l10n_sk_fund_capture_metadata()
        facts = self._l10n_sk_fund_source_facts()
        result["sources"] = {
            "signature": _digest(facts),
            "predecessors": facts["predecessors"],
        }
        return result

    def _l10n_sk_recorded_source_signature(self):
        self.ensure_one()
        return self.l10n_sk_fund_source_signature

    def _l10n_sk_write_lifecycle(self, values):
        """Private generated stamp writer; no context capability is accepted."""
        return super().write(values)

    @api.model_create_multi
    def create(self, values_list):
        if any("default_" + name in self.env.context for name in GENERATED) or any(
            GENERATED.intersection(values) for values in values_list
        ):
            raise UserError(
                self.env._("Fund evidence is generated by payroll calculation.")
            )
        # Direct state creation must pass the same validation as a write.
        defaults = self.default_get(
            ["struct_id", "employee_id", "state", "refunded_id"]
        )
        employees = self.env["hr.employee"]
        for values in values_list:
            structure = self.env["hr.payroll.structure"].browse(
                values.get("struct_id", defaults.get("struct_id"))
            )
            if structure.country_id.code == "SK":
                if values.get("refunded_id", defaults.get("refunded_id")):
                    raise UserError(
                        self.env._("Use the native full payroll refund action.")
                    )
                if values.get("state", defaults.get("state")) in {"done", "paid"}:
                    raise UserError(
                        self.env._("Calculate the payslip before confirming payroll.")
                    )
                employees |= self.env["hr.employee"].browse(
                    values.get("employee_id", defaults.get("employee_id"))
                )
        employees._l10n_sk_lock_fund_source()
        return super().create(values_list)

    def compute_sheet(self):
        with self.env.cr.savepoint():
            self._l10n_sk_lock_fund_payslips()
            if any(slip._l10n_sk_fund_is_protected() for slip in self):
                raise UserError(
                    self.env._(
                        "Retain confirmed payroll fund sources; use a payroll correction."
                    )
                )
            result = super().compute_sheet()
            for slip in self.filtered(lambda row: row._l10n_sk_fund_is_relevant()):
                slip._l10n_sk_write_lifecycle(
                    {
                        "l10n_sk_fund_source_signature": _digest(
                            slip._l10n_sk_fund_source_facts()
                        )
                    }
                )
            return result

    def _l10n_sk_validate_retained_fund_source(self):
        """Check retained bytes only; later monthly payroll is not HR drift."""
        self.ensure_one()
        original = self.l10n_sk_fund_refund_original_id
        if original:
            if self._l10n_sk_refund_original() != original:
                raise UserError(
                    self.env._(
                        "The full payroll refund no longer matches its original recorded source."
                    )
                )
        if self.l10n_sk_fund_assessment:
            self._l10n_sk_checked_fund_assessment()

    def _l10n_sk_validate_confirmation(self):
        self.ensure_one()
        if not self.l10n_sk_fund_refund_original_id:
            self._l10n_sk_check_current_fund_sources()
        self._l10n_sk_validate_retained_fund_source()

    def write(self, values):
        if GENERATED.intersection(values):
            raise UserError(
                self.env._("Fund evidence is generated by payroll calculation.")
            )
        with self.env.cr.savepoint():
            relevant_before = self.filtered(lambda row: row._l10n_sk_fund_is_relevant())
            if (
                IDENTITY.intersection(values)
                or "state" in values
                or "refunded_id" in values
            ):
                sources = relevant_before
                if (
                    values.get("struct_id")
                    and self.env["hr.payroll.structure"]
                    .browse(values["struct_id"])
                    .country_id.code
                    == "SK"
                ):
                    sources |= self
                employees = sources.employee_id
                if sources and values.get("employee_id"):
                    employees |= self.env["hr.employee"].browse(values["employee_id"])
                employees._l10n_sk_lock_fund_source()
                self._l10n_sk_lock_fund_payslips()
            protected = self.filtered(lambda row: row._l10n_sk_fund_is_protected())
            if protected and (
                IDENTITY.intersection(values)
                or any(
                    "state" in values
                    and values["state"] not in {row.state, "cancel"}
                    and not (
                        values["state"] == "paid" and row.state in {"done", "paid"}
                    )
                    for row in protected
                )
            ):
                raise UserError(
                    self.env._(
                        "Retain confirmed payroll fund sources; use a payroll correction."
                    )
                )
            if "refunded_id" in values:
                for slip in relevant_before:
                    refund = self.browse(values["refunded_id"])
                    if refund == slip.refunded_id:
                        continue
                    if (not refund and slip in protected) or (
                        refund
                        and (
                            refund.l10n_sk_fund_refund_original_id != slip
                            or slip.refunded_id
                        )
                    ):
                        raise UserError(
                            self.env._("Use the native full payroll refund action.")
                        )
            if values.get("state") in {"done", "paid"}:
                # Apply header/child commands exactly once, through every
                # cooperative write guard, before validating their result.
                header = {
                    name: value for name, value in values.items() if name != "state"
                }
                if header:
                    super().write(header)
                for slip in self.sorted("id"):
                    relevant = (
                        slip in relevant_before or slip._l10n_sk_fund_is_relevant()
                    )
                    if relevant:
                        if slip in protected:
                            slip._l10n_sk_validate_retained_fund_source()
                        else:
                            # Closing one source changes the next source's
                            # predecessor signature even within this same TX.
                            slip._l10n_sk_validate_confirmation()
                            slip._l10n_sk_write_lifecycle(
                                {"l10n_sk_fund_confirmed_at": fields.Datetime.now()}
                            )
                    if slip.state != values["state"]:
                        super(FundLifecyclePayslip, slip).write(
                            {"state": values["state"]}
                        )
                return True
            return super().write(values)

    def action_payslip_done(self):
        self.check_access("write")
        with self.env.cr.savepoint():
            self._l10n_sk_lock_fund_payslips()
            done = self.filtered(
                lambda row: row._l10n_sk_fund_is_protected()
                and row.state in {"done", "paid"}
            )
            for slip in done:
                slip._l10n_sk_validate_retained_fund_source()
            result = True
            for slip in (self - done).sorted("id"):
                # Native singleton compute/confirm retains its own opt-outs
                # and MRO. The next calculation sees the preceding done row.
                result = super(FundLifecyclePayslip, slip).action_payslip_done()
            return result

    def _copy_refund_payslip(self):
        """OCA PR 332 hook; retained lines are copied, never recomputed."""
        self.ensure_one()
        self._l10n_sk_lock_fund_payslips()
        if self._l10n_sk_fund_is_relevant():
            if (
                self.credit_note
                or not self._l10n_sk_fund_is_protected()
                or self.refunded_id
            ):
                raise UserError(
                    self.env._(
                        "Use a confirmed original payroll source for the full refund."
                    )
                )
        refund = super()._copy_refund_payslip()
        if self._l10n_sk_fund_is_relevant():
            refund._l10n_sk_write_lifecycle(
                {"l10n_sk_fund_refund_original_id": self.id}
            )
            self.write({"refunded_id": refund.id})
        return refund

    def unlink(self):
        self._l10n_sk_lock_fund_payslips()
        if any(slip._l10n_sk_fund_is_protected() for slip in self):
            raise UserError(
                self.env._(
                    "Retain confirmed payroll fund sources; use a payroll correction."
                )
            )
        return super().unlink()
