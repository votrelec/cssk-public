# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Read-only shipped-rule evidence for cooperative monthly extensions."""
import ast
from functools import lru_cache
from textwrap import dedent

from lxml import etree

from odoo import models
from odoo.tools import file_path


def _python(source):
    return ast.dump(ast.parse(dedent(source or "").strip()), include_attributes=False)


@lru_cache(maxsize=1)
def _shipped_rules():
    path = file_path("l10n_sk_hr_payroll_oca/data/hr_salary_rule_data.xml")
    result = {}
    for node in etree.parse(path).xpath("//record[@model='hr.salary.rule']"):
        fields = {field.get("name"): (field.text or "", field.get("ref")) for field in node.findall("field")}
        code = fields.get("code", ("", None))[0]
        if code in result:
            # Ambiguous definitions cannot establish a canonical formula.
            result[code] = None
        else:
            result[code] = fields
    return result


class CanonicalFundRule(models.Model):
    _inherit = "hr.salary.rule"

    def _l10n_sk_is_canonical_fund_rule(self):
        """Accept semantic copies; never use XML identity as arithmetic proof.

        Monthly consumers must call this before overriding native amounts,
        then independently compare those amounts with explicit recorder facts.
        Names, translations and display settings do not affect arithmetic.
        AccessError deliberately propagates; no sudo or live-source fallback.
        """
        self.ensure_one()
        source = _shipped_rules().get(self.code)
        if not source or not self.active or self.child_ids:
            return False
        for name in ("category_id", "parent_rule_id"):
            ref = source.get(name, ("", None))[1]
            expected = self.env.ref(ref if ref and "." in ref else "l10n_sk_hr_payroll_oca." + ref) if ref else False
            if self[name] != expected and (self[name] or expected):
                return False
        scalars = {"sequence": 5, "condition_select": "none", "amount_select": "fix"}
        for name, default in scalars.items():
            value = source.get(name, (str(default), None))[0].strip()
            if str(self[name]) != value:
                return False
        try:
            if self.condition_select == "python" and _python(self.condition_python) != _python(source.get("condition_python", ("", None))[0]):
                return False
            if self.condition_select == "range":
                for name in ("condition_range", "condition_range_min", "condition_range_max"):
                    expected = source.get(name, ("0" if name != "condition_range" else "contract.wage", None))[0].strip()
                    if name == "condition_range":
                        if _python(self[name]) != _python(expected):
                            return False
                    elif self[name] != float(expected):
                        return False
            if self.amount_select == "code":
                return _python(self.amount_python_compute) == _python(source.get("amount_python_compute", ("", None))[0])
            if _python(self.quantity) != _python(source.get("quantity", ("1.0", None))[0]):
                return False
            if self.amount_select == "fix":
                return self.amount_fix == float(source.get("amount_fix", ("0", None))[0])
            return self.amount_percentage == float(source.get("amount_percentage", ("0", None))[0]) and _python(self.amount_percentage_base) == _python(source.get("amount_percentage_base", ("", None))[0])
        except (SyntaxError, ValueError, TypeError):
            return False
