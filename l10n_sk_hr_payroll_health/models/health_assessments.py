# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Consume the shared recorded-fund protocol for the existing 514 workflow."""

from datetime import date, timedelta
from decimal import Decimal

from odoo import _, models
from odoo.exceptions import UserError

from ..assessment514 import merge_assessment_rows, row_from_assessments
from ..text514 import aggregate


def _xml_health_row(row, previous, sequence=None):
    rendered = dict(previous)
    for target, key in (
        ("tarifa_zamtel", "rate_employer"), ("tarifa_zamnec", "rate_employee"),
        ("prijem", "income"), ("vz", "base"), ("preddavok_zamtel", "employer"),
        ("preddavok_zamnec", "employee"), ("preddavok_spolu", "total"),
        ("doplatok", "topup"), ("op_prijem", "op_income"),
        ("iny_prijem", "other_income"), ("op", "op"), ("exempt_income", "exempt_income"),
    ):
        rendered[target] = format(row[key], ".2f")
    rendered.update(
        minimum_not_applied=str(row["minimum_opt_out"]), poc_dni=str(row["days"]),
        shorttime_base=format(row["shorttime_base"], ".2f") if row["shorttime_base"] is not None else None,
    )
    if sequence is not None:
        rendered["pc"] = str(sequence)
    return rendered


