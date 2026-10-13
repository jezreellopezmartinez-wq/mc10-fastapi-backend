"""Timestamp policy for NEW sales. Existing history is never rewritten here."""
from datetime import datetime, timedelta, timezone


def choose_sale_time(raw: str | None, received: str, clock_source: str | None = None):
    arrival = datetime.fromisoformat(received.replace("Z", "+00:00"))
    status = "legacy_device"
    try:
        sale = datetime.fromisoformat((raw or "").replace("Z", "+00:00"))
        if sale.tzinfo is None:
            raise ValueError("timezone required")
        sale = sale.astimezone(timezone.utc)
        if sale > arrival + timedelta(minutes=5):
            status = "future_device_time"
        elif sale.year < 2020:
            status = "invalid_device_time"
        elif clock_source == "unverified":
            status = "unverified_device_time"
        else:
            # Old offline sales remain on their original date, not receipt date.
            source = "server_synced" if clock_source == "server_synced" else "legacy_device"
            return sale.isoformat().replace("+00:00", "Z"), source
    except (ValueError, TypeError, OverflowError):
        status = "invalid_device_time"
    return received, "receipt_fallback:" + status
