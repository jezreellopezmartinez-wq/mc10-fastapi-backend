from __future__ import annotations

import argparse
import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from import_backup import load_backup


def merge(connection: psycopg.Connection, backup: dict) -> dict:
    if any(not row.get("sale_id") for row in backup["sales"]):
        raise ValueError("La sincronizacion requiere sale_id en todas las ventas")

    with connection.cursor() as cursor:
        before = {}
        for table in ("machines", "products", "sales", "alerts"):
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
            before[table] = int(cursor.fetchone()["total"])

        cursor.executemany(
            """
            INSERT INTO machines (
              serial, name, model, profile_id, profile_title, location, status,
              version, cloud_enabled, last_seen, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (serial) DO UPDATE SET
              name = EXCLUDED.name, model = EXCLUDED.model,
              profile_id = EXCLUDED.profile_id, profile_title = EXCLUDED.profile_title,
              location = EXCLUDED.location, status = EXCLUDED.status,
              version = EXCLUDED.version, cloud_enabled = EXCLUDED.cloud_enabled,
              last_seen = EXCLUDED.last_seen, updated_at = EXCLUDED.updated_at
            """,
            [
                (
                    row["serial"], row.get("name") or "", row.get("model") or "MC10",
                    row.get("profile_id") or "", row.get("profile_title") or "",
                    row.get("location") or "Sin ubicacion", row.get("status") or "En linea",
                    row.get("version") or "", 1 if row.get("cloud_enabled", True) else 0,
                    row.get("last_seen") or "", row.get("created_at") or "",
                    row.get("updated_at") or "",
                )
                for row in backup["machines"]
            ],
        )

        cursor.executemany(
            """
            INSERT INTO products (
              machine_serial, product_id, name, relay, price, dispense_size,
              ms, calibration_ms, active, category, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (machine_serial, product_id) DO UPDATE SET
              name = EXCLUDED.name, relay = EXCLUDED.relay, price = EXCLUDED.price,
              dispense_size = EXCLUDED.dispense_size, ms = EXCLUDED.ms,
              calibration_ms = EXCLUDED.calibration_ms, active = EXCLUDED.active,
              category = EXCLUDED.category, updated_at = EXCLUDED.updated_at
            """,
            [
                (
                    row["machine_serial"], row["product_id"], row.get("name") or "",
                    int(row.get("relay") or row["product_id"]), float(row.get("price") or 0),
                    float(row.get("dispense_size") or 0), int(row.get("ms") or 0),
                    int(row.get("calibration_ms") or 0), 1 if row.get("active", True) else 0,
                    row.get("category") or "", row.get("updated_at") or "",
                )
                for row in backup["products"]
            ],
        )

        cursor.executemany(
            """
            INSERT INTO sales (
              machine_serial, sale_id, request_id, product_id, product_name,
              method, payment_method, amount, units, currency, source, app_version,
              channel, relay, local_sale_counter, dispatch_status, sold_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sale_id) WHERE sale_id IS NOT NULL AND sale_id <> '' DO NOTHING
            """,
            [
                (
                    row["machine_serial"], row["sale_id"], row.get("request_id"),
                    row.get("product_id"), row.get("product_name") or "Venta manual",
                    row.get("method") or "MEI", row.get("payment_method") or "",
                    float(row.get("amount") or 0), float(row.get("units") or 0),
                    row.get("currency") or "MXN", row.get("source") or "",
                    row.get("app_version") or "", int(row.get("channel") or 0),
                    int(row.get("relay") or 0), int(row.get("local_sale_counter") or 0),
                    row.get("dispatch_status") or "", row.get("sold_at") or "",
                    row.get("created_at") or "",
                )
                for row in backup["sales"]
            ],
        )

        for row in backup["alerts"]:
            cursor.execute(
                """
                SELECT 1 FROM alerts
                WHERE machine_serial = %s AND type = %s AND title = %s
                  AND detail = %s AND created_at = %s
                LIMIT 1
                """,
                (
                    row["machine_serial"], row.get("type") or "warning",
                    row.get("title") or "Alerta", row.get("detail") or "",
                    row.get("created_at") or "",
                ),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    """
                    INSERT INTO alerts (machine_serial, type, title, detail, active, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row["machine_serial"], row.get("type") or "warning",
                        row.get("title") or "Alerta", row.get("detail") or "",
                        1 if row.get("active", True) else 0, row.get("created_at") or "",
                    ),
                )

        after = {}
        for table in ("machines", "products", "sales", "alerts"):
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
            after[table] = int(cursor.fetchone()["total"])

        sale_ids = [str(row["sale_id"]) for row in backup["sales"]]
        cursor.execute("SELECT COUNT(*) AS total FROM sales WHERE sale_id = ANY(%s)", (sale_ids,))
        found_sales = int(cursor.fetchone()["total"])
        if found_sales != len(set(sale_ids)):
            raise ValueError("No se localizaron todas las ventas del respaldo en PostgreSQL")

    return {
        "before": before,
        "after": after,
        "added": {key: after[key] - before[key] for key in before},
        "backup_totals": backup["totals"],
        "matched_backup_sales": found_sales,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--database-url-file", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", required=True)
    args = parser.parse_args()

    database_url = args.database_url_file.read_text(encoding="utf-8").strip()
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise ValueError("Conexion PostgreSQL no valida")
    backup = load_backup(args.backup.resolve())
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        result = merge(connection, backup)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
