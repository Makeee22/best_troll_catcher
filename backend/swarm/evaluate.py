THRESHOLDS = (0, 0.05, 0.1, 0.2, 0.3, 0.5)


def _ratio(a, b):
    return round(a / b, 4) if b else None


def _counts(accounts, cut):
    """accounts: (is_bot, confidence or None) pairs. Flagged = in a cluster with confidence >= cut."""
    tp = sum(1 for bot, c in accounts if bot and c is not None and c >= cut)
    fp = sum(1 for bot, c in accounts if not bot and c is not None and c >= cut)
    fn = sum(1 for bot, c in accounts if bot and (c is None or c < cut))
    tn = sum(1 for bot, c in accounts if not bot and (c is None or c < cut))
    return {"min_confidence": cut, "true_positives": tp, "false_positives": fp, "false_negatives": fn,
            "true_negatives": tn, "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn),
            "false_positive_rate": _ratio(fp, fp + tn)}


def evaluate(con, min_confidence):
    """Metrics from the profiles' label column, or None when no profile has a label."""
    rows = con.execute("""
        select p.label, exists (select 1 from item i where i.username = p.username) as has_content, c.confidence
        from profiles p
        left join member m on m.username = p.username
        left join cluster c on c.cluster = m.cluster
        where p.label is not null""").fetchall()
    if not rows:
        return None
    with_content = [(label, conf) for label, has, conf in rows if has]
    with_content = [(label.strip().lower(), conf) for label, conf in with_content if label.strip()]
    accounts = [(label.startswith("bot"), conf) for label, conf in with_content]
    by_label = {}
    for label, conf in with_content:
        entry = by_label.setdefault(label, {"accounts": 0, "flagged": 0})
        entry["accounts"] += 1
        entry["flagged"] += conf is not None and conf >= min_confidence
    return {"labelled_accounts": len(with_content), "labelled_without_content": len(rows) - len(with_content),
            "at_min_confidence": _counts(accounts, min_confidence),
            "by_threshold": [_counts(accounts, t) for t in THRESHOLDS],
            "by_label": by_label}
