# Copyright 2026 Data Dance s.r.o., votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from contextlib import contextmanager
from uuid import uuid4

from odoo import SUPERUSER_ID, api, sql_db
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2.errors import SerializationFailure


@tagged("post_install", "-at_install")
class TestFundSourceConcurrency(TransactionCase):
    @contextmanager
    def source_fixture(self, payslip=True, country="SK"):
        connection = sql_db.db_connect(self.env.cr.dbname)
        company_id = employee_id = slip_id = False
        partner_ids = []
        try:
            with connection.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {"lang": "en_US"})
                company = env["res.company"].create(
                    {
                        "name": "Social source concurrency " + uuid4().hex,
                        "country_id": env.ref("base." + country.lower()).id,
                        "currency_id": env.ref("base.EUR").id,
                    }
                )
                env.user.company_ids |= company
                env = env(context=dict(env.context, allowed_company_ids=company.ids))
                structure = env.ref(
                    "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_employee_salary"
                )
                employee = env["hr.employee"].create(
                    {
                        "name": company.name,
                        "company_id": company.id,
                        "date_version": "2026-01-01",
                        "contract_date_start": "2026-01-01",
                        "wage": 2000,
                        "struct_id": structure.id,
                        "l10n_sk_tax_declaration_signed": False,
                    }
                )
                partner_ids = (company.partner_id | employee.work_contact_id).ids
                version = employee.version_id
                company_id, employee_id = company.id, employee.id
                if payslip:
                    slip = env["hr.payslip"].create(
                        self.slip_values(employee, version, structure)
                    )
                    slip.compute_sheet()
                    slip_id = slip.id
                version_id, structure_id = version.id, structure.id
                cr.commit()
            yield connection, company_id, employee_id, version_id, structure_id, slip_id
        finally:
            if company_id:
                with connection.cursor() as cr:
                    env = api.Environment(
                        cr,
                        SUPERUSER_ID,
                        {"lang": "en_US", "allowed_company_ids": [company_id]},
                    )
                    # Committed fixtures are isolated to this random employee;
                    # production retention deliberately forbids ORM removal.
                    cr.execute(
                        "DELETE FROM hr_payslip WHERE employee_id = %s", [employee_id]
                    )
                    versions = (
                        env["hr.version"]
                        .with_context(active_test=False)
                        .search([("employee_id", "=", employee_id)])
                    )
                    env["hr.employee"].browse(employee_id).exists().unlink()
                    # Native employee unlink can detach historical versions.
                    # These are committed synthetic fixtures, not real history.
                    versions.exists().unlink()
                    self.assertFalse(versions.exists())
                    env["res.company"].browse(company_id).exists().unlink()
                    env = env(
                        context=dict(
                            env.context, allowed_company_ids=self.env.companies.ids
                        )
                    )
                    env["res.partner"].browse(partner_ids).exists().unlink()
                    cr.commit()
                    self.assertFalse(env["res.partner"].browse(partner_ids).exists())

    @staticmethod
    def slip_values(employee, version, structure):
        return {
            "name": "Social source concurrency",
            "employee_id": employee.id,
            "company_id": employee.company_id.id,
            "contract_id": version.id,
            "struct_id": structure.id,
            "date_from": "2026-03-01",
            "date_to": "2026-03-31",
        }

    def test_concurrent_version_change_retries_before_confirmation_then_rejects_stale(
        self,
    ):
        with self.source_fixture() as (
            connection,
            company,
            _employee,
            version,
            _structure,
            slip,
        ):
            with connection.cursor() as stale, connection.cursor() as writer:
                context = {"allowed_company_ids": [company], "lang": "en_US"}
                old_env = api.Environment(stale, SUPERUSER_ID, context)
                new_env = api.Environment(writer, SUPERUSER_ID, context)
                self.assertTrue(
                    old_env["hr.payslip"].browse(slip).l10n_sk_fund_assessment
                )
                new_env["hr.version"].browse(version).wage = 2200
                writer.commit()
                with (
                    mute_logger("odoo.sql_db"),
                    self.assertRaises(SerializationFailure),
                ):
                    old_env["hr.payslip"].browse(slip).with_context(
                        without_compute_sheet=True
                    ).action_payslip_done()
                stale.rollback()
            with connection.cursor() as retry:
                env = api.Environment(retry, SUPERUSER_ID, context)
                with self.assertRaisesRegex(UserError, "sources changed"):
                    env["hr.payslip"].browse(slip).with_context(
                        without_compute_sheet=True
                    ).action_payslip_done()
                self.assertNotEqual(env["hr.payslip"].browse(slip).state, "done")

    def test_concurrent_version_insert_retries_the_old_employee_snapshot(self):
        with self.source_fixture(payslip=False) as (
            connection,
            company,
            employee,
            version,
            _structure,
            _slip,
        ):
            context = {"allowed_company_ids": [company], "lang": "en_US"}
            with connection.cursor() as stale, connection.cursor() as writer:
                old_env = api.Environment(stale, SUPERUSER_ID, context)
                new_env = api.Environment(writer, SUPERUSER_ID, context)
                self.assertEqual(old_env["hr.employee"].browse(employee).wage, 2000)
                new_env["hr.version"].browse(version).copy(
                    {"date_version": "2026-03-16", "wage": 2200}
                )
                writer.commit()
                with (
                    mute_logger("odoo.sql_db"),
                    self.assertRaises(SerializationFailure),
                ):
                    old_env["hr.employee"].browse(employee)._l10n_sk_lock_fund_source()
                stale.rollback()

    def test_source_payslip_nonkey_lock_is_compatible_with_foreign_key_readers(self):
        with self.source_fixture() as (
            connection,
            company,
            employee,
            version,
            structure,
            slip,
        ):
            context = {"allowed_company_ids": [company], "lang": "en_US"}
            with connection.cursor() as child, connection.cursor() as coordinator:
                # PostgreSQL's FK check acquires exactly this key-share lock.
                child.execute(
                    "SELECT id FROM hr_payslip WHERE id = %s FOR KEY SHARE", [slip]
                )
                coordinator.execute("SET LOCAL lock_timeout='1s'")
                other = api.Environment(coordinator, SUPERUSER_ID, context)
                other["hr.payslip"].browse(slip)._l10n_sk_lock_fund_payslips()
                coordinator.commit()
                child.rollback()

    def test_new_confirmed_peer_retries_then_requires_recalculation(self):
        with self.source_fixture() as (
            connection,
            company,
            employee,
            version,
            structure,
            slip,
        ):
            context = {"allowed_company_ids": [company], "lang": "en_US"}
            with connection.cursor() as stale, connection.cursor() as writer:
                old = api.Environment(stale, SUPERUSER_ID, context)
                new = api.Environment(writer, SUPERUSER_ID, context)
                self.assertTrue(old["hr.payslip"].browse(slip).l10n_sk_fund_assessment)
                peer = new["hr.payslip"].create(
                    self.slip_values(
                        new["hr.employee"].browse(employee),
                        new["hr.version"].browse(version),
                        new["hr.payroll.structure"].browse(structure),
                    )
                )
                peer.compute_sheet()
                peer.with_context(without_compute_sheet=True).action_payslip_done()
                new.flush_all()
                writer.commit()
                with (
                    mute_logger("odoo.sql_db"),
                    self.assertRaises(SerializationFailure),
                ):
                    old["hr.payslip"].browse(slip).with_context(
                        without_compute_sheet=True
                    ).action_payslip_done()
                stale.rollback()
            with connection.cursor() as retry:
                env = api.Environment(retry, SUPERUSER_ID, context)
                pending = env["hr.payslip"].browse(slip)
                with self.assertRaises(UserError):
                    pending.with_context(
                        without_compute_sheet=True
                    ).action_payslip_done()
                pending.compute_sheet()
                pending.with_context(without_compute_sheet=True).action_payslip_done()
                env.flush_all()
                retry.commit()

    def test_parameter_insertion_retries_and_does_not_commit_stale_confirmation(self):
        with self.source_fixture() as (
            connection,
            company,
            _employee,
            _version,
            _structure,
            slip,
        ):
            context = {"allowed_company_ids": [company], "lang": "en_US"}
            inserted = False
            try:
                with connection.cursor() as stale, connection.cursor() as writer:
                    old = api.Environment(stale, SUPERUSER_ID, context)
                    new = api.Environment(writer, SUPERUSER_ID, context)
                    self.assertTrue(
                        old["hr.payslip"].browse(slip).l10n_sk_fund_assessment
                    )
                    parameter = new.ref(
                        "l10n_sk_hr_payroll_oca.rule_parameter_monthly_taxable_max"
                    )
                    value = (
                        new["hr.rule.parameter.value"]
                        .with_context(default_rule_parameter_id=parameter.id)
                        .create({"date_from": "2026-03-01", "parameter_value": "18000"})
                    )
                    inserted = value.id
                    writer.commit()
                    with (
                        mute_logger("odoo.sql_db"),
                        self.assertRaises(SerializationFailure),
                    ):
                        old["hr.payslip"].browse(slip).with_context(
                            without_compute_sheet=True
                        ).action_payslip_done()
                    stale.rollback()
                with connection.cursor() as retry:
                    env = api.Environment(retry, SUPERUSER_ID, context)
                    pending = env["hr.payslip"].browse(slip)
                    with self.assertRaises(UserError):
                        pending.with_context(
                            without_compute_sheet=True
                        ).action_payslip_done()
                    self.assertNotEqual(pending.state, "done")
            finally:
                if inserted:
                    with connection.cursor() as cleanup:
                        env = api.Environment(cleanup, SUPERUSER_ID, context)
                        env["hr.rule.parameter.value"].browse(inserted).unlink()
                        cleanup.commit()

    def test_czech_version_does_not_wait_for_unrelated_slovak_source(self):
        with (
            self.source_fixture(payslip=False) as sk,
            self.source_fixture(payslip=False, country="CZ") as cz,
        ):
            connection, company, employee, *_ = sk
            _, foreign_company, foreign_employee, foreign_version, *_ = cz
            with connection.cursor() as held, connection.cursor() as writer:
                first = api.Environment(
                    held, SUPERUSER_ID, {"allowed_company_ids": [company]}
                )
                second = api.Environment(
                    writer, SUPERUSER_ID, {"allowed_company_ids": [foreign_company]}
                )
                first["hr.employee"].browse(employee)._l10n_sk_lock_fund_source()
                writer.execute("SET LOCAL lock_timeout='1s'")
                before = (
                    second["hr.employee"]
                    .browse(foreign_employee)
                    .l10n_sk_fund_source_epoch
                )
                second["hr.version"].browse(foreign_version).wage = 2400
                second.flush_all()
                writer.commit()
                self.assertEqual(
                    second["hr.employee"]
                    .browse(foreign_employee)
                    .l10n_sk_fund_source_epoch,
                    before,
                )
                held.rollback()

    def test_other_slovak_payroll_does_not_take_a_global_salary_rule_epoch(self):
        with self.source_fixture() as first, self.source_fixture() as other:
            connection, company, employee, *_ = first
            _, other_company, _employee, _version, _structure, other_slip = other
            with connection.cursor() as held, connection.cursor() as writer:
                env = api.Environment(
                    held, SUPERUSER_ID, {"allowed_company_ids": [company]}
                )
                independent = api.Environment(
                    writer, SUPERUSER_ID, {"allowed_company_ids": [other_company]}
                )
                env["hr.employee"].browse(employee)._l10n_sk_lock_fund_source()
                writer.execute("SET LOCAL lock_timeout='1s'")
                independent["hr.payslip"].browse(other_slip).compute_sheet()
                independent.flush_all()
                writer.commit()
                held.rollback()
