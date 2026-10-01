import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from sales_report import sales_report, utc_text, SALE_TIME, SALE_TIMESTAMP


class TestConnection(sqlite3.Connection):
    def execute(self, sql, params=()):
        # SQLite's equivalent to PostgreSQL timezone-aware timestamp casts.
        sql = sql.replace(SALE_TIMESTAMP, f"julianday({SALE_TIME})")
        sql = sql.replace("CAST(? AS TIMESTAMP WITH TIME ZONE)", "julianday(?)")
        return super().execute(sql, params)


class SalesReportTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:", factory=TestConnection)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("CREATE TABLE sales (id INTEGER PRIMARY KEY, machine_serial TEXT, amount REAL, method TEXT, payment_method TEXT, product_name TEXT, sold_at TEXT, created_at TEXT)")
        self.zone = timezone(timedelta(hours=-6))
        self.now = datetime(2026, 9, 29, 12, tzinfo=self.zone)
        for i in range(145):
            day = self.now if i >= 120 else self.now-timedelta(days=2)
            self.add(i+1, "a", 10, day, "card" if i % 2 else "cash")
        self.add(146, "b", 9999, self.now, "cash")

    def tearDown(self):
        self.conn.close()

    def add(self, id, machine, amount, day, payment, product="Agua"):
        self.conn.execute("INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (id, machine, amount, "Terminal" if payment == "card" else "MEI", payment, product, utc_text(day), utc_text(self.now)))

    def report(self, **kw):
        return sales_report(self.conn, "a", self.zone, now=self.now, **kw)

    def test_totals_over_100_and_today_over_20(self):
        r = self.report()
        self.assertEqual(r["totals"]["count"], 145)
        self.assertEqual(r["totals"]["amount"], 1450)
        self.assertEqual(r["today"]["count"], 25)
        self.assertEqual(r["today"]["amount"], 250)
        self.assertEqual(len(r["items"]), 20)
        self.assertEqual(sum(d["amount"] for d in r["daily"]), 1450)
        self.assertEqual(r["totals"]["cash_amount"]+r["totals"]["card_amount"], 1450)

    def test_new_sale_increases_total_and_snapshot_is_stable(self):
        before = self.report()
        self.add(147, "a", 18, self.now, "card")
        after = self.report()
        self.assertEqual(after["totals"]["amount"], 1468)
        self.assertEqual(after["today"]["amount"], 268)
        ids = []
        for offset in range(0, 145, 20):
            r = self.report(offset=offset, snapshot=before["snapshot"])
            ids += [row["id"] for row in r["items"]]
        self.assertEqual(len(ids), 145)
        self.assertEqual(len(set(ids)), 145)
        self.assertNotIn(147, ids)

    def test_filters_aggregate_before_paginating(self):
        r = self.report(period="today", payment="cash", query="Agua", limit=5)
        self.assertEqual(r["filtered"]["count"], 13)
        self.assertEqual(r["filtered"]["amount"], 130)
        self.assertEqual(len(r["items"]), 5)
        self.assertEqual(self.report(query="%' OR 1=1 --")["filtered"]["count"], 0)
        self.assertEqual(self.report(query="%")["filtered"]["count"], 0)

    def test_midnight_and_delayed_sync_keep_sale_day(self):
        midnight = self.now.replace(hour=0)
        self.add(147, "a", 2, midnight-timedelta(seconds=1), "cash")
        self.add(148, "a", 3, midnight, "cash")
        self.add(149, "a", 4, midnight+timedelta(days=1), "cash")
        r = self.report()
        self.assertEqual(r["today"]["amount"], 253)
        self.assertEqual(r["daily"][-2]["amount"], 2)
        self.assertEqual(r["totals"]["amount"], 1459)

    def test_empty_machine(self):
        r = sales_report(self.conn, "empty", self.zone, now=self.now)
        self.assertEqual(r["totals"]["amount"], 0)
        self.assertEqual(r["items"], [])
        self.assertFalse(r["has_more"])

    def test_timestamp_offsets_and_fractional_midnight(self):
        self.add(147, "a", 5, self.now, "cash")
        self.conn.execute("UPDATE sales SET sold_at = ? WHERE id = 147", ("2026-09-29T00:00:00.000-06:00",))
        self.assertEqual(self.report()["today"]["amount"], 255)


if __name__ == "__main__":
    unittest.main()
