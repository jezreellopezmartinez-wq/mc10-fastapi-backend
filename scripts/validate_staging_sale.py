from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


def api(base_url: str, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=90) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"HTTP inesperado: {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} en {path}: {body}") from error


def close_enough(actual: float, expected: float) -> bool:
    return math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=0.000001)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--database-url-file", required=True, type=Path)
    parser.add_argument("--serial", required=True)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    if "mc10-fastapi-postgres-stage.onrender.com" not in base_url:
        raise ValueError("La prueba solo puede ejecutarse contra el servicio de staging")
    if not (args.serial.isdigit() and len(args.serial) == 16):
        raise ValueError("Serie de prueba no valida")

    database_url = args.database_url_file.read_text(encoding="utf-8").strip()
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise ValueError("Conexion PostgreSQL no valida")

    sale_id = f"STAGE6-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:10]}"
    result: dict[str, Any] = {"sale_id": sale_id, "serial": args.serial}
    cleanup_required = False

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM machines WHERE serial = %s", (args.serial,))
            machine_before = cursor.fetchone()
            if not machine_before:
                raise ValueError("La maquina de prueba no existe en staging")
            cursor.execute("SELECT COUNT(*) AS total FROM sales")
            global_sales_before = int(cursor.fetchone()["total"])
            cursor.execute("SELECT COUNT(*) AS total FROM sales WHERE machine_serial = %s", (args.serial,))
            machine_sales_before = int(cursor.fetchone()["total"])

    summary_before = api(base_url, f"/machines/{args.serial}/summary")
    products_before = api(base_url, f"/machines/{args.serial}/products")
    sales_before = api(base_url, f"/machines/{args.serial}/sales")
    if not products_before:
        raise ValueError("La maquina seleccionada no tiene productos")
    if len(sales_before) != machine_sales_before:
        raise ValueError("El historial inicial de la API no coincide con PostgreSQL")

    product_before = products_before[0]
    product_id = int(product_before["product_id"])
    amount = float(product_before.get("price") or 0)
    units = float(product_before.get("dispense_size") or product_before.get("dispenseSize") or 0)
    payload = {
        "sale_id": sale_id,
        "request_id": sale_id,
        "product_id": product_id,
        "product_name": product_before.get("name") or f"Producto {product_id}",
        "method": "MEI",
        "payment_method": "mei",
        "amount": amount,
        "units": units,
        "currency": "MXN",
        "sold_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "stage-6-validation",
        "app_version": "stage-6",
        "channel": int(product_before.get("relay") or product_id),
        "relay": int(product_before.get("relay") or product_id),
        "local_sale_counter": 0,
        "dispatch_status": "completed",
    }

    try:
        cleanup_required = True
        first = api(base_url, f"/machines/{args.serial}/sales", method="POST", payload=payload)
        second = api(base_url, f"/machines/{args.serial}/sales", method="POST", payload=payload)
        if first.get("id") != second.get("id") or first.get("sale_id") != second.get("sale_id"):
            raise ValueError("La repeticion de la venta no fue idempotente")

        summary_after = api(base_url, f"/machines/{args.serial}/summary")
        products_after = api(base_url, f"/machines/{args.serial}/products")
        sales_after = api(base_url, f"/machines/{args.serial}/sales")
        matches = [row for row in sales_after if row.get("sale_id") == sale_id]
        product_after = next(row for row in products_after if int(row["product_id"]) == product_id)

        if len(matches) != 1:
            raise ValueError(f"La venta temporal aparece {len(matches)} veces en el historial")
        if len(sales_after) != machine_sales_before + 1:
            raise ValueError("El conteo de ventas de la maquina no aumento exactamente en uno")
        expected_total = float(summary_before["summary"]["totalToday"]) + amount
        if not close_enough(summary_after["summary"]["totalToday"], expected_total):
            raise ValueError("El total de la maquina no aumento por el monto esperado")
        expected_quantity = int(product_before.get("quantity") or 0) + 1
        if int(product_after.get("quantity") or 0) != expected_quantity:
            raise ValueError("La cantidad vendida del producto no aumento exactamente en uno")

        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM sales WHERE sale_id = %s", (sale_id,))
                if int(cursor.fetchone()["total"]) != 1:
                    raise ValueError("PostgreSQL no contiene exactamente una venta temporal")
                cursor.execute("SELECT COUNT(*) AS total FROM sales")
                if int(cursor.fetchone()["total"]) != global_sales_before + 1:
                    raise ValueError("El total global no aumento exactamente en uno")

        result.update(
            {
                "status": "validated",
                "product_id": product_id,
                "amount": amount,
                "units": units,
                "database_rows_during_test": global_sales_before + 1,
                "history_matches": len(matches),
                "same_id_on_retry": first["id"] == second["id"],
                "summary_before": float(summary_before["summary"]["totalToday"]),
                "summary_during_test": float(summary_after["summary"]["totalToday"]),
            }
        )
    finally:
        if cleanup_required:
            with psycopg.connect(database_url, row_factory=dict_row) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM sales WHERE sale_id = %s", (sale_id,))
                    deleted = cursor.rowcount
                    cursor.execute(
                        """
                        UPDATE machines
                        SET status = %s, last_seen = %s, updated_at = %s
                        WHERE serial = %s
                        """,
                        (
                            machine_before["status"],
                            machine_before["last_seen"],
                            machine_before["updated_at"],
                            args.serial,
                        ),
                    )
                    cursor.execute(
                        "SELECT setval(pg_get_serial_sequence('sales', 'id'), "
                        "COALESCE((SELECT MAX(id) FROM sales), 1), EXISTS(SELECT 1 FROM sales))"
                    )
                if deleted > 1:
                    raise ValueError(f"La limpieza encontro {deleted} ventas temporales duplicadas")

    summary_restored = api(base_url, f"/machines/{args.serial}/summary")
    sales_restored = api(base_url, f"/machines/{args.serial}/sales")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM sales")
            global_sales_restored = int(cursor.fetchone()["total"])
            cursor.execute("SELECT COUNT(*) AS total FROM sales WHERE sale_id = %s", (sale_id,))
            test_rows_restored = int(cursor.fetchone()["total"])

    if global_sales_restored != global_sales_before:
        raise ValueError("La limpieza no restauro el total global inicial")
    if test_rows_restored != 0:
        raise ValueError("La venta temporal continua en PostgreSQL")
    if len(sales_restored) != machine_sales_before:
        raise ValueError("La limpieza no restauro el historial inicial")
    if not close_enough(summary_restored["summary"]["totalToday"], summary_before["summary"]["totalToday"]):
        raise ValueError("La limpieza no restauro el total inicial de la maquina")

    result.update(
        {
            "cleanup": "restored",
            "database_rows_after_cleanup": global_sales_restored,
            "test_rows_after_cleanup": test_rows_restored,
            "summary_after_cleanup": float(summary_restored["summary"]["totalToday"]),
        }
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
