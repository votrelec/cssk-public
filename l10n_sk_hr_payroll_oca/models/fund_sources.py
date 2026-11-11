# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Coordinate actual source writers with the same employee epoch as payroll.

Rules and parameters can be shared by several employers. A source edit touches
only Slovak employees whose structures consume it; calculation itself locks
only its own employees. There is no global country advisory lock.
"""

import re

from odoo import api, models


class FundRuleSource(models.AbstractModel):
    _name = "l10n.sk.fund.rule.source"
    _description = "Payroll calculation source coordination"

    def _l10n_sk_source_employees(self, values=None):
        # Native payslip lines inherit salary-rule fields and methods, but
        # changing a calculated line is not a shared rule/configuration edit.
        if self._name not in {
            "hr.salary.rule",
            "hr.payroll.structure",
            "hr.rule.parameter",
            "hr.rule.parameter.value",
            "resource.calendar",
            "resource.calendar.attendance",
        }:
            return self.env["hr.employee"]
        versions = (
            self.env["hr.version"]
            .sudo()
            .search([("struct_id", "!=", False)])
            .filtered(
                lambda version: version.company_id.country_id.code == "SK"
                and version.struct_id.country_id.code == "SK"
            )
        )
        if self._name == "hr.salary.rule":
            versions = versions.filtered(
                lambda version: bool(
                    version.struct_id.get_structure_with_parents().get_all_rules()
                    & self
                )
            )
        elif self._name == "hr.payroll.structure":
            versions = versions.filtered(
                lambda version: bool(
                    version.struct_id.get_structure_with_parents() & self
                )
            )
        elif self._name in {"hr.rule.parameter", "hr.rule.parameter.value"}:
            params = (
                self if self._name == "hr.rule.parameter" else self.rule_parameter_id
            )
            if values and values.get("rule_parameter_id"):
                params |= self.env["hr.rule.parameter"].browse(
                    values["rule_parameter_id"]
                )
            if params and all(
                param.country_id.code not in {False, "SK"} for param in params
            ):
                return self.env["hr.employee"]
            codes = set(params.mapped("code"))
            if values and values.get("code"):
                codes.add(values["code"])
            if codes:
                versions = versions.filtered(
                    lambda version: bool(
                        codes & version.struct_id._l10n_sk_fund_parameter_codes()
                    )
                )
        elif self._name in {"resource.calendar", "resource.calendar.attendance"}:
            calendars = self if self._name == "resource.calendar" else self.calendar_id
            if values and values.get("calendar_id"):
                calendars |= self.env["resource.calendar"].browse(values["calendar_id"])
            versions = versions.filtered(
                lambda version: bool(version.resource_calendar_id & calendars)
            )
        return versions.employee_id

    @api.model_create_multi
    def create(self, values_list):
        self.check_access("create")
        employees = self.env["hr.employee"]
        field = {
            "hr.rule.parameter.value": "rule_parameter_id",
            "resource.calendar.attendance": "calendar_id",
        }.get(self._name)
        defaults = self.default_get([field]) if field else {}
        for values in values_list:
            employees |= self._l10n_sk_source_employees(dict(defaults, **values))
        employees._l10n_sk_lock_fund_source()
        return super().create(values_list)

    def write(self, values):
        self.check_access("write")
        if set(values) - {"name", "description", "note", "appears_on_payslip"}:
            self._l10n_sk_source_employees(values)._l10n_sk_lock_fund_source()
        return super().write(values)

    def unlink(self):
        self.check_access("unlink")
        self._l10n_sk_source_employees()._l10n_sk_lock_fund_source()
        return super().unlink()


class FundSalaryRule(models.Model):
    _name = "hr.salary.rule"
    _inherit = ["hr.salary.rule", "l10n.sk.fund.rule.source"]


class FundStructure(models.Model):
    _name = "hr.payroll.structure"
    _inherit = ["hr.payroll.structure", "l10n.sk.fund.rule.source"]

    def _l10n_sk_fund_parameter_codes(self):
        """Cooperative dependency list for snapshots AND parameter writers.

        Rule providers using helper methods or dynamically constructed codes
        must extend this set with those helpers' explicit parameter codes.
        """
        rules = self.get_structure_with_parents().get_all_rules()
        source = "\n".join(
            rule[name] or ""
            for rule in rules
            for name in (
                "amount_python_compute",
                "condition_python",
                "quantity",
                "condition_range",
                "amount_percentage_base",
            )
        )
        # Literal references are dependencies even before a parameter exists;
        # searching only current parameter rows would miss insertion phantoms.
        return set(re.findall(r"rule_parameter\(\s*['\"]([^'\"]+)['\"]", source))


class FundParameter(models.Model):
    _name = "hr.rule.parameter"
    _inherit = ["hr.rule.parameter", "l10n.sk.fund.rule.source"]


class FundParameterValue(models.Model):
    _name = "hr.rule.parameter.value"
    _inherit = ["hr.rule.parameter.value", "l10n.sk.fund.rule.source"]


class FundResourceCalendar(models.Model):
    _name = "resource.calendar"
    _inherit = ["resource.calendar", "l10n.sk.fund.rule.source"]


class FundCalendarAttendance(models.Model):
    _name = "resource.calendar.attendance"
    _inherit = ["resource.calendar.attendance", "l10n.sk.fund.rule.source"]


class FundLeave(models.Model):
    _inherit = "hr.leave"

    @api.model_create_multi
    def create(self, values_list):
        self.check_access("create")
        default = self.default_get(["employee_id"]).get("employee_id")
        identifiers = {values.get("employee_id", default) for values in values_list}
        self.env["hr.employee"].browse(
            sorted(x for x in identifiers if x)
        )._l10n_sk_lock_fund_source()
        return super().create(values_list)

    def write(self, values):
        self.check_access("write")
        if set(values) - {"name", "private_name", "notes", "message_ids"}:
            (
                self.employee_id
                | self.env["hr.employee"].browse(values.get("employee_id"))
            )._l10n_sk_lock_fund_source()
        return super().write(values)

    def unlink(self):
        self.check_access("unlink")
        self.employee_id._l10n_sk_lock_fund_source()
        return super().unlink()
