# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Feed reviewed health calendar facts to both engines' monetary rules."""

from calendar import monthrange

from odoo import fields, models

from ..health_calculation import monthly_minimum, monthly_op


class HealthCalculationProfile(models.Model):
    _inherit = "hr.version"

    def _l10n_sk_health_profile(self, day):
        """Cooperative health facts, extensible by the country output module."""
        self.ensure_one()
        calendar = self._l10n_sk_health_calendar_context(day)
        return {
            "disabled": self.l10n_sk_health_is_disabled(day),
            "exempt": self.l10n_sk_health_is_exempt(),
            "minimum_opt_out": self.l10n_sk_health_minimum_is_opted_out(),
            "calendar": calendar or None,
        }

    def l10n_sk_health_is_disabled(self, day=None):
        profile = super().l10n_sk_health_is_disabled()
        if day is None:
            return profile
        calendar = self._l10n_sk_health_calendar_context(day)
        return bool(profile or (calendar and calendar["disability_in_month"]))

    def l10n_sk_health_employee_op(self, income, day, maximum, phaseout_end):
        """Current native single-income source; derived from actual OP facts.

        A benefit interval leaves OP employment intact; 2N shortens it.
        Concurrent employers/SZCO postpone OP to the insurer's annual result.
        Other income allocation can extend this hook before calling monthly_op.
        """
        self.ensure_one()
        day = fields.Date.to_date(day)
        calendar = self._l10n_sk_health_calendar_context(day)
        eligible = self.l10n_sk_employment_form() == "none"
        claim = getattr(self, "l10n_sk_health_oop_claim", False)
        if not eligible or not claim or self.l10n_sk_health_is_exempt():
            return 0.0
        if calendar and (
            calendar["concurrent_other_employment"]
            or calendar["concurrent_self_employment"]
        ):
            return 0.0
        days = (
            calendar["op_employment_days"]
            if calendar
            else self._l10n_sk_month_employed_days(day)
        )
        return float(
            monthly_op(
                income,
                max(income, 0),
                maximum,
                phaseout_end,
                days,
                monthrange(day.year, day.month)[1],
            )
        )

    def l10n_sk_health_calendar_minimum(self, day, base, employee_rate, employer_rate):
        """False preserves the native absence fallback when no calendar exists."""
        self.ensure_one()
        day = fields.Date.to_date(day)
        calendar = self._l10n_sk_health_calendar_context(day)
        if not calendar:
            return False
        if self.l10n_sk_health_minimum_is_exempt():
            return 0.0
        if self.l10n_sk_health_minimum_is_opted_out():
            return 0.0
        return float(
            monthly_minimum(
                base,
                employee_rate,
                employer_rate,
                calendar["minimum_days"],
                calendar["calendar_days"],
            )
        )
