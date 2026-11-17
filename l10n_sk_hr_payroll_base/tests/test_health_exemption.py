# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import BaseCase, tagged
from ..applicability import PENSION_TYPES
from ..health_exemption import (
    agreement_health_exempt,
    pension_state_insured,
    pension_health_disabled,
)


@tagged("post_install", "-at_install")
class TestHealthExclusionPolicy(BaseCase):
    def test_recognised_invalidity_includes_ordinary_and_service_invalidity(self):
        for pension in (
            "disability",
            "disability_over_70",
            "disability_at_age",
            "disability_service",
        ):
            self.assertTrue(pension_health_disabled(pension))
        for pension in (False, "old_age", "early_old_age", "service_at_age"):
            self.assertFalse(pension_health_disabled(pension))

    def test_student_and_all_listed_pension_agreement_receipts(self):
        for pension in (False, *PENSION_TYPES):
            self.assertTrue(agreement_health_exempt("dobps", pension))
        for form in ("dovp", "dopc"):
            self.assertFalse(agreement_health_exempt(form, False))
            for pension in PENSION_TYPES:
                self.assertTrue(agreement_health_exempt(form, pension))

    def test_pensioner_employment_is_state_insured_without_excluding_income(self):
        for pension in PENSION_TYPES:
            self.assertFalse(agreement_health_exempt("none", pension))
            self.assertTrue(pension_state_insured(pension))
        self.assertFalse(pension_state_insured(False))

    def test_unqualified_service_pension_does_not_mean_service_at_retirement_age(self):
        for form in ("dovp", "dopc"):
            self.assertFalse(agreement_health_exempt(form, "service"))
            self.assertTrue(agreement_health_exempt(form, "service_at_age"))
