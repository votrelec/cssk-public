# Copyright 2026 Data Dance s.r.o., votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Mixed-country HR updates must not acquire unrelated Slovak payroll epochs."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFundSourceScope(TransactionCase):
    def _employee(self, country):
        company = self.env["res.company"].create(
            {
                "name": "Source scope " + country,
                "country_id": self.env.ref("base." + country.lower()).id,
            }
        )
        self.env.user.company_ids |= company
        return (
            self.env["hr.employee"]
            .with_company(company)
            .create(
                {
                    "name": "Source scope fixture",
                    "company_id": company.id,
                    "date_version": "2026-01-01",
                    "contract_date_start": "2026-01-01",
                    "wage": 2000,
                }
            )
        )

    def test_czech_version_and_direct_coordinator_leave_epoch_unchanged(self):
        employee = self._employee("CZ")
        before = employee.l10n_sk_fund_source_epoch
        employee.version_id.wage = 2200
        employee._l10n_sk_lock_fund_source()
        self.assertEqual(employee.l10n_sk_fund_source_epoch, before)

    def test_unrelated_slovak_note_does_not_change_the_fund_source(self):
        employee = self._employee("SK")
        before = employee.l10n_sk_fund_source_epoch
        employee.version_id.additional_note = "HR contact note"
        self.assertEqual(employee.l10n_sk_fund_source_epoch, before)

    def test_relevant_slovak_version_change_advances_the_source(self):
        employee = self._employee("SK")
        before = employee.l10n_sk_fund_source_epoch
        employee.version_id.wage = 2200
        self.assertGreater(employee.l10n_sk_fund_source_epoch, before)

    def test_default_employee_link_is_coordinated_on_version_create(self):
        employee = self._employee("SK")
        before = employee.l10n_sk_fund_source_epoch
        self.env["hr.version"].with_company(employee.company_id).with_context(
            default_employee_id=employee.id
        ).create(
            {
                "date_version": "2026-02-01",
                "wage": 2200,
            }
        )
        self.assertGreater(employee.l10n_sk_fund_source_epoch, before)

    def test_mixed_country_batch_coordinates_only_the_slovak_employee(self):
        slovak = self._employee("SK")
        czech = self._employee("CZ")
        employees = (
            self.env["hr.employee"]
            .browse([slovak.id, czech.id])
            .with_context(
                allowed_company_ids=[slovak.company_id.id, czech.company_id.id]
            )
        )
        before = {
            employee.id: employee.l10n_sk_fund_source_epoch for employee in employees
        }
        employees._l10n_sk_lock_fund_source()
        self.assertGreater(slovak.l10n_sk_fund_source_epoch, before[slovak.id])
        self.assertEqual(czech.l10n_sk_fund_source_epoch, before[czech.id])
