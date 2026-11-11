# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Monthly health OP and minimum, independent of payroll and calendars.

Act 580/2004 sections 16(16-18), 16a; Dôvera's current OP guidance
requires upward cent rounding of OP. Do not round gross income here.
"""

from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP

CENT = Decimal("0.01")


def _number(value):
    if isinstance(value, bool):
        raise ValueError("Expected a finite health calculation number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Expected a finite health calculation number") from error
    if not result.is_finite():
        raise ValueError("Expected a finite health calculation number")
    return result


def _days(days, month_days):
    if (
        type(days) is not int
        or type(month_days) is not int
        or not 28 <= month_days <= 31
        or not 0 <= days <= month_days
    ):
        raise ValueError("Invalid health calendar day counts")


def monthly_op(income, eligible_income, maximum, phaseout_end, days, month_days):
    """Cap OP by eligible income, prorate once, then round upward.

    Other same-employer income participates in phase-out but cannot receive
    OP itself. Eligibility/notice/concurrent-employer checks belong to callers.
    A negative correction carries no new monthly allowance.
    """
    income, eligible, maximum, end = map(
        _number, (income, eligible_income, maximum, phaseout_end)
    )
    _days(days, month_days)
    if maximum <= 0 or end <= maximum or eligible < 0 or eligible > max(income, 0):
        raise ValueError("Invalid monthly health OP inputs")
    if income <= 0 or eligible == 0 or days == 0:
        return Decimal(0)
    allowance = max(
        Decimal(0),
        maximum - maximum / (end - maximum) * max(Decimal(0), income - maximum),
    )
    result = (min(eligible, allowance) * days / month_days).quantize(
        CENT, rounding=ROUND_UP
    )
    return min(result, eligible)


def monthly_minimum(base, employee_rate, employer_rate, days, month_days):
    """Floor each statutory advance first, then prorate the monthly sum."""
    base, employee_rate, employer_rate = map(
        _number, (base, employee_rate, employer_rate)
    )
    _days(days, month_days)
    if base < 0 or not 0 <= employee_rate <= 100 or not 0 <= employer_rate <= 100:
        raise ValueError("Invalid monthly health minimum inputs")
    full = sum(
        (base * rate / 100).quantize(CENT, rounding=ROUND_DOWN)
        for rate in (employee_rate, employer_rate)
    )
    return (full * days / month_days).quantize(CENT, rounding=ROUND_DOWN)
