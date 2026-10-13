"""No real network/DB: exercise the actual handler and INSERT against SQLite."""
import sqlite3
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from fastapi.testclient import TestClient
import main


class SaleTimeApiTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE sales (
          id INTEGER PRIMARY KEY, machine_serial TEXT, sale_id TEXT UNIQUE, request_id TEXT,
          product_id INTEGER, product_name TEXT, method TEXT, payment_method TEXT,
          amount REAL, units REAL, currency TEXT, source TEXT, app_version TEXT,
          channel INTEGER, relay INTEGER, local_sale_counter INTEGER, dispatch_status TEXT,
          sold_at TEXT, created_at TEXT, original_sold_at TEXT, device_sold_at TEXT, time_status TEXT)""")
        self.db.execute("CREATE TABLE machines (serial TEXT, status TEXT, last_seen TEXT, updated_at TEXT)")
        self.db.execute("INSERT INTO machines(serial) VALUES ('test')")

    def tearDown(self):
        self.db.close()

    def save(self, **fields):
        with patch.object(main, "get_db", return_value=self.db), \
             patch.object(main, "get_machine_or_404"), \
             patch.object(main, "now_iso", return_value="2026-10-13T18:00:00Z"):
            return main.create_sale("test", main.SaleCreate(**fields))

    def test_future_sale_saved_once_with_original_for_audit(self):
        fields = dict(sale_id="one", amount=27, sold_at="2028-04-14T23:31:24Z")
        first = self.save(**fields)
        again = self.save(**fields)
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(first["sold_at"], "2026-10-13T18:00:00Z")
        self.assertEqual(first["original_sold_at"], fields["sold_at"])
        self.assertEqual(first["time_status"], "receipt_fallback:future_device_time")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 1)

    def test_synced_sale_keeps_date_when_uploaded_later(self):
        result = self.save(sale_id="offline", amount=10, clock_source="server_synced",
                           sold_at="2026-10-10T10:00:00Z", device_sold_at="2028-01-01T00:00:00Z")
        self.assertEqual(result["sold_at"], "2026-10-10T10:00:00Z")
        self.assertEqual(result["time_status"], "server_synced")
        self.assertEqual(result["device_sold_at"], "2028-01-01T00:00:00Z")

    def test_time_endpoint_is_dynamic_and_uncached(self):
        # Not entering TestClient context prevents production startup migration.
        client = TestClient(main.app)
        response = client.get("/time")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertLess(abs(response.json()["epoch_ms"] - datetime.now(timezone.utc).timestamp()*1000), 5000)
        self.assertEqual(response.json()["business_timezone"], main.BUSINESS_TIMEZONE_NAME)


if __name__ == "__main__":
    unittest.main()
