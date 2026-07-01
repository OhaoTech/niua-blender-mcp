from __future__ import annotations


def score_item(item: dict, gates_pass: bool, lens_scores: dict[str, float]) -> dict:
    if gates_pass and lens_scores:
        overall = sum(lens_scores.values()) / len(lens_scores)
    else:
        overall = 0.0
    threshold = float(item.get("senior_threshold", 7.0))
    return {
        "id": item.get("id"),
        "asset_class": item.get("asset_class"),
        "gates_pass": gates_pass,
        "lens_scores": dict(lens_scores),
        "overall": overall,
        "senior_pass": bool(gates_pass) and overall >= threshold,
    }


def aggregate(cards: list[dict]) -> dict:
    n = len(cards)
    n_pass = sum(1 for c in cards if c["senior_pass"])
    mean_overall = (sum(c["overall"] for c in cards) / n) if n else 0.0
    per_class: dict[str, dict] = {}
    for c in cards:
        bucket = per_class.setdefault(c["asset_class"], {"n": 0, "n_pass": 0, "_sum": 0.0})
        bucket["n"] += 1
        bucket["n_pass"] += 1 if c["senior_pass"] else 0
        bucket["_sum"] += c["overall"]
    for bucket in per_class.values():
        bucket["mean_overall"] = bucket.pop("_sum") / bucket["n"]
    lens_totals: dict[str, list[float]] = {}
    for c in cards:
        for lens, val in c["lens_scores"].items():
            lens_totals.setdefault(lens, []).append(val)
    weakest = min(lens_totals, key=lambda k: sum(lens_totals[k]) / len(lens_totals[k])) if lens_totals else None
    return {
        "n_items": n,
        "n_senior_pass": n_pass,
        "pass_rate": (n_pass / n) if n else 0.0,
        "mean_overall": mean_overall,
        "per_class": per_class,
        "weakest_lens": weakest,
    }
