from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row


TABLES = ("machines", "products", "sales", "alerts")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rows_from_optional_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = read_json(path)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    raise ValueError(f"Formato JSON no valido: {path}")


def verify_checksums(root: Path) -> int:
    checksum_file = root / "SHA256SUMS.txt"
    if not checksum_file.exists():
        raise ValueError("Falta SHA256SUMS.txt")

    checked = 0
    for raw_line in checksum_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        expected, relative = line.split(maxsplit=1)
        target = root / relative.strip().replace("\\", os.sep)
        if not target.is_file():
            raise ValueError(f"Falta archivo respaldado: {relative}")
        actual = hashlib.sha256(target.read_bytes()).hexdigest().upper()
        if actual != expected.upper():
            raise ValueError(f"Checksum incorrecto: {relative}")
        checked += 1
    return checked


def ensure_unique(rows: Iterable[dict[str, Any]], fields: tuple[str, ...], label: str) -> None:
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = tuple(row.get(field) for field in fields)
        if key in seen:
            raise ValueError(f"Duplicado en {label}: {key}")
        seen.add(key)


def load_backup(root: Path) -> dict[str, Any]:
    checked = verify_checksums(root)
    manifest = read_json(root / "manifest.json")
    if manifest.get("schema") != "mc10-cloud-backup-v1":
        raise ValueError("Version de respaldo no compatible")
    if manifest.get("secrets_included") is not False:
        raise ValueError("El respaldo no confirma la exclusion de secretos")

    machines = read_json(root / "data" / "machines.json")
    if not isinstance(machines, list):
        raise ValueError("machines.json debe contener una lista")

    products: list[dict[str, Any]] = []
    sales: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    machine_serials = {str(row.get("serial", "")) for row in machines}

    for serial in sorted(machine_serials):
        if not (serial.isdigit() and len(serial) == 16):
            raise ValueError(f"Serie no valida: {serial}")
        machine_dir = root / "data" / "machines" / serial
        for label, destination in (
            ("products", products),
            ("sales", sales),
            ("alerts", alerts),
        ):
            for row in rows_from_optional_file(machine_dir / f"{label}.json"):
                if str(row.get("machine_serial", serial)) != serial:
                    raise ValueError(f"Relacion incorrecta en {label} de {serial}")
                destination.append(row)

    expected = {key: int(manifest["totals"][key]) for key in TABLES}
    actual = {
        "machines": len(machines),
        "products": len(products),
        "sales": len(sales),
        "alerts": len(alerts),
    }
    if actual != expected:
        raise ValueError(f"Conteos distintos al manifiesto: esperado={expected}, actual={actual}")

    ensure_unique(machines, ("serial",), "machines")
    ensure_unique(products, ("machine_serial", "product_id"), "products")
    ensure_unique(sales, ("id",), "sales.id")
    ensure_unique(alerts, ("id",), "alerts.id")
    sale_ids = [row for row in sales if row.get("sale_id")]
    ensure_unique(sale_ids, ("sale_id",), "sales.sale_id")

    for label, rows in (("products", products), ("sales", sales), ("alerts", alerts)):
        unknown = sorted({str(row.get("machine_serial", "")) for row in rows} - machine_serials)
        if unknown:
            raise ValueError(f"{label} hace referencia a maquinas inexistentes: {unknown}")

    return {
        "manifest": manifest,
        "checksums_verified": checked,
        "machines": machines,
        "products": products,
        "sales": sales,
        "alerts": alerts,
        "totals": actual,
        "sales_amount": round(sum(float(row.get("amount") or 0) for row in sales), 2),
        "sales_units": round(sum(float(row.get("units") or 0) for row in sales), 6),
    }


