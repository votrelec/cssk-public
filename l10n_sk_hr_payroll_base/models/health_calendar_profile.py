# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Read reviewed calendar facts without changing any payroll calculation."""

from calendar import monthrange
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..health_exemption import pension_health_disabled


class HealthCalendarProfile(models.Model):
    _inherit = "hr.version"

    l10n_sk_health_minimum_opt_out = fields.Boolean(
        string="Concurrent-employment minimum opt-out",
        help="Section 16a(5): written notice of concurrent employers. This is separate from state-insured status or disability.",
    )
    l10n_sk_health_minimum_evidence = fields.Char(
        string="Minimum opt-out notice reference",
        help="Retained written notice and concurrent-employment facts for this version.",
    )

    @api.model
    def _get_whitelist_fields_from_template(self):
        values = super()._get_whitelist_fields_from_template() or []
        return values + [
            name
            for name in (
                "l10n_sk_health_minimum_opt_out",
                "l10n_sk_health_minimum_evidence",
            )
            if name not in values
        ]

    def l10n_sk_health_minimum_is_opted_out(self):
        self.ensure_one()
        if (
            self.l10n_sk_health_minimum_opt_out
            and not (self.l10n_sk_health_minimum_evidence or "").strip()
        ):
            raise UserError(
                _(
                    "Record the employee's written concurrent-employment minimum opt-out notice before calculation."
                )
            )
        return bool(self.l10n_sk_health_minimum_opt_out)

    def _l10n_sk_health_calendar_context(self, day):
        """Read the reviewed month; a replacement draft is never new evidence.

        Both engines and the registration/declaration adapters can consume this
        factual API. This contribution does not alter salary rules or amounts.
        """
        self.ensure_one()
        self.check_access("read")
        month = fields.Date.to_date(day).replace(day=1)
        calendar = self.env["l10n.sk.health.calendar"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("employee_id", "=", self.employee_id.id),
                ("month", "=", month),
                ("state", "!=", "superseded"),
            ]
        )
        if calendar and calendar.state != "reviewed":
            raise UserError(
                _("Finish reviewing the employee's health calendar before calculation.")
            )
        facts = calendar._calendar_context() if calendar else False
        if (
            facts
            and (
                getattr(self, "l10n_sk_ztp", False)
                or pension_health_disabled(self.l10n_sk_pension_status())
            )
            and not facts["disability_in_month"]
        ):
            raise UserError(
                _(
                    "Review the disability disagreement between the employment version and the health calendar."
                )
            )
        if facts and self.l10n_sk_health_minimum_opt_out:
            self.l10n_sk_health_minimum_is_opted_out()
            if not facts["minimum_concurrent_other_employment"]:
                raise UserError(
                    _(
                        "A minimum opt-out requires concurrent employers in the reviewed health calendar."
                    )
                )
        return facts

    def _l10n_sk_validate_health_calendar_source(self, day):
        """Validate new payroll input, never the reading of retained evidence.

        A reviewed month may describe zero premium days without ending a PP:
        benefits leave registration intact, while explicit 2N explains its
        exclusion. An empty month cannot replace a signed ordinary contract.
        Engines call this before evaluation and when building new evidence;
        legacy profile readers deliberately keep their existing policy.
        """
        self.ensure_one()
        facts = self._l10n_sk_health_calendar_context(day)
        if not facts or self.l10n_sk_health_is_exempt():
            return facts
        first = fields.Date.to_date(day).replace(day=1)
        last = first.replace(day=monthrange(first.year, first.month)[1])
        versions = self.employee_id.with_context(active_test=False).version_ids.sorted(
            lambda version: (version.date_version, version.id),
        )
        expected = set()
        for index, version in enumerate(versions):
            if not version.contract_date_start or version.l10n_sk_is_agreement():
                continue
            start = max(first, version.date_version, version.contract_date_start)
            end = min(last, version.contract_date_end or last)
            if index + 1 < len(versions):
                end = min(end, versions[index + 1].date_version - timedelta(days=1))
            if start <= end and not version.l10n_sk_health_is_exempt():
                expected.update(start + timedelta(days=offset)
                                for offset in range((end - start).days + 1))
        calendar = self.env["l10n.sk.health.calendar"].browse(facts["calendar_id"])
        registered, excluded = set(), set()
        for interval in calendar.interval_ids:
            if interval.kind not in {"2", "2P", "2N"}:
                continue
            target = excluded if interval.kind == "2N" else registered
            target.update(interval.date_start + timedelta(days=offset)
                          for offset in range((interval.date_end - interval.date_start).days + 1))
        if expected - registered - excluded or registered - expected:
            raise UserError(_(
                "Review the health calendar for '%(name)s': ordinary contract days must be "
                "supported by employment (2/2P) or an explicit no-income exclusion (2N). "
                "Benefit days do not end the employment registration.",
                name=self.employee_id.display_name,
            ))
        return facts
