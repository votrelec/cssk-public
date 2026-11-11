# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Project recorded payroll facts into a 514 row, without recalculating payroll.

Assessment bases follow section 13(17)'s downward cent conversion. Amounts
already charged by payroll use their currency-cent representation. In
particular, neither a tariff nor an OP is reconstructed from a rounded charge.
The declaration adapter supplies registration days and the recorded profile.
"""

from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP


def number(value):
    if isinstance(value, bool):
        raise ValueError("A health assessment number cannot be a boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("A health assessment number must be finite") from exc
    if not result.is_finite():
        raise ValueError("A health assessment number must be finite")
    return result


def base_cents(value):
    return number(value).quantize(Decimal(".01"), rounding=ROUND_DOWN)


def amount_cents(value):
    return number(value).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)


def row_from_assessments(records, health, *, op_eligible, days, direction=1):
    """Return one source row or None for an actually zero excluded receipt.

    ``direction`` is supplied by the payroll engine's existing refund adapter.
    This function never reads an employee's current card or changes a source.
    Consolidating distinct slips/person identities belongs to the collector.
    """
    if type(direction) is not int or direction not in (-1, 1):
        raise ValueError("Use the payroll engine's signed record direction")
    if type(days) is not int or not 0 <= days <= 31:
        raise ValueError("Supply reviewed calendar days for the health row")
    for key in ("exempt", "disabled", "minimum_opt_out", "minimum_exempt"):
        if type(health.get(key)) is not bool:
            raise ValueError("Supply a complete recorded health profile")
    if type(op_eligible) is not bool:
        raise ValueError("Supply the recorded OP income classification")
    selected = {}
    for record in records:
        if record["fund"] == "health":
            side = record["side"]
            if side in selected:
                raise ValueError("A health assessment side occurs more than once")
            selected[side] = record
    if set(selected) != {"employee", "employer"}:
        raise ValueError("Supply both actual health assessment sides")
    ee, er = selected["employee"], selected["employer"]
    if health["exempt"]:
        if any(number(record[key]) for record in (ee, er) for key in ("base", "amount")):
            raise ValueError("Excluded health income has nonzero payroll assessments")
        return None
    facts = ee["facts"]
    if "income" not in facts or "op" not in facts:
        raise ValueError("Retain the charging rule's actual income and OP facts")
    topup = amount_cents(facts.get("topup", 0))
    employee = amount_cents(ee["amount"]) - topup
    employer = amount_cents(er["amount"])
    minimum_not_applied = health["minimum_opt_out"] or health["minimum_exempt"]
    if minimum_not_applied and topup:
        raise ValueError("An exempt monthly minimum has a nonzero top-up")
    income = amount_cents(facts["income"])
    employer_base = base_cents(er["base"])
    base = base_cents(ee["base"])
    op = amount_cents(facts["op"])
    if not op_eligible and op:
        raise ValueError("An OP-ineligible receipt has a nonzero payroll OP")
    shorttime_base = er["facts"].get("shorttime_base")
    if shorttime_base is not None:
        shorttime_base = base_cents(shorttime_base)
        if shorttime_base != employer_base:
            raise ValueError("The short-time support basis disagrees with payroll")
    elif employer_base != base_cents(facts["income"]):
        raise ValueError("Retain the legal reason for a different employer health base")
    row = {
        "disabled": health["disabled"],
        "days": days,
        "rate_employee": number(ee["rate"]),
        "rate_employer": number(er["rate"]),
        "income": income,
        "base": base,
        "employee": employee,
        "employer": employer,
        "topup": topup,
        "total": employee + employer + topup,
        "op_income": income if op_eligible else Decimal(0),
        "other_income": Decimal(0) if op_eligible else income,
        "op": op,
        "exempt_income": Decimal(0),
        "shorttime_base": shorttime_base,
        "minimum_opt_out": int(minimum_not_applied),
        "premium_assessed": bool(base or employer_base or employee or employer or topup),
    }
    for key in (
        "income", "base", "employee", "employer", "topup", "total", "op_income",
        "other_income", "op", "exempt_income", "shorttime_base",
    ):
        if row[key] is not None:
            row[key] *= direction
    return row