def insert_backup(connection: psycopg.Connection, backup: dict[str, Any]) -> str:
    with connection.cursor() as cursor:
        destination = {}
        for table in TABLES:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
            destination[table] = int(cursor.fetchone()["total"])

        expected = backup["totals"]
        if destination == expected:
            cursor.execute("SELECT COALESCE(SUM(amount), 0) AS amount, COALESCE(SUM(units), 0) AS units FROM sales")
            totals = cursor.fetchone()
            if round(float(totals["amount"]), 2) != backup["sales_amount"]:
                raise ValueError("La base tiene los mismos conteos pero un total de ventas distinto")
            if round(float(totals["units"]), 6) != backup["sales_units"]:
                raise ValueError("La base tiene los mismos conteos pero unidades distintas")
            return "already_present"
        if any(destination.values()):
            raise ValueError(f"La base destino no esta vacia: {destination}")

        cursor.executemany(
            """
            INSERT INTO machines (
              serial, name, model, profile_id, profile_title, location, status,
              version, cloud_enabled, last_seen, created_at, updated_at,
              archived_at, archive_reason
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    row["serial"], row.get("name") or "", row.get("model") or "MC10",
                    row.get("profile_id") or "", row.get("profile_title") or "",
                    row.get("location") or "Sin ubicacion", row.get("status") or "En linea",
                    row.get("version") or "", 1 if row.get("cloud_enabled", True) else 0,
                    row.get("last_seen") or "", row.get("created_at") or "",
                    row.get("updated_at") or "", row.get("archived_at") or "",
                    row.get("archive_reason") or "",
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
              id, machine_serial, sale_id, request_id, product_id, product_name,
              method, payment_method, amount, units, currency, source, app_version,
              channel, relay, local_sale_counter, dispatch_status, sold_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    row["id"], row["machine_serial"], row.get("sale_id"), row.get("request_id"),
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

        cursor.executemany(
            """
            INSERT INTO alerts (id, machine_serial, type, title, detail, active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    row["id"], row["machine_serial"], row.get("type") or "warning",
                    row.get("title") or "Alerta", row.get("detail") or "",
                    1 if row.get("active", True) else 0, row.get("created_at") or "",
                )
                for row in backup["alerts"]
            ],
        )

        for table in ("sales", "alerts"):
            cursor.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
                f"EXISTS(SELECT 1 FROM {table}))"
            )
    return "imported"


def verify_destination(connection: psycopg.Connection, backup: dict[str, Any]) -> dict[str, Any]:
    with connection.cursor() as cursor:
        totals = {}
        for table in TABLES:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
            totals[table] = int(cursor.fetchone()["total"])
        cursor.execute("SELECT COALESCE(SUM(amount), 0) AS amount, COALESCE(SUM(units), 0) AS units FROM sales")
        sales = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS total FROM sales WHERE sale_id IS NOT NULL AND sale_id <> ''")
        sale_ids = int(cursor.fetchone()["total"])
        cursor.execute("SELECT COUNT(DISTINCT sale_id) AS total FROM sales WHERE sale_id IS NOT NULL AND sale_id <> ''")
        unique_sale_ids = int(cursor.fetchone()["total"])

    result = {
        "totals": totals,
        "sales_amount": round(float(sales["amount"]), 2),
        "sales_units": round(float(sales["units"]), 6),
        "sale_ids": sale_ids,
        "unique_sale_ids": unique_sale_ids,
    }
    if totals != backup["totals"]:
        raise ValueError(f"Conteos destino incorrectos: {result}")
    if result["sales_amount"] != backup["sales_amount"]:
        raise ValueError(f"Monto destino incorrecto: {result}")
    if result["sales_units"] != backup["sales_units"]:
        raise ValueError(f"Unidades destino incorrectas: {result}")
    if sale_ids != unique_sale_ids:
        raise ValueError("Hay sale_id duplicados en el destino")
    return result


def database_url(args: argparse.Namespace) -> str:
    if args.database_url_file:
        return Path(args.database_url_file).read_text(encoding="utf-8").strip()
    return os.getenv("DATABASE_URL", "").strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--database-url-file", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    backup = load_backup(args.backup.resolve())
    public_summary = {
        "mode": "dry-run" if args.dry_run else "apply",
        "checksums_verified": backup["checksums_verified"],
        "totals": backup["totals"],
        "sales_amount": backup["sales_amount"],
        "sales_units": backup["sales_units"],
    }
    if args.dry_run:
        print(json.dumps(public_summary, ensure_ascii=False, sort_keys=True))
        return

    url = database_url(args)
    if not url.startswith(("postgresql://", "postgres://")):
        raise ValueError("DATABASE_URL no configurada o no valida")

    with psycopg.connect(url, row_factory=dict_row) as connection:
        status = insert_backup(connection, backup)
        verified = verify_destination(connection, backup)
    public_summary.update({"status": status, "verified": verified})
    print(json.dumps(public_summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
