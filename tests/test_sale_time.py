import unittest
from sale_time import choose_sale_time


class SaleTimeTests(unittest.TestCase):
    received = "2026-10-13T18:00:00Z"

    def test_future_is_flagged_and_original_is_not_called_purchase_time(self):
        stamp, status = choose_sale_time("2028-04-14T23:31:24Z", self.received)
        self.assertEqual(stamp, self.received)
        self.assertEqual(status, "receipt_fallback:future_device_time")

    def test_offline_original_date_preserved(self):
        for source in (None, "server_synced"):
            stamp, status = choose_sale_time("2026-09-10T09:00:00-06:00", self.received, source)
            self.assertEqual(stamp, "2026-09-10T15:00:00Z")
            self.assertNotIn("fallback", status)

    def test_unsynced_boot_is_explicitly_uncertain(self):
        self.assertEqual(choose_sale_time("2026-10-12T10:00:00Z", self.received, "unverified"),
                         (self.received, "receipt_fallback:unverified_device_time"))

    def test_invalid_dates(self):
        for raw in (None, "", "broken", "2026-10-13T12:00:00", "1999-01-01T00:00:00Z"):
            self.assertEqual(choose_sale_time(raw, self.received)[1], "receipt_fallback:invalid_device_time")

    def test_small_clock_tolerance(self):
        self.assertEqual(choose_sale_time("2026-10-13T18:00:02Z", self.received, "server_synced")[1], "server_synced")


if __name__ == "__main__":
    unittest.main()
