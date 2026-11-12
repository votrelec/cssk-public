# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMonthlyVersions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {
                "name": "Synthetic monthly version payments",
                "country_id": cls.env.ref("base.sk").id,
            }
        )
        cls.env.user.company_ids |= cls.company
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Synthetic two hours weekly",
                "company_id": cls.company.id,
                "attendance_ids": [
                    Command.create(
                        {
                            "name": "Monday",
                            "dayofweek": "0",
                            "hour_from": 8,
                            "hour_to": 10,
                            "day_period": "morning",
                        }
                    )
                ],
            }
        )
        cls.structure = cls.env.ref(
            "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_employee_salary"
        )

    def employee(self, wage):
        return (
            self.env["hr.employee"]
            .with_company(self.company)
            .create(
                {
                    "name": "Synthetic monthly employee",
                    "company_id": self.company.id,
                    "date_version": "2026-01-01",
                    "contract_date_start": "2026-01-01",
                    "resource_calendar_id": self.calendar.id,
                    "struct_id": self.structure.id,
                    "wage": wage,
                    "l10n_sk_tax_declaration_signed": True,
                    "l10n_sk_health_oop_claim": True,
                }
            )
        )

    def payment(self, employee, version=None):
        version = version or employee.version_id
        slip = (
            self.env["hr.payslip"]
            .with_company(self.company)
            .create(
                {
                    "employee_id": employee.id,
                    "company_id": self.company.id,
                    "contract_id": version.id,
                    "struct_id": self.structure.id,
                    "date_from": "2026-06-01",
                    "date_to": "2026-06-30",
                }
            )
        )
        slip.compute_sheet()
        # Native declaration fixtures confirm sources without an accounting app.
        slip.write({"state": "done"})
        return slip

    def check_combined(self, amount):
        employee = self.employee(amount)
        first = self.payment(employee)
        later = employee.version_id.copy({"date_version": "2026-06-16"})
        second = self.payment(employee, later)
        reference = self.payment(self.employee(2 * amount))
        for code in (
            "GROSS",
            "SICK",
            "PENSION",
            "DISABILITY",
            "UNEMPLOYMENT",
            "SICKEMPLOYER",
            "PENSIONEMPLOYER",
            "DISABILITYEMPLOYER",
            "UNEMPLOYMENTEMPLOYER",
            "RESERVEFUNDEMPLOYER",
            "ACCIDENT",
            "GUARANTEEEMPLOYER",
            "SHORTTIMEEMPLOYER",
            "HEALTH",
            "HEALTHEMPLOYER",
            "HEALTHDOPLATOK",
            "TAXBASE",
            "INCOMETAX",
            "NET",
        ):
            self.assertAlmostEqual(
                first.get_salary_line_total(code) + second.get_salary_line_total(code),
                reference.get_salary_line_total(code),
                places=2,
                msg=code,
            )
        self.assertFalse(second.l10n_sk_monthly_fund_warning)
        self.assertFalse(second.l10n_sk_monthly_tax_unverified)

    def test_version_change_keeps_health_op_minimum_and_tax_monthly(self):
        self.check_combined(200)

    def test_version_change_keeps_social_cap_and_uncapped_accident(self):
        self.check_combined(10000)