class HealthAssessments(models.Model):
    _inherit = "l10n.sk.health"

    def _uses_recorded_funds(self):
        return True

    def _required_recorded_fund_keys(self):
        return frozenset({("health", "employee"), ("health", "employer")})

    @staticmethod
    def _complete_health_profile(profile):
        if not isinstance(profile, dict) or not {"agreement", "regular", "health"}.issubset(profile):
            return False
        if not isinstance(profile["agreement"], str) or type(profile["regular"]) is not bool:
            return False
        health = profile["health"]
        flags = {"op_eligible", "minimum_exempt", "minimum_opt_out", "exempt", "disabled"}
        if not isinstance(health, dict) or not (flags | {"insurer_code", "calendar"}).issubset(health):
            return False
        if any(type(health[name]) is not bool for name in flags):
            return False
        if health["insurer_code"] not in ("24", "25", "27", None, False):
            return False
        calendar = health["calendar"]
        if calendar is None or calendar is False:
            return True
        if not isinstance(calendar, dict) or not {"insured_days", "insured_dates", "month_start"}.issubset(calendar):
            return False
        days, dates = calendar["insured_days"], calendar["insured_dates"]
        if type(days) is not int or not 0 <= days <= 31 or not isinstance(dates, list):
            return False
        if any(not isinstance(day, str) for day in dates) or len(set(dates)) != days:
            return False
        try:
            month = date.fromisoformat(calendar["month_start"]).replace(day=1)
            if "employment_dates" in calendar:
                employed = calendar["employment_dates"]
                count = calendar.get("employment_days")
                if (not isinstance(employed, list) or any(not isinstance(day, str) for day in employed)
                        or type(count) is not int or len(set(employed)) != count
                        or not set(dates).issubset(employed)):
                    return False
                dates = dates + employed
            if "irregular_dates" in calendar:
                irregular = calendar["irregular_dates"]
                if (not isinstance(irregular, list) or any(not isinstance(day, str) for day in irregular)
                        or len(set(irregular)) != len(irregular)
                        or not set(irregular).issubset(calendar.get("employment_dates", []))):
                    return False
                dates = dates + irregular
            return all(date.fromisoformat(day).replace(day=1) == month for day in dates)
        except (ValueError, TypeError):
            return False

    def _payslip_fund_records(self, slips):
        records, missing = super()._payslip_fund_records(slips)
        profiles = self._payslip_fund_profiles(slips)
        for slip in slips:
            if records[slip.id] and not self._complete_health_profile(profiles[slip.id]):
                records[slip.id] = False
                missing |= slip
            elif records[slip.id] and not self._health_recorded_contract_period(profiles[slip.id]):
                # Coverage is a required source fact, but its absence must not
                # discard valid historical monetary assessments or profiles.
                missing |= slip
        missing |= self._health_multiple_card_monthly_sources(slips, records)
        return records, missing

    def _health_multiple_card_monthly_sources(self, slips, records):
        """The form owns personal identity; arithmetic does not guess allocation."""
        groups = {}
        for slip in slips:
            number = (slip.employee_id.identification_id or "").replace("/", "").strip()
            if number and any(
                row["fund"] == "health" and row["facts"].get("monthly_health")
                for row in records[slip.id] or []
            ):
                groups[number] = groups.get(number, slips.browse()) | slip
        result = slips.browse()
        for group in groups.values():
            if len(group.employee_id) > 1:
                result |= group
        return result

    @staticmethod
    def _health_recorded_contract_period(profile):
        period = profile.get("contract_period") if isinstance(profile, dict) else None
        if not isinstance(period, dict) or set(period) != {"start", "end"}:
            return None
        try:
            start = date.fromisoformat(period["start"])
            end = date.fromisoformat(period["end"]) if period["end"] is not None else None
        except (ValueError, TypeError):
            return None
        if start.isoformat() != period["start"] or (end and end.isoformat() != period["end"]):
            return None
        return (start, end) if not end or start <= end else None

    def _missing_fund_evidence_warning(self, missing):
        profiles = self._payslip_fund_profiles(missing)
        records, _without_evidence = self._payslip_fund_records(missing)
        cards = self._health_multiple_card_monthly_sources(missing, records)
        coverage = missing.filtered(
            lambda slip: records[slip.id] and self._complete_health_profile(profiles[slip.id])
            and not self._health_recorded_contract_period(profiles[slip.id])
        )
        if not coverage and not cards:
            return super()._missing_fund_evidence_warning(missing)
        warnings = []
        if cards:
            warnings.append(_(
                "Monthly health allocation across multiple HR cards requires review for: %(slips)s. "
                "Recorded actual amounts are preserved; no shared OP or minimum is guessed.",
                slips=", ".join(cards.mapped("display_name")),
            ))
        if coverage:
            warnings.append(_(
                "Historical contract coverage was not recorded for: %(slips)s. "
                "Review the original contract periods. Recorded amounts are preserved; "
                "the legacy coverage fallback uses only the payslip dates.",
                slips=", ".join(coverage.mapped("display_name")),
            ))
        other = missing - coverage - cards
        if other:
            warnings.append(super()._missing_fund_evidence_warning(other))
        return "\n".join(warnings)

    def _health_source_coverage_dates(self, slip, profile):
        """Use the frozen source contract, not a later HR version's interval."""
        start, end = max(self.date_from, slip.date_from), min(self.date_to, slip.date_to)
        period = profile.get("contract_period")
        if period:
            start = max(start, period[0])
            end = min(end, period[1] or self.date_to)
        dates = {start + timedelta(days=offset) for offset in range((end - start).days + 1)}
        # Only an explicit 2Y source can extend coverage past this contract.
        # The employee calendar can also describe another ordinary contract;
        # its 2/2P or 2D days must never cover that contract's missing payroll.
        calendar = profile.get("calendar")
        if period and calendar:
            dates.update(
                date.fromisoformat(day) for day in calendar.get("irregular_dates", [])
                if max(self.date_from, slip.date_from) <= date.fromisoformat(day)
                <= min(self.date_to, slip.date_to)
            )
        return dates

    def _health_source_insured_dates(self, slips, profiles):
        dates = set()
        for slip in slips:
            profile = profiles[slip.id]
            if profile.get("calendar"):
                covered = self._health_source_coverage_dates(slip, profile)
                dates.update(date.fromisoformat(day).isoformat() for day in profile["calendar"]["insured_dates"]
                             if date.fromisoformat(day) in covered)
            else:
                dates.update(day.isoformat() for day in self._health_source_coverage_dates(slip, profile))
        return dates

    def _health_registered_counts(self):
        """Count people across insurers; a reviewed zero month still needs payroll."""
        slips = self.env["hr.payslip"].search(self._payslip_period_domain(
            self.company_id, self.date_from, self.date_to,
        ))
        slips = self._effective_fund_payslips(slips)
        profiles = self._health_payslip_profiles(slips)
        people, selected, covered = set(), set(), {}
        for slip in slips:
            health = profiles[slip.id]
            covered.setdefault(slip.employee_id.id, set()).update(
                self._health_source_coverage_dates(slip, health)
            )
            if health.get("exempt"):
                continue
            identity = self._digits(slip.employee_id.identification_id)
            if not 9 <= len(identity) <= 10 or not health.get("insurer_code"):
                raise UserError(_(
                    "Review the historical insurer and identification number for all insured payroll sources "
                    "before generating the 514 counts."
                ))
            people.add(identity)
            if health["insurer_code"] == self.insurer_code:
                selected.add(identity)
        calendars = self.env["l10n.sk.health.calendar"].search([
            ("company_id", "=", self.company_id.id), ("month", "=", self.date_from),
            ("state", "!=", "superseded"),
        ])
        by_employee = {calendar.employee_id.id: calendar for calendar in calendars}
        employees = self.env["hr.employee"].with_context(active_test=False).search([
            ("company_id", "=", self.company_id.id),
        ])
        for employee in employees:
            if self._health_missing_payroll_registration(
                employee, by_employee.get(employee.id), covered.get(employee.id, set()),
            ):
                raise UserError(_(
                    "Complete payroll, including zero-premium months, for '%(name)s' before filing the 514.",
                    name=employee.display_name,
                ))
        return len(selected), len(people)

    def _health_missing_payroll_registration(self, employee, calendar, covered_dates):
        """Discover missing sources independently of slips and calendars.

        A regular PP establishes employment during its effective contract. A
        dohoda or post-contract 2Y only establishes the actual registered days
        recorded in a reviewed calendar. Neither source establishes wages.
        All insurers matter because the 514 also counts all insured persons.
        Confirmed payroll keeps its recorded profile for its actual date range,
        even if HR changes. A partial payslip cannot cover another interval.
        """
        if len(covered_dates) == (self.date_to - self.date_from).days + 1:
            return False
        versions = employee.with_context(active_test=False).version_ids.sorted(
            lambda version: (version.date_version, version.id),
        )
        ordinary_dates = set()
        relevant = self.env["hr.version"]
        for index, version in enumerate(versions):
            start, end = max(self.date_from, version.date_version), self.date_to
            if index + 1 < len(versions):
                end = min(end, versions[index + 1].date_version - timedelta(days=1))
            dates = {start + timedelta(days=offset) for offset in range((end - start).days + 1)} - covered_dates
            if not dates:
                continue
            relevant |= version
            # An HR card alone is not an employment registration. Unlike a
            # report-day fallback, completeness needs a real contract start.
            if not version.contract_date_start:
                continue
            dates = {day for day in dates if version.contract_date_start <= day
                     <= (version.contract_date_end or self.date_to)}
            if (dates and not version.l10n_sk_is_agreement()
                    and not version.l10n_sk_health_is_exempt()):
                ordinary_dates.update(dates)
        if calendar:
            if not relevant or all(version.l10n_sk_health_is_exempt() for version in relevant):
                return False
            if calendar.state != "reviewed":
                raise UserError(_("Finish reviewing monthly health calendars before filing the 514."))
            # Benefits can reduce premium days to zero without ending the
            # registration; only 2N excludes days from the employee role.
            dates, excluded = set(), set()
            for interval in calendar.interval_ids:
                target = excluded if interval.kind == "2N" else dates
                if interval.kind not in {"2", "2P", "2D", "2Y", "2N"}:
                    continue
                target.update(interval.date_start + timedelta(days=offset)
                              for offset in range((interval.date_end - interval.date_start).days + 1))
            for day in dates - excluded - covered_dates:
                version = versions.filtered(lambda row: row.date_version <= day)[-1:]
                if version and not version.l10n_sk_health_is_exempt():
                    return True
            ordinary_dates -= excluded
        return bool(ordinary_dates)

    def _health_payslip_profiles(self, slips):
        profiles = self._payslip_fund_profiles(slips)
        result = {}
        for slip in slips:
            recorded = profiles[slip.id]
            precise = self._complete_health_profile(recorded)
            health = recorded.get("health") if recorded else False
            if not precise:
                version = self._payslip_version(slip)
                health = version._l10n_sk_health_profile(slip.date_from) if version else {}
            result[slip.id] = dict(
                health, precise_profile=precise,
                employment_form=recorded["agreement"] if precise else False,
                regular=recorded["regular"] if precise else True,
                contract_period=self._health_recorded_contract_period(recorded),
            )
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
        for slip in slips:
            profile = profiles[slip.id]
            if (
                profile.get("insurer_code") == self.insurer_code
                and not profile.get("exempt") and profile["precise_profile"]
                and (profile["employment_form"] != "none" or not profile["regular"])
                and not profile.get("calendar")
            ):
                raise UserError(_(
                    "Review actual agreement or irregular-income registration days in the monthly health "
                    "calendar for '%(name)s' before generating the 514.", name=slip.display_name,
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
            dates = self._health_source_insured_dates(slips, profiles)
            for slip in slips:
                health = profiles[slip.id]
                calendar = health.get("calendar")
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
                    "days": len(self._health_source_insured_dates(bucket["payslips"], data["health514_profiles"])),
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
                    "_insured_dates": self._health_source_insured_dates(bucket["payslips"], data["health514_profiles"]),
                }
                row["total"] = row["employee"] + row["employer"] + row["topup"]
            complete_rows.append(dict(row, birth_number=rendered["rc"]))
            rendered.update(_xml_health_row(row, rendered))
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
                result["rows514"].append(_xml_health_row(
                    row, rendered_by_identity[row["birth_number"]], sequence,
                ))
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
