"""Calibration report for settled combos.

The question: at the price we could actually have paid, did combos hit more
often than that price implies, and did that survive the fee? The builder price
and the FanDuel ratio are shown for context only and are not used for any
verdict.
"""

import math
import sqlite3

TARGET_N = 200


def poisson_binomial_tails(probs: list[float], k: int) -> tuple[float, float]:
    """Exact (P[X >= k], P[X <= k]) for a sum of independent Bernoulli(p_i)."""
    dist = [1.0]
    for p in probs:
        nxt = [0.0] * (len(dist) + 1)
        for i, mass in enumerate(dist):
            nxt[i] += mass * (1 - p)
            nxt[i + 1] += mass * p
        dist = nxt
    return sum(dist[k:]), sum(dist[: k + 1])


def poisson_tails(lam: float, k: int) -> tuple[float, float]:
    """(P[X >= k], P[X <= k]) for X ~ Poisson(lam)."""
    if lam <= 0:
        return (1.0 if k <= 0 else 0.0), 1.0
    pmf = [math.exp(-lam)]
    for i in range(1, k + 1):
        pmf.append(pmf[-1] * lam / i)
    lower = min(1.0, sum(pmf))
    upper = 1.0 - sum(pmf[:k]) if k > 0 else 1.0
    return max(0.0, upper), lower


def load_settled(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT c.id, c.rfq_yes_price AS price, c.taker_fee_per_contract AS fee,"
        " c.builder_payout_multiple AS builder_x, s.result"
        " FROM combos c JOIN settlements s ON s.combo_id = c.id"
        " WHERE c.rfq_yes_price IS NOT NULL AND c.status NOT IN ('expired', 'ungateable')"
        " ORDER BY c.id"
    ).fetchall()


def load_ungateable(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Settled combos that could not be gated on an executable price."""
    return conn.execute(
        "SELECT c.id, c.builder_payout_multiple AS builder_x, s.result"
        " FROM combos c JOIN settlements s ON s.combo_id = c.id"
        " WHERE c.status = 'ungateable' ORDER BY c.id"
    ).fetchall()


def ungateable_section(rows: list[sqlite3.Row]) -> list[str]:
    """Selection-bias check: how did combos we could not price do?"""
    if not rows:
        return []
    hits = sum(1 for r in rows if r["result"] == "win")
    lines = ["", f"Ungateable combos (no executable price), settled: {len(rows)}, hits: {hits}"]
    implied = [1 / r["builder_x"] for r in rows if r["builder_x"]]
    if implied:
        lines.append(
            f"    expected hits at builder-implied probability: {sum(implied):.2f} "
            f"(builder price only, not executable, so this is a rough guide)"
        )
    lines.append(
        "    Compare with the gated combos above: a big gap hints that gating on "
        "executable price filters the sample."
    )
    return lines


def build_report(rows: list[sqlite3.Row], ungateable: list[sqlite3.Row] | None = None) -> str:
    extra = ungateable_section(ungateable or [])
    n = len(rows)
    lines = ["Calibration report (paper log, one contract per combo at the executable price)"]
    if n == 0:
        lines.append("No settled combos with an executable price yet.")
        lines.append(f"Target is {TARGET_N}+ settled combos before drawing any conclusion.")
        lines += extra
        return "\n".join(lines)

    probs = [r["price"] for r in rows]
    fees = [r["fee"] if r["fee"] is not None else 0.0 for r in rows]
    hits = sum(1 for r in rows if r["result"] == "win")
    expected = sum(probs)
    sd = math.sqrt(sum(p * (1 - p) for p in probs))
    cost = sum(p + f for p, f in zip(probs, fees, strict=True))
    roi = (hits - cost) / cost

    lines += [
        f"Settled combos:            {n}",
        f"Actual hits:               {hits}",
        f"Expected hits at price:    {expected:.2f}  (sd {sd:.2f})",
        f"Hit surplus vs price:      {hits - expected:+.2f}",
        f"Average executable price:  {expected / n:.4f}",
        f"Average fee per contract:  {sum(fees) / n:.4f}",
        f"ROI at executable + fee:   {roi:+.1%}  (cost {cost:.2f}, returned {hits:.2f})",
    ]

    builder = [1 / r["builder_x"] for r in rows if r["builder_x"]]
    if builder:
        lines.append(
            f"Context: average builder-implied probability {sum(builder) / len(builder):.4f} "
            f"vs executable {expected / n:.4f}"
        )

    upper_pb, lower_pb = poisson_binomial_tails(probs, hits)
    upper_po, lower_po = poisson_tails(expected, hits)
    if hits >= expected:
        label = f"P(this many or more hits if the prices are fair, k>={hits})"
        pb, po = upper_pb, upper_po
    else:
        label = f"P(this few or fewer hits if the prices are fair, k<={hits})"
        pb, po = lower_pb, lower_po
    lines += [
        f"{label}:",
        f"    exact (Poisson-binomial) {pb:.4f}   Poisson approximation {po:.4f}",
        "    This is how likely a result this far from the price would be by luck alone.",
        "    It is not the probability that an edge exists.",
    ]

    lines.append("")
    if n < TARGET_N:
        lines.append(
            f"Sample size: {n} of {TARGET_N}. Too few to conclude anything; "
            "treat every number above as noise until the count is higher."
        )
    else:
        lines.append(
            f"Sample size: {n}, past the {TARGET_N} target. That is a minimum, not a guarantee; "
            "check that the log has no selection bias (only logging combos that looked good)."
        )
    lines.append(
        "An edge needs the true hit rate to beat executable price plus fee. "
        "Hits above the price are necessary, not sufficient: at a fair price the fee still "
        "makes a loss the default outcome."
    )
    lines += extra
    return "\n".join(lines)
