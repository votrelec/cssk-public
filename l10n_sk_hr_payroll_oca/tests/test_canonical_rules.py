# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCanonicalFundRule(TransactionCase):
    def health(self):
        return self.env["hr.salary.rule"].search([("code", "=", "HEALTH"), ("company_id", "=", False)], limit=1)

    def test_shipped_and_semantic_copy(self):
        rule = self.health()
        self.assertTrue(rule._l10n_sk_is_canonical_fund_rule())
        copy = rule.copy({"name": "Own readable label", "amount_python_compute": "# own comment\n" + rule.amount_python_compute})
        self.assertTrue(copy._l10n_sk_is_canonical_fund_rule())

    def test_changed_amount_and_recorder_are_not_canonical(self):
        rule = self.health().copy()
        rule.amount_python_compute += "\nresult -= 1\nif 'l10n_sk_fund_record' in locals():\n    l10n_sk_fund_record['amount'] += 1\n"
        self.assertFalse(rule._l10n_sk_is_canonical_fund_rule())

    def test_changed_category_or_order_or_condition(self):
        rule = self.health().copy()
        rule.sequence += 1
        self.assertFalse(rule._l10n_sk_is_canonical_fund_rule())
        rule.sequence -= 1
        rule.condition_select = "python"
        rule.condition_python = "result = True"
        self.assertFalse(rule._l10n_sk_is_canonical_fund_rule())
