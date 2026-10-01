"""Read-only sales reports. Aggregates never depend on the page size."""
from datetime import datetime, time, timedelta, timezone

SALE_TIME = "CASE WHEN COALESCE(sold_at, '') <> '' THEN sold_at ELSE created_at END"
SALE_TIMESTAMP = f"CAST(({SALE_TIME}) AS TIMESTAMP WITH TIME ZONE)"
DATE_RANGE = f"{SALE_TIMESTAMP} >= CAST(? AS TIMESTAMP WITH TIME ZONE) AND {SALE_TIMESTAMP} < CAST(? AS TIMESTAMP WITH TIME ZONE)"
CARD = "(LOWER(COALESCE(NULLIF(payment_method, ''), method, '')) IN ('card', 'tarjeta', 'terminal'))"


def utc_text(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def totals(conn, where, params):
    row = conn.execute(f"""
        SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS amount,
          COALESCE(SUM(CASE WHEN {CARD} THEN amount ELSE 0 END), 0) AS card_amount,
          COALESCE(SUM(CASE WHEN {CARD} THEN 1 ELSE 0 END), 0) AS card_count
        FROM sales WHERE {where}
    """, tuple(params)).fetchone()
    count, card_count = int(row["count"]), int(row["card_count"])
    amount, card_amount = round(float(row["amount"]), 2), round(float(row["card_amount"]), 2)
    return dict(count=count, amount=amount, card_count=card_count,
                card_amount=card_amount, cash_count=count-card_count,
                cash_amount=round(amount-card_amount, 2))


def sales_report(conn, serial, zone, *, period="all", payment="all", query="",
                 limit=20, offset=0, snapshot=None, now=None):
    now = now or datetime.now(zone)
    start = datetime.combine(now.astimezone(zone).date(), time.min, tzinfo=zone)
    if snapshot is None:
        snapshot = int(conn.execute("SELECT COALESCE(MAX(id), 0) AS id FROM sales WHERE machine_serial = ?", (serial,)).fetchone()["id"])
    base = "machine_serial = ? AND id <= ?"
    base_params = [serial, snapshot]
    overall = totals(conn, base, base_params)
    daily = []
    for days_ago in range(6, -1, -1):
        day = start - timedelta(days=days_ago)
        result = totals(conn, base + " AND " + DATE_RANGE,
                        base_params + [utc_text(day), utc_text(day+timedelta(days=1))])
        daily.append(dict(date=day.date().isoformat(), **result))
    where, params = base, list(base_params)
    if period != "all":
        days = {"today": 1, "7d": 7, "30d": 30}[period]
        where += " AND " + DATE_RANGE
        params += [utc_text(start-timedelta(days=days-1)), utc_text(start+timedelta(days=1))]
    if payment != "all":
        where += " AND " + (CARD if payment == "card" else f"NOT {CARD}")
    if query:
        # Escape LIKE metacharacters: a product search is literal text.
        escaped = query.lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
        where += " AND LOWER(product_name) LIKE ? ESCAPE '!'"
        params.append("%" + escaped + "%")
    filtered = totals(conn, where, params)
    top = conn.execute(f"SELECT product_name, COUNT(*) AS n FROM sales WHERE {where} GROUP BY product_name ORDER BY n DESC, product_name LIMIT 1", tuple(params)).fetchone()
    rows = conn.execute(f"SELECT * FROM sales WHERE {where} ORDER BY {SALE_TIMESTAMP} DESC, id DESC LIMIT ? OFFSET ?", tuple(params+[limit, offset])).fetchall()
    return dict(version=1, totals=overall, today=daily[-1], daily=daily,
                filtered=filtered, top_product=top["product_name"] if top else None,
                items=[dict(row) for row in rows], snapshot=snapshot,
                offset=offset, limit=limit, has_more=offset+len(rows)<filtered["count"])
