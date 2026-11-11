# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Consume the shared recorded-fund protocol for the existing 514 workflow."""

from decimal import Decimal
from datetime import timedelta

from odoo import _, models
from odoo.exceptions import UserError

from ..assessment514 import merge_assessment_rows, row_from_assessments
from ..text514 import aggregate


class HealthAssessments(models.Model):
    _inherit = "l10n.sk.health"

    def _uses_recorded_funds(self):
        return True

    def _required_recorded_fund_keys(self):
        return frozenset({("health", "employee"), ("health", "employer")})

    def _health_employment_dates(self, employee):
        return {
            (start + timedelta(days=offset)).isoformat()
            for start, end in self._employee_contract_intervals(employee, self.date_from, self.date_to)
            for offset in range((end - start).days + 1)
        }

    def _health_registered_counts(self):
        """Count people across insurers; a reviewed zero month still needs payroll."""
        slips = self.env["hr.payslip"].search(self._payslip_period_domain(
            self.company_id, self.date_from, self.date_to,
        ))
        slips = self._effective_fund_payslips(slips)
        profiles = self._health_payslip_profiles(slips)
        people, selected, covered = set(), set(), set()
        for slip in slips:
            health = profiles[slip.id]
            if health.get("exempt"):
                continue
            identity = self._digits(slip.employee_id.identification_id)
            if not 9 <= len(identity) <= 10 or not health.get("insurer_code"):
                raise UserError(_(
                    "Review the historical insurer and identification number for all insured payroll sources "
                    "before generating the 514 counts."
                ))
            people.add(identity)
            covered.add(slip.employee_id.id)
            if health["insurer_code"] == self.insurer_code:
                selected.add(identity)
        calendars = self.env["l10n.sk.health.calendar"].search([
            ("company_id", "=", self.company_id.id), ("month", "=", self.date_from),
            ("state", "!=", "superseded"),
        ])
        for calendar in calendars:
            if calendar.employee_id.id in covered:
                continue
            version = calendar.employee_id._get_version(self.date_to)
            if version.l10n_sk_health_is_exempt():
                continue
            if calendar.state != "reviewed":
                raise UserError(_("Finish reviewing monthly health calendars before filing the 514."))
            if calendar._calendar_context()["employment_days"]:
                raise UserError(_(
                    "Complete payroll, including zero-premium months, for '%(name)s' before filing the 514.",
                    name=calendar.employee_id.display_name,
                ))
        return len(selected), len(people)

    def _health_payslip_profiles(self, slips):
        profiles = self._payslip_fund_profiles(slips)
        result = {}
        for slip in slips:
            recorded = profiles[slip.id]
            health = recorded.get("health") if recorded else False
            if not health:
                version = self._payslip_version(slip)
                health = version._l10n_sk_health_profile(slip.date_from) if version else {}
            result[slip.id] = health
        return result

    def _health_selected_payslips(self, slips):
        if not slips:
            return slips
        slips = self._effective_fund_payslips(slips)
        profiles = self._health_payslip_profiles(slips)
        missing = slips.filtered(
            lambda slip: not profiles[slip.id].get("exempt")
            and not profiles[slip.id].get("insurer_code")
        )
        if missing:
            raise UserError(_(
                "Review the historical health insurer for: %(slips)s",
                slips=", ".join(missing.mapped("display_name")),
            ))
        return slips.filtered(
            lambda slip: profiles[slip.id].get("insurer_code") == self.insurer_code
            and not profiles[slip.id].get("exempt")
        )

    def _health_check_excluded(self, slips):
        if not slips:
            return
        slips = self._effective_fund_payslips(slips)
        profiles = self._health_payslip_profiles(slips)
        records, _missing = self._payslip_fund_records(slips)
        for slip in slips:
            profile = profiles[slip.id]
            if profile.get("insurer_code") != self.insurer_code or not profile.get("exempt"):
                continue
            nonzero = any(
                Decimal(row[key])
                for row in records[slip.id] or []
                if row["fund"] == "health"
                for key in ("base", "amount")
            ) or any(
                line.total
                for line in slip.line_ids
                if line.code in {"HEALTH", "HEALTHEMPLOYER", "HEALTHDOPLATOK", "HEALTH_DOPLATOK"}
            )
            if nonzero:
                raise UserError(_(
                    "Payslip '%(name)s' has nonzero health assessments for excluded income. "
                    "Review its historical profile and the payroll correction before filing.",
                    name=slip.display_name,
                ))

    def _collect_payslip_totals(self, payslips):
        data = super()._collect_payslip_totals(payslips)
        records = data["recorded_funds"]
        profiles = self._health_payslip_profiles(payslips)
        rows = {}
        for employee, bucket in data["per_employee"].items():
            slips = bucket["payslips"]
            if not all(records.get(slip.id) for slip in slips):
                # The framework has already applied the original/corrective
                # legacy policy. Preserve the existing report fallback.
                continue
            parts = []
            dates = set()
            for slip in slips:
                health = profiles[slip.id]
                calendar = health.get("calendar")
                if calendar:
                    dates.update(calendar["insured_dates"])
                direction_hook = getattr(slip, "_cssk_fund_record_direction", None)
                direction = direction_hook() if callable(direction_hook) else 1
                try:
                    part = row_from_assessments(
                        records[slip.id], health,
                        op_eligible=health["op_eligible"],
                        days=calendar["insured_days"] if calendar else 0,
                        direction=direction,
                    )
                except (KeyError, ValueError) as exc:
                    raise UserError(_(
                        "Review the recorded health assessments and monthly profile for '%(name)s' "
                        "before generating the 514.", name=slip.display_name,
                    )) from exc
                if part is not None:
                    parts.append(part)
            if not parts:
                continue
            try:
                first = merge_assessment_rows(parts)
            except ValueError as exc:
                raise UserError(_(
                    "Review the inconsistent monthly health profile across payroll sources for '%(name)s'.",
                    name=employee.display_name,
                )) from exc
            if not all(profiles[slip.id].get("calendar") for slip in slips):
                dates = self._health_employment_dates(employee)
            first["days"] = len(dates)
            first["_insured_dates"] = dates
            rows[employee.id] = first
        data["health514_rows"] = rows
        data["health514_profiles"] = profiles
        return data

    def _prepare_employee_declarations(self, data):
        super()._prepare_employee_declarations(data)
        rows = data["health514_rows"]
        for line in self._sheet_lines():
            row = rows.get(line.employee_id.id)
            if row:
                line.write({"vz_base": float(row["base"]), "insured_days": row["days"]})

    def _declaration_render_context(self, data):
        result = super()._declaration_render_context(data)
        rows = data.get("health514_rows", {})
        complete_rows = []
        for line, rendered in zip(self._sheet_lines().sorted("sequence"), result["rows514"]):
            row = rows.get(line.employee_id.id)
            if not row:
                bucket = data["per_employee"][line.employee_id]
                profile = data["health514_profiles"][bucket["payslips"][0].id]
                # Only the shared framework may admit a missing-evidence
                # original or explicitly reviewed legacy correction. Preserve
                # that row's existing gross-based figures, including its old
                # rate fallback; mix known precise rows without losing them.
                row = {
                    "disabled": bool(profile.get("disabled")),
                    "days": line.insured_days,
                    "rate_employer": Decimal(rendered["tarifa_zamtel"]),
                    "rate_employee": Decimal(rendered["tarifa_zamnec"]),
                    "income": Decimal(rendered["prijem"]),
                    "base": Decimal(rendered["vz"]),
                    "employer_base": Decimal(rendered["prijem"]),
                    "employer": Decimal(rendered["preddavok_zamtel"]),
                    "employee": Decimal(rendered["preddavok_zamnec"]),
                    "topup": Decimal(rendered["doplatok"]),
                    "op_income": Decimal(rendered["prijem"]) if profile.get("op_eligible") else Decimal(0),
                    "other_income": Decimal(0) if profile.get("op_eligible") else Decimal(rendered["prijem"]),
                    "op": Decimal(0), "exempt_income": Decimal(0), "shorttime_base": None,
                    "minimum_opt_out": 0,
                    "premium_assessed": bool(line.vz_base),
                    "_insured_dates": self._health_employment_dates(line.employee_id),
                }
                row["total"] = row["employee"] + row["employer"] + row["topup"]
            complete_rows.append(dict(row, birth_number=rendered["rc"]))
            for target, key in (
                ("tarifa_zamtel", "rate_employer"), ("tarifa_zamnec", "rate_employee"),
                ("prijem", "income"), ("vz", "base"), ("preddavok_zamtel", "employer"),
                ("preddavok_zamnec", "employee"), ("preddavok_spolu", "total"),
                ("doplatok", "topup"), ("op_prijem", "op_income"),
                ("iny_prijem", "other_income"), ("op", "op"),
            ):
                rendered[target] = format(row[key], ".2f")
            rendered["minimum_not_applied"] = str(row["minimum_opt_out"])
            rendered["poc_dni"] = str(row["days"])
            rendered["exempt_income"] = format(row["exempt_income"], ".2f")
            rendered["shorttime_base"] = (
                format(row["shorttime_base"], ".2f") if row["shorttime_base"] is not None else None
            )
        if len(complete_rows) == len(result["rows514"]):
            grouped = {}
            for row in complete_rows:
                grouped.setdefault(row["birth_number"], []).append(row)
            try:
                complete_rows = [merge_assessment_rows(parts) for parts in grouped.values()]
            except ValueError as exc:
                raise UserError(_(
                    "Review the inconsistent monthly health profile across records of the same insured person."
                )) from exc
            # The employee sheet keeps its individual HR sources. The wire
            # format requires one consolidated row per insured person.
            rendered_by_identity = {row["rc"]: row for row in result["rows514"]}
            result["rows514"] = []
            for sequence, row in enumerate(complete_rows, 1):
                rendered = dict(rendered_by_identity[row["birth_number"]])
                rendered.update(pc=str(sequence), poc_dni=str(row["days"]))
                for target, key in (
                    ("prijem", "income"), ("vz", "base"), ("preddavok_zamtel", "employer"),
                    ("preddavok_zamnec", "employee"), ("preddavok_spolu", "total"),
                    ("doplatok", "topup"), ("op_prijem", "op_income"),
                    ("iny_prijem", "other_income"), ("op", "op"), ("exempt_income", "exempt_income"),
                ):
                    rendered[target] = format(row[key], ".2f")
                rendered["shorttime_base"] = (
                    format(row["shorttime_base"], ".2f") if row["shorttime_base"] is not None else None
                )
                result["rows514"].append(rendered)
            result["ident"]["pocet_viet"] = str(len(complete_rows))
            registered, registered_all = self._health_registered_counts()
            summary = aggregate(complete_rows, registered, registered_all)
            result["health514_summary"] = summary
            result["agg514"].update({
                "pocet": str(registered),
                "pocet1": str(summary["count_standard"]), "pocet2": str(summary["count_disabled"]),
                "dni1": str(summary["days_standard"]), "dni2": str(summary["days_disabled"]),
                "prijem1": format(summary["income_standard"], ".2f"),
                "prijem2": format(summary["income_disabled"], ".2f"),
                "vz1": format(summary["base_standard"], ".2f"),
                "vz2": format(summary["base_disabled"], ".2f"),
                "deposit1": format(summary["er_standard"], ".2f"),
                "deposit2": format(summary["ee_standard"], ".2f"),
                "deposit3": format(summary["er_disabled"], ".2f"),
                "deposit4": format(summary["ee_disabled"], ".2f"),
                "preddavok_spolu": format(summary["total"], ".2f"),
            })
        result["health514_wire_rows"] = complete_rows
        result["ident"]["charakter"] = {
            "regular": "N", "corrective": "O", "supplementary": "A",
        }[self.correction_type]
        return result
