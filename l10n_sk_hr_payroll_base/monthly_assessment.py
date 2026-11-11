# Copyright 2026 Data Dance s.r.o., votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Incremental monthly social assessments from actual retained fund facts.

The caller owns employment identity, applicability and effective source selection.
No paid amount, historical base or income is reconstructed from another value.
"""
from decimal import Decimal, InvalidOperation


def _number(value):
    if isinstance(value, bool):
        raise ValueError("Expected a finite monthly assessment number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Expected a finite monthly assessment number") from error
    if not number.is_finite():
        raise ValueError("Expected a finite monthly assessment number")
    return number


def _native_premium(base, rate):
    # Keep the shipped rule's disclosed floating-point guard and cent floor.
    # Applying it to the monthly rate bucket avoids flooring each instalment.
    return Decimal(int(round(float(base) * float(rate), 4))) / 100


def monthly_assessment(*, income, rate, maximum, deduction, previous):
    """Return this calculation's base and premium, preserving prior charges.

    ``previous`` contains actual income, base, rate and charged amount for this
    fund/side of the same monthly employment scope. Different rate buckets keep
    their own prior premiums; a later rate does not rewrite an earlier charge.
    ``maximum=None`` represents the uncapped accident base.
    """
    income, rate, deduction = map(_number, (income, rate, deduction))
    maximum = _number(maximum) if maximum is not None else None
    if income < 0 or not 0 <= rate <= 100 or deduction < 0:
        raise ValueError("Unsupported monthly assessment inputs")
    if maximum is not None and maximum < 0:
        raise ValueError("A monthly maximum cannot be negative")
    rows = []
    for row in previous:
        if set(row) != {"income", "base", "rate", "amount"}:
            raise ValueError("A prior monthly assessment is incomplete")
        values = {key: _number(value) for key, value in row.items()}
        if any(values[key] < 0 for key in ("income", "base", "amount")):
            raise ValueError("Signed corrections need their effective source workflow")
        if not 0 <= values["rate"] <= 100:
            raise ValueError("A prior fund rate is invalid")
        rows.append(values)
    total_income = income + sum((row["income"] for row in rows), Decimal(0))
    total_base = max(Decimal(0), total_income - deduction)
    if maximum is not None:
        total_base = min(total_base, maximum)
    increment = total_base - sum((row["base"] for row in rows), Decimal(0))
    if increment < 0:
        raise ValueError("Earlier assessments require an explicit correction")
    same_rate = [row for row in rows if row["rate"] == rate]
    bucket_base = increment + sum((row["base"] for row in same_rate), Decimal(0))
    charged = sum((row["amount"] for row in same_rate), Decimal(0))
    return {"base": increment, "amount": _native_premium(bucket_base, rate) - charged}
