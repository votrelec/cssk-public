# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Calendar consistency against real bridge-owned disability fields."""

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHealthCalendarProfile(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))

    def source(self, disabled_on=None):
        employee = self.env["hr.employee"].create(
            {"name": "Synthetic calendar profile"}
        )
        intervals = [
            Command.create(
                {"kind": "2", "date_start": "2026-06-01", "date_end": "2026-06-30"}
            )
        ]
        if disabled_on:
            intervals.append(
                Command.create(
                    {
                        "kind": "disabled",
                        "date_start": disabled_on,
                        "date_end": "2026-06-30",
                    }
                )
            )
        calendar = self.env["l10n.sk.health.calendar"].create(
            {
                "company_id": employee.company_id.id,
                "employee_id": employee.id,
                "month": "2026-06-01",
                "evidence": "Synthetic reviewed employment and disability decision",
                "complete": True,
                "interval_ids": intervals,
            }
        )
        calendar.action_review()
        return employee.version_id

    def test_disabled_profile_is_not_silently_replaced_by_a_non_disabled_month(self):
        version = self.source()
        version.l10n_sk_ztp = True
        with self.assertRaisesRegex(UserError, "disability disagreement"):
            version._l10n_sk_health_calendar_context("2026-06-01")
        self.assertTrue(version.l10n_sk_ztp)

    def test_disability_beginning_during_month_is_not_a_false_profile_conflict(self):
        version = self.source(disabled_on="2026-06-15")
        for profile in (False, True):
            version.l10n_sk_ztp = profile
            facts = version._l10n_sk_health_calendar_context("2026-06-01")
            self.assertTrue(facts["disability_in_month"])
            self.assertEqual(facts["insured_days"], 30)
            self.assertEqual(facts["minimum_days"], 0)
            self.assertEqual(version.l10n_sk_ztp, profile)
