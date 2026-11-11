# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from copy import deepcopy
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFundLifecycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))
        cls.company = cls.env["res.company"].create(
            {
                "name": "Source lifecycle company",
                "country_id": cls.env.ref("base.sk").id,
            }
        )
        cls.env.user.company_ids |= cls.company
        cls.structure = cls.env.ref(
            "l10n_sk_hr_payroll_oca.hr_payroll_structure_sk_employee_salary"
        )
        cls.employee = (
            cls.env["hr.employee"]
            .with_company(cls.company)
            .create(
                {
                    "name": "Source lifecycle employee",
                    "company_id": cls.company.id,
                    "date_version": "2026-01-01",
                    "contract_date_start": "2026-01-01",
                    "wage": 2000,
                    "struct_id": cls.structure.id,
                }
            )
        )
        cls.version = cls.employee.version_id

    def _slip(self):
        slip = (
            self.env["hr.payslip"]
            .with_company(self.company)
            .create(
                {
                    "name": "Lifecycle source",
                    "company_id": self.company.id,
                    "employee_id": self.employee.id,
                    "contract_id": self.version.id,
                    "struct_id": self.structure.id,
                    "date_from": "2026-06-01",
                    "date_to": "2026-06-30",
                    "worked_days_line_ids": [
                        Command.create(
                            {
                                "name": "Worked",
                                "code": "WORK100",
                                "contract_id": self.version.id,
                                "number_of_days": 22,
                                "number_of_hours": 176,
                            }
                        )
                    ],
                }
            )
        )
        slip.compute_sheet()
        return slip

    def _confirm(self, slip):
        return slip.with_context(without_compute_sheet=True).action_payslip_done()

    def _monthly_pair(self):
        self.version.write({"wage": 1200, "l10n_sk_tax_declaration_signed": True})
        reference = self._slip()
        expected = reference.line_ids.filtered(
            lambda row: row.code == "INCOMETAX"
        ).total
        self.version.wage = 600
        return self._slip(), self._slip(), expected

    def test_precomputed_monthly_batch_refuses_atomically_then_sequentially_works(self):
        first, second, expected = self._monthly_pair()
        frozen = (
            deepcopy(first.l10n_sk_fund_assessment),
            first._l10n_sk_fund_salary_facts(),
        )
        with self.assertRaises(UserError):
            (first | second).with_context(
                without_compute_sheet=True
            ).action_payslip_done()
        self.assertNotEqual(first.state, "done")
        self.assertNotEqual(second.state, "done")
        self.assertTrue(
            all(
                not value
                for value in (first | second).mapped("l10n_sk_fund_confirmed_at")
            )
        )
        self.assertEqual(
            (first.l10n_sk_fund_assessment, first._l10n_sk_fund_salary_facts()), frozen
        )
        self._confirm(first)
        second.compute_sheet()
        self._confirm(second)
        self.assertAlmostEqual(
            sum(
                (first | second)
                .line_ids.filtered(lambda row: row.code == "INCOMETAX")
                .mapped("total")
            ),
            expected,
            places=2,
        )

    def test_default_monthly_batch_confirmation_uses_prior_confirmed_amounts(self):
        first, second, expected = self._monthly_pair()
        (first | second).action_payslip_done()
        self.assertEqual(set((first | second).mapped("state")), {"done"})
        self.assertAlmostEqual(
            sum(
                (first | second)
                .line_ids.filtered(lambda row: row.code == "INCOMETAX")
                .mapped("total")
            ),
            expected,
            places=2,
        )
        self.assertTrue(
            all(
                slip.l10n_sk_fund_assessment["profile"]["monthly_tax"]["complete"]
                for slip in (first, second)
            )
        )

    def test_combined_source_and_closing_values_validate_after_source_change(self):
        slip = self._slip()
        original = (
            deepcopy(slip.l10n_sk_fund_assessment),
            slip._l10n_sk_fund_salary_facts(),
        )
        line = slip.line_ids[:1]
        payloads = [
            {"date_to": "2026-07-31"},
            {
                "input_line_ids": [
                    Command.create(
                        {
                            "name": "New input",
                            "code": "SOURCE_CHANGE",
                            "amount": 17,
                            "contract_id": self.version.id,
                        }
                    )
                ]
            },
            {"line_ids": [Command.update(line.id, {"amount": line.amount + 1})]},
        ]
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(UserError):
                slip.write(dict(payload, state="done"))
            self.assertEqual(str(slip.date_to), "2026-06-30")
            self.assertNotEqual(slip.state, "done")
            self.assertFalse(slip.l10n_sk_fund_confirmed_at)
            self.assertEqual(
                (slip.l10n_sk_fund_assessment, slip._l10n_sk_fund_salary_facts()),
                original,
            )
        slip.write({"name": "Reviewed source", "state": "done"})
        self.assertEqual(slip.name, "Reviewed source")
        self.assertEqual(slip.state, "done")

    def test_retained_done_paid_and_batch_retry_ignore_later_live_predecessors(self):
        first, second, expected = self._monthly_pair()
        self._confirm(first)
        second.compute_sheet()
        self._confirm(second)
        frozen = (
            deepcopy(first.l10n_sk_fund_assessment),
            first._l10n_sk_fund_salary_facts(),
            first.l10n_sk_fund_confirmed_at,
        )
        state_field = self.env["hr.payslip"]._fields["state"]
        # Stock OCA has no paid state. Model the selection extension used by
        # payment adapters, without pretending to execute an actual payment.
        with (
            patch.object(
                state_field, "selection", state_field.selection + [("paid", "Paid")]
            ),
            patch.object(
                state_field, "_selection", set(state_field._selection) | {"paid"}
            ),
        ):
            first.write({"state": "paid"})
            self.assertEqual(first.state, "paid")
            (first | second).action_payslip_done()
            self.assertEqual(first.state, "paid")
            (first | second).write({"state": "paid"})
            (first | second).write({"state": "paid"})
            self.assertEqual(set((first | second).mapped("state")), {"paid"})
        self.assertEqual(
            (
                first.l10n_sk_fund_assessment,
                first._l10n_sk_fund_salary_facts(),
                first.l10n_sk_fund_confirmed_at,
            ),
            frozen,
        )

    def test_closing_values_cannot_forge_generated_status_or_refund_links(self):
        slip = self._slip()
        for field in (
            "l10n_sk_fund_source_signature",
            "l10n_sk_monthly_tax_unverified",
        ):
            with self.assertRaises(UserError):
                slip.write({"name": "Injected", "state": "done", field: False})
            self.assertEqual(slip.name, "Lifecycle source")
            self.assertNotEqual(slip.state, "done")
        self._confirm(slip)
        candidate = slip.copy({"credit_note": True})
        draft = self._slip()
        with self.assertRaises(UserError):
            draft.write({"refunded_id": candidate.id, "state": "done"})
        with self.assertRaises(UserError):
            draft.copy({"refunded_id": candidate.id})
        with self.assertRaises(UserError):
            draft.with_context(default_refunded_id=candidate.id).copy()
        self.assertFalse(draft.refunded_id)
        slip.refund_sheet()
        self.assertTrue(slip.refunded_id)

    def test_denied_create_and_closing_check_access_before_employee_epoch(self):
        slip = self._slip()
        group = self.env["res.groups"].create(
            {"name": "Read-only payroll source review"}
        )
        self.env["ir.model.access"].create(
            {
                "name": "Read-only payroll source review",
                "model_id": self.env["ir.model"]._get_id("hr.payslip"),
                "group_id": group.id,
                "perm_read": True,
                "perm_write": False,
                "perm_create": False,
                "perm_unlink": False,
            }
        )
        reader = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Read-only payroll reviewer",
                    "login": "source-reader@example.invalid",
                    "company_id": self.company.id,
                    "company_ids": [Command.set(self.company.ids)],
                    "group_ids": [
                        Command.set(
                            [
                                self.env.ref("base.group_user").id,
                                self.env.ref("hr.group_hr_manager").id,
                                group.id,
                            ]
                        )
                    ],
                }
            )
        )
        readonly = slip.with_user(reader).with_company(self.company)
        self.assertFalse(readonly.env.user.has_group("payroll.group_payroll_user"))
        employee_type = type(self.employee)
        original = employee_type._l10n_sk_lock_fund_source
        calls = []

        def employee_gate(employees):
            calls.extend(employees.ids)
            return original(employees)

        operations = [
            lambda: readonly.write({"state": "done"}),
            lambda: readonly.env["hr.payslip"].create(
                {
                    "name": "Denied create",
                    "company_id": self.company.id,
                    "employee_id": self.employee.id,
                    "contract_id": self.version.id,
                    "struct_id": self.structure.id,
                    "date_from": "2026-06-01",
                    "date_to": "2026-06-30",
                }
            ),
        ]
        with patch.object(employee_type, "_l10n_sk_lock_fund_source", employee_gate):
            for operation in operations:
                calls.clear()
                with self.subTest(operation=operation):
                    with self.assertRaises(AccessError):
                        operation()
                    self.assertEqual(calls, [])

    def test_changed_wage_cannot_confirm_stale_calculation(self):
        slip = self._slip()
        self.version.wage = 2200
        with self.assertRaises(UserError):
            self._confirm(slip)
        self.assertNotEqual(slip.state, "done")
        slip.compute_sheet()
        self._confirm(slip)
        self.assertEqual(slip.state, "done")

    def test_prevent_compute_and_direct_state_use_same_source_check(self):
        slip = self._slip()
        self.env["ir.config_parameter"].sudo().set_param(
            "payroll.prevent_compute_on_confirm", True
        )
        slip.invalidate_recordset(["prevent_compute_on_confirm"])
        self.assertTrue(slip.prevent_compute_on_confirm)
        self.version.l10n_sk_agreement_oop = True
        with self.assertRaises(UserError):
            slip.action_payslip_done()
        with self.assertRaises(UserError):
            slip.write({"state": "done"})

    def test_new_confirmed_predecessor_invalidates_later_draft(self):
        first = self._slip()
        later = self._slip()
        self._confirm(first)
        with self.assertRaises(UserError):
            self._confirm(later)
        later.compute_sheet()
        self._confirm(later)
        self.assertEqual(later.state, "done")

    def test_dated_parameter_insertion_invalidates_calculation(self):
        slip = self._slip()
        parameter = self.env["hr.rule.parameter"].search(
            [("code", "=", "l10n_sk_monthly_taxable_max")], limit=1
        )
        self.assertTrue(parameter)
        self.env["hr.rule.parameter.value"].create(
            {
                "rule_parameter_id": parameter.id,
                "date_from": "2026-06-01",
                "parameter_value": "18000",
            }
        )
        with self.assertRaises(UserError):
            self._confirm(slip)

    def test_confirmed_sources_and_children_remain_immutable_after_cancel(self):
        slip = self._slip()
        self._confirm(slip)
        facts = deepcopy(slip.l10n_sk_fund_assessment)
        for operation in [
            lambda: slip.compute_sheet(),
            lambda: slip.write({"state": "draft"}),
            lambda: slip.line_ids[:1].write({"amount": 1}),
            lambda: slip.worked_days_line_ids[:1].unlink(),
            lambda: self.env["hr.payslip.input"]
            .with_context(default_payslip_id=slip.id)
            .create({"name": "Injected", "code": "INJECT", "amount": 1}),
        ]:
            with self.assertRaises(UserError):
                operation()
        slip.write({"state": "cancel"})
        with self.assertRaises(UserError):
            slip.write({"state": "draft"})
        self.assertEqual(slip.l10n_sk_fund_assessment, facts)

    def test_copy_and_native_refund_preserve_full_increment_and_one_direction(self):
        slip = self._slip()
        self._confirm(slip)
        facts = deepcopy(slip.l10n_sk_fund_assessment)
        clone = slip.copy()
        self.assertFalse(clone.l10n_sk_fund_assessment)
        self.assertFalse(clone.l10n_sk_fund_source_signature)
        self.assertFalse(clone.refunded_id)
        self.version.wage = 5000
        slip.refund_sheet()
        refund = slip.refunded_id
        self.assertEqual(
            refund._l10n_sk_fund_salary_facts(), slip._l10n_sk_fund_salary_facts()
        )
        self.assertEqual(refund._cssk_fund_record_direction(), -1)
        self.assertFalse((slip | refund)._cssk_effective_fund_payslips())
        self.assertEqual(slip.l10n_sk_fund_assessment, facts)
        self.assertTrue(refund.l10n_sk_fund_confirmed_at)
        self._confirm(refund)
        with self.assertRaises(UserError):
            slip.refund_sheet()

    def test_generated_values_and_defaults_cannot_forge_confirmation(self):
        slip = self._slip()
        for field in [
            "l10n_sk_fund_source_signature",
            "l10n_sk_fund_confirmed_at",
            "l10n_sk_fund_refund_original_id",
        ]:
            with self.assertRaises(UserError):
                slip.write({field: False})
            with self.assertRaises(UserError):
                slip.with_context(**{"default_" + field: False}).copy()

    def test_child_reparent_checks_both_original_and_new_parent(self):
        original = self._slip()
        self._confirm(original)
        draft = self._slip()
        with self.assertRaises(UserError):
            original.line_ids[:1].write({"slip_id": draft.id})
        with self.assertRaises(UserError):
            draft.line_ids[:1].write({"slip_id": original.id})

    def test_future_parameter_value_does_not_change_current_month(self):
        slip = self._slip()
        self.env["hr.rule.parameter.value"].create(
            {
                "rule_parameter_id": self.env.ref(
                    "l10n_sk_hr_payroll_oca.rule_parameter_monthly_taxable_max"
                ).id,
                "date_from": "2028-01-01",
                "parameter_value": "30000",
            }
        )
        self._confirm(slip)
        self.assertEqual(slip.state, "done")

    def test_parameter_used_in_native_quantity_invalidates_custom_calculation(self):
        parameter = self.env["hr.rule.parameter"].create(
            {
                "name": "Native quantity source",
                "code": "source_controls_quantity",
                "country_id": self.env.ref("base.sk").id,
            }
        )
        value = self.env["hr.rule.parameter.value"].create(
            {
                "rule_parameter_id": parameter.id,
                "date_from": "2026-01-01",
                "parameter_value": "2",
            }
        )
        rule = self.structure.get_all_rules().filtered(
            lambda line: line.code == "HEALTH"
        )
        rule.write({"amount_select": "fix", "amount_fix": -100,
                    "quantity": "payslip.rule_parameter('source_controls_quantity')"})
        slip = self._slip()
        self.assertFalse(slip.l10n_sk_fund_assessment)
        value.parameter_value = "3"
        with self.assertRaises(UserError):
            self._confirm(slip)
        slip.compute_sheet()
        self._confirm(slip)
        self.assertEqual(slip.state, "done")

    def test_changed_rule_invalidates_but_confirmed_history_stays_readable(self):
        first = self._slip()
        self._confirm(first)
        rows = first._cssk_recorded_fund_bases()
        later = self._slip()
        rule = self.structure.get_all_rules().filtered(
            lambda line: line.code == "HEALTH"
        )
        rule.amount_python_compute += "\nresult = result + 0.01"
        with self.assertRaises(UserError):
            self._confirm(later)
        self.assertEqual(first._cssk_recorded_fund_bases(), rows)

    def test_optional_custom_metadata_absent_still_confirms_native_amount(self):
        rule = self.structure.get_all_rules().filtered(
            lambda line: line.code == "HEALTH"
        )
        rule.amount_python_compute = "result = -123.45"
        slip = self._slip()
        self.assertFalse(slip.l10n_sk_fund_assessment)
        self._confirm(slip)
        self.assertEqual(slip.state, "done")
        self.assertEqual(
            slip.line_ids.filtered(lambda line: line.code == "HEALTH").total, -123.45
        )
