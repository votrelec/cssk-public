# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Monthly health targets and signed instalment differences from recorded facts.

Callers own native engagement/profile identity and effective source selection.
Amounts and bases are never recovered from a premium by division. An OP or
minimum refund may be negative in one instalment; validation belongs to the
reconciled monthly assessment, not each fragment in isolation.
"""
from decimal import Decimal, InvalidOperation

from .health_calculation import monthly_minimum, monthly_op

FIELDS = frozenset({"income", "base", "employer_base", "employee", "employer", "op", "topup"})
POLICY_FIELDS = frozenset({
    "employee_rate", "employer_rate", "op_maximum", "op_phaseout_end", "op_days", "month_days",
    "minimum_base", "minimum_days", "apply_op", "minimum_exempt", "exempt",
})


def number(value):
    if isinstance(value, bool):
        raise ValueError("A monthly health number must be finite")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("A monthly health number must be finite") from error
    if not result.is_finite():
        raise ValueError("A monthly health number must be finite")
    return result


def _text(value):
    value = number(value)
    result = format(value, "f")
    return (result.rstrip("0").rstrip(".") if "." in result else result) if value else "0"


def health_policy(**values):
    """Canonical, JSON-safe monthly parameters retained by charging rules."""
    if set(values) != POLICY_FIELDS:
        raise ValueError("A monthly health policy is incomplete")
    for key in ("apply_op", "minimum_exempt", "exempt"):
        if type(values[key]) is not bool:
            raise ValueError("Monthly health flags must be explicit")
    days = values["month_days"]
    if type(days) is not int or not 28 <= days <= 31:
        raise ValueError("Supply actual health calendar month days")
    if any(type(values[key]) is not int or not 0 <= values[key] <= days
           for key in ("op_days", "minimum_days")):
        raise ValueError("Supply actual monthly health day counts")
    numeric = {key: number(values[key]) for key in (
        "employee_rate", "employer_rate", "op_maximum", "op_phaseout_end", "minimum_base",
    )}
    if (any(not 0 <= numeric[key] <= 100 for key in ("employee_rate", "employer_rate"))
            or numeric["op_maximum"] <= 0 or numeric["op_phaseout_end"] <= numeric["op_maximum"]
            or numeric["minimum_base"] < 0 or (values["exempt"] and values["apply_op"])):
        raise ValueError("Invalid monthly health policy")
    return dict(values, **{key: _text(value) for key, value in numeric.items()})


def native_premium(base, rate):
    """The shipped canonical health rule's cent floor and float guard."""
    return Decimal(int(round(float(number(base)) * float(number(rate)), 4))) / 100


def health_total(income, policy):
    """One canonical monthly assessment, also the independent single-slip target."""
    policy = health_policy(**policy)
    income = number(income)
    if income < 0:
        raise ValueError("Signed income corrections require their effective source workflow")
    result = {key: Decimal(0) for key in FIELDS}
    result["income"] = income
    if policy["exempt"]:
        return result
    op = monthly_op(
        income, income, policy["op_maximum"], policy["op_phaseout_end"],
        policy["op_days"], policy["month_days"],
    ) if policy["apply_op"] else Decimal(0)
    # Match the native rule's actual subtraction, including its recorded
    # binary artefact; the 514 wire base is rounded only after consolidation.
    base = number(max(0.0, float(income) - float(op))) if policy["apply_op"] else income
    employee = native_premium(base, policy["employee_rate"])
    employer = native_premium(income, policy["employer_rate"])
    minimum = Decimal(0) if policy["minimum_exempt"] else monthly_minimum(
        policy["minimum_base"], policy["employee_rate"], policy["employer_rate"],
        policy["minimum_days"], policy["month_days"],
    )
    return dict(result, base=base, employer_base=income, employee=employee, employer=employer,
                op=op, topup=max(Decimal(0), minimum - employee - employer))


def monthly_health(*, income, policy, previous):
    """Return actual incremental facts while preserving all prior source charges.

    Every previous row contains its actual income, both bases, raw charges,
    OP and topup. Signed OP/topup fragments are allowed. Their monthly sum
    must match the canonical target before another exact difference is made.
    A custom, legacy, orphaned or different-policy source is not guessed.
    """
    policy = health_policy(**policy)
    income = number(income)
    if income < 0 or not isinstance(previous, list):
        raise ValueError("Unsupported monthly health sources")
    prior = {key: Decimal(0) for key in FIELDS}
    for row in previous:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError("A prior monthly health source is incomplete")
        parsed = {key: number(value) for key, value in row.items()}
        if parsed["income"] < 0:
            raise ValueError("Select the effective native refund sources first")
        for key in FIELDS:
            prior[key] += parsed[key]
    if previous:
        expected = health_total(prior["income"], policy)
        if any(prior[key] != expected[key] for key in FIELDS):
            raise ValueError("Prior health charges require an explicit source correction")
    target = health_total(prior["income"] + income, policy)
    delta = {key: target[key] - prior[key] for key in FIELDS}
    delta["income"] = income
    return dict(delta, amount_employee=delta["employee"] + delta["topup"],
                total=delta["employee"] + delta["employer"] + delta["topup"], monthly_total=target)
