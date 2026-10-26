"""Token-usage and cost aggregation for the Tokenomics view.

All figures come from the API's own reported token counts stored in the `runs` table
(never invented). Projections are clearly separated from measured costs and use the
explicit assumptions in config (documented in the UI and README).
"""

from __future__ import annotations

from . import config, db


def _num(x):
    return x if isinstance(x, (int, float)) else 0


def summary() -> dict:
    runs = db.list_runs(limit=100000)
    measured = [r for r in runs if r.get("status") != "error"]
    n = len(measured)
    total_cost = sum(_num(r.get("cost_usd")) for r in measured)
    total_in = sum(_num(r.get("input_tokens")) for r in measured)
    total_cached = sum(_num(r.get("cached_tokens")) for r in measured)
    total_out = sum(_num(r.get("output_tokens")) for r in measured)

    by_agent = {}
    for r in measured:
        a = r.get("agent") or "unknown"
        d = by_agent.setdefault(a, {"runs": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0})
        d["runs"] += 1
        d["cost_usd"] += _num(r.get("cost_usd"))
        d["input_tokens"] += _num(r.get("input_tokens"))
        d["output_tokens"] += _num(r.get("output_tokens"))
    for d in by_agent.values():
        d["cost_usd"] = round(d["cost_usd"], 6)

    avg_cost = round(total_cost / n, 6) if n else 0.0
    any_cached_reported = any(r.get("cached_tokens") is not None for r in measured)

    return {
        "measured": {
            "runs": n,
            "errors": len(runs) - n,
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_per_run_usd": avg_cost,
            "input_tokens": total_in,
            "cached_tokens": total_cached if any_cached_reported else None,
            "cached_tokens_note": None if any_cached_reported else "API did not report cached tokens — unavailable",
            "output_tokens": total_out,
            "by_agent": by_agent,
            "model": config.MODEL,
        },
        "pricing": {
            "model": config.MODEL,
            "rates_per_1m": config.price_for(config.MODEL),
            "source": config.PRICING_SOURCE,
            "date": config.PRICING_DATE,
        },
        "projections": _projections(avg_cost),
    }


def _projections(avg_cost: float) -> dict:
    runs_user_month = config.RUNS_PER_USER_PER_DAY * config.ACTIVE_DAYS_PER_MONTH
    per_user_month = round(avg_cost * runs_user_month, 4)
    return {
        "assumptions": {
            "runs_per_user_per_day": config.RUNS_PER_USER_PER_DAY,
            "active_days_per_month": config.ACTIVE_DAYS_PER_MONTH,
            "runs_per_user_per_month": runs_user_month,
            "basis": "avg measured cost per run from this app's run log",
        },
        "cost_per_user_per_month_usd": per_user_month,
        "cost_100_users_month_usd": round(per_user_month * 100, 2),
        "cost_10000_users_month_usd": round(per_user_month * 10000, 2),
        "levers": [
            "Prompt caching of the stable system/safety preamble lowers repeated input cost.",
            "Limiting retrieved context (smaller k) cuts input tokens per run.",
            "Using a smaller model for simple actions (e.g. terminology) reduces output cost.",
            "Avoiding unnecessary agent calls — simple direct calls instead of full orchestration.",
        ],
        "disclaimer": "Projections are estimates from the explicit assumptions above applied to "
                      "measured per-run cost. They are NOT measured bills.",
    }
