from __future__ import annotations

import os
from uuid import uuid4
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from psycopg.rows import dict_row


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
OWNER_ACCESS_CODE = os.getenv("MC10_OWNER_CODE", "9876543210987654")
DEMO_MACHINE_CODE = os.getenv("MC10_DEMO_MACHINE_CODE", "1234567890123456")
ENABLE_DEMO_DATA = os.getenv("MC10_ENABLE_DEMO_DATA", "0").strip().lower() in {"1", "true", "yes", "on"}


DEFAULT_PRODUCTS = [
    {"product_id": 1, "name": "Pinol", "relay": 1, "price": 30, "dispense_size": 1.5, "category": "Limpieza"},
    {"product_id": 2, "name": "Cloro", "relay": 2, "price": 40, "dispense_size": 1.5, "category": "Limpieza"},
    {"product_id": 3, "name": "Suavizante", "relay": 3, "price": 45, "dispense_size": 1.5, "category": "Limpieza"},
    {"product_id": 4, "name": "Jabon para ropa", "relay": 4, "price": 50, "dispense_size": 1.5, "category": "Limpieza"},
    {"product_id": 5, "name": "Multiusos", "relay": 5, "price": 40, "dispense_size": 1.5, "category": "Limpieza"},
    {"product_id": 6, "name": "Desengrasante", "relay": 6, "price": 50, "dispense_size": 1.5, "category": "Limpieza"},
    {"product_id": 7, "name": "Aromatizante", "relay": 7, "price": 35, "dispense_size": 1.0, "category": "Limpieza"},
    {"product_id": 8, "name": "Shampoo para auto", "relay": 8, "price": 50, "dispense_size": 1.5, "category": "Limpieza"},
    {"product_id": 9, "name": "Limpiavidrios", "relay": 9, "price": 40, "dispense_size": 1.5, "category": "Limpieza"},
    {"product_id": 10, "name": "Gel antibacterial", "relay": 10, "price": 40, "dispense_size": 1.0, "category": "Limpieza"},
]


DEMO_MACHINES = [
    {
        "serial": DEMO_MACHINE_CODE,
        "name": "Demo limpieza 1",
        "model": "M10 Productos de Limpieza",
        "profile_id": "limpieza",
        "profile_title": "Productos de Limpieza",
        "location": "Monterrey, Nuevo Leon",
        "status": "En linea",
    },
    {
        "serial": "2222333344445555",
        "name": "Demo limpieza 2",
        "model": "M10 Productos de Limpieza",
        "profile_id": "limpieza",
        "profile_title": "Productos de Limpieza",
        "location": "San Nicolas, Nuevo Leon",
        "status": "En linea",
    },
    {
        "serial": "3333444455556666",
        "name": "Demo limpieza 3",
        "model": "MC10 Limpieza Express",
        "profile_id": "limpieza",
        "profile_title": "Productos de Limpieza",
        "location": "Guadalupe, Nuevo Leon",
        "status": "En linea",
    },
    {
        "serial": "4444555566667777",
        "name": "Demo limpieza 4",
        "model": "M10 Productos de Limpieza",
        "profile_id": "limpieza",
        "profile_title": "Productos de Limpieza",
        "location": "Apodaca, Nuevo Leon",
        "status": "Fuera de linea",
    },
]

DEMO_MACHINE_CODES = {machine["serial"] for machine in DEMO_MACHINES}


class LoginRequest(BaseModel):
    code: str = Field(..., min_length=1)


class ProductUpsert(BaseModel):
    product_id: int = Field(..., ge=1)
    name: Optional[str] = None
    relay: Optional[int] = None
    price: Optional[float] = None
    dispense_size: Optional[float] = None
    ms: Optional[int] = None
    calibration_ms: Optional[int] = None
    active: Optional[bool] = None
    category: Optional[str] = None


class MachineCreate(BaseModel):
    serial: str = Field(..., min_length=16, max_length=16)
    name: Optional[str] = None
    model: str = "MC10"
    profile_id: Optional[str] = None
    profile_title: Optional[str] = None
    location: str = "Sin ubicacion"
    status: str = "En linea"
    version: Optional[str] = None
    admin_machine_id: Optional[str] = None
    security_install_fingerprint: Optional[str] = None
    security_install_fingerprint_status: Optional[str] = None
    security_install_fingerprint_created_at: Optional[str] = None
    coin_profile: Optional[str] = None
    coin_profile_label: Optional[str] = None
    bill_profile: Optional[str] = None
    bill_profile_label: Optional[str] = None
    meiCoinProfile: Optional[str] = None
    meiCoinProfileLabel: Optional[str] = None
    meiBillProfile: Optional[str] = None
    meiBillProfileLabel: Optional[str] = None
    cloud_enabled: Optional[bool] = True
    products: Optional[List[ProductUpsert]] = None


class SaleCreate(BaseModel):
    sale_id: Optional[str] = None
    request_id: Optional[str] = None
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    method: str = "MEI"
    payment_method: Optional[str] = None
    amount: Optional[float] = None
    units: Optional[float] = None
    currency: Optional[str] = None
    sold_at: Optional[str] = None
    source: Optional[str] = None
    app_version: Optional[str] = None
    channel: Optional[int] = None
    relay: Optional[int] = None
    local_sale_counter: Optional[int] = None
    dispatch_status: Optional[str] = None


class AlertCreate(BaseModel):
    type: str = "warning"
    title: str
    detail: str = ""
    active: bool = True


class ProductPatch(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    dispense_size: Optional[float] = None
    relay: Optional[int] = None
    ms: Optional[int] = None
    calibration_ms: Optional[int] = None
    active: Optional[bool] = None
    category: Optional[str] = None


class PriceChangeCreate(BaseModel):
    product_id: int = Field(..., ge=1)
    new_price: float = Field(..., ge=0, le=999999)


class PriceUpdateBatchCreate(BaseModel):
    changes: List[PriceChangeCreate] = Field(..., min_length=1, max_length=50)


class PriceUpdateConfirm(BaseModel):
    applied: bool = True
    message: Optional[str] = None
    software_version: Optional[str] = None


class MachineStatusPatch(BaseModel):
    status: str = "En linea"
    version: Optional[str] = None
    admin_machine_id: Optional[str] = None
    security_install_fingerprint: Optional[str] = None
    security_install_fingerprint_status: Optional[str] = None
    security_install_fingerprint_created_at: Optional[str] = None
    coin_profile: Optional[str] = None
    coin_profile_label: Optional[str] = None
    bill_profile: Optional[str] = None
    bill_profile_label: Optional[str] = None
    meiCoinProfile: Optional[str] = None
    meiCoinProfileLabel: Optional[str] = None
    meiBillProfile: Optional[str] = None
    meiBillProfileLabel: Optional[str] = None


app = FastAPI(title="MC10 Cloud API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class DatabaseConnection:
    """Small compatibility layer that preserves the API's existing query calls."""

    def __init__(self) -> None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL no esta configurada")
        self.connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)

    @staticmethod
    def _postgres_query(query: str) -> str:
        return query.replace("?", "%s")

    def execute(self, query: str, params: Optional[tuple[Any, ...]] = None):
        return self.connection.execute(self._postgres_query(query), params)

    def executemany(self, query: str, params: List[tuple[Any, ...]]):
        cursor = self.connection.cursor()
        cursor.executemany(self._postgres_query(query), params)
        return cursor

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.connection.execute(statement)

    def __enter__(self) -> "DatabaseConnection":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()


def get_db() -> DatabaseConnection:
    return DatabaseConnection()


def row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return dict(row)


def is_16_digit_code(value: str) -> bool:
    return value.isdigit() and len(value) == 16


def verify_owner_access(x_mc10_owner_code: Optional[str] = Header(None)) -> None:
    if x_mc10_owner_code != OWNER_ACCESS_CODE:
        raise HTTPException(status_code=401, detail="Acceso de dueño no autorizado")


def safe_text(value: Optional[str], fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def first_text(*values: Optional[str], fallback: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return fallback


def bool_to_int(value: Optional[bool], fallback: bool = True) -> int:
    if value is None:
        return 1 if fallback else 0
    return 1 if bool(value) else 0


def is_demo_serial(serial: str) -> bool:
    return serial in DEMO_MACHINE_CODES


def get_table_columns(conn: DatabaseConnection, table: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = ?
        """,
        (table,),
    ).fetchall()
    return {row["column_name"] for row in rows}


def ensure_column(conn: DatabaseConnection, table: str, column: str, definition: str) -> None:
    if column in get_table_columns(conn, table):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def serialize_machine(row: Dict[str, Any]) -> Dict[str, Any]:
    data = row_to_dict(row)
    data["cloud_enabled"] = bool(data.get("cloud_enabled", 1))
    data["profileId"] = data.get("profile_id", "")
    data["profileTitle"] = data.get("profile_title", "")
    data["adminMachineId"] = data.get("admin_machine_id", "")
    data["securityFingerprint"] = data.get("security_install_fingerprint", "")
    data["securityFingerprintStatus"] = data.get("security_install_fingerprint_status", "")
    data["securityFingerprintCreatedAt"] = data.get("security_install_fingerprint_created_at", "")
    data["coinProfile"] = data.get("coin_profile", "")
    data["coinProfileLabel"] = data.get("coin_profile_label", "")
    data["billProfile"] = data.get("bill_profile", "")
    data["billProfileLabel"] = data.get("bill_profile_label", "")
    data["meiCoinProfile"] = data.get("coin_profile", "")
    data["meiCoinProfileLabel"] = data.get("coin_profile_label", "")
    data["meiBillProfile"] = data.get("bill_profile", "")
    data["meiBillProfileLabel"] = data.get("bill_profile_label", "")
    return data


def serialize_product(row: Dict[str, Any]) -> Dict[str, Any]:
    data = row_to_dict(row)
    data["active"] = bool(data.get("active", 1))
    data["dispenseSize"] = data.get("dispense_size", 0)
    data["calibrationMs"] = data.get("calibration_ms", 0)
    if "mei_sales" in data:
        data["meiSales"] = float(data.get("mei_sales") or 0)
    if "terminal_sales" in data:
        data["terminalSales"] = float(data.get("terminal_sales") or 0)
    if "last_sale_at" in data:
        data["lastSaleAt"] = data.get("last_sale_at") or ""
        data["lastSale"] = data["name"] if (data.get("quantity") or 0) > 0 else "Sin ventas"
    return data


def serialize_sale(row: Dict[str, Any]) -> Dict[str, Any]:
    data = row_to_dict(row)
    data["occurred_at"] = data.get("sold_at") or data.get("created_at")
    return data


def serialize_price_update(row: Dict[str, Any]) -> Dict[str, Any]:
    data = row_to_dict(row)
    data["old_price"] = float(data.get("old_price") or 0)
    data["new_price"] = float(data.get("new_price") or 0)
    return data


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS machines (
              serial TEXT PRIMARY KEY,
              name TEXT NOT NULL DEFAULT '',
              model TEXT NOT NULL,
              profile_id TEXT NOT NULL DEFAULT '',
              profile_title TEXT NOT NULL DEFAULT '',
              location TEXT NOT NULL,
              status TEXT NOT NULL,
              version TEXT NOT NULL DEFAULT '',
              cloud_enabled INTEGER NOT NULL DEFAULT 1,
              last_seen TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS products (
              machine_serial TEXT NOT NULL,
              product_id INTEGER NOT NULL,
              name TEXT NOT NULL,
              relay INTEGER NOT NULL,
              price REAL NOT NULL,
              dispense_size REAL NOT NULL,
              ms INTEGER NOT NULL DEFAULT 0,
              calibration_ms INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1,
              category TEXT NOT NULL DEFAULT '',
              updated_at TEXT NOT NULL DEFAULT '',
              PRIMARY KEY (machine_serial, product_id),
              FOREIGN KEY (machine_serial) REFERENCES machines(serial)
            );

            CREATE TABLE IF NOT EXISTS sales (
              id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
              machine_serial TEXT NOT NULL,
              sale_id TEXT,
              request_id TEXT,
              product_id INTEGER,
              product_name TEXT NOT NULL,
              method TEXT NOT NULL,
              payment_method TEXT NOT NULL DEFAULT '',
              amount REAL NOT NULL,
              units REAL NOT NULL,
              currency TEXT NOT NULL DEFAULT 'MXN',
              source TEXT NOT NULL DEFAULT '',
              app_version TEXT NOT NULL DEFAULT '',
              channel INTEGER NOT NULL DEFAULT 0,
              relay INTEGER NOT NULL DEFAULT 0,
              local_sale_counter INTEGER NOT NULL DEFAULT 0,
              dispatch_status TEXT NOT NULL DEFAULT '',
              sold_at TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              FOREIGN KEY (machine_serial) REFERENCES machines(serial)
            );

            CREATE TABLE IF NOT EXISTS alerts (
              id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
              machine_serial TEXT NOT NULL,
              type TEXT NOT NULL,
              title TEXT NOT NULL,
              detail TEXT NOT NULL,
              active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              FOREIGN KEY (machine_serial) REFERENCES machines(serial)
            );

            CREATE TABLE IF NOT EXISTS price_updates (
              id TEXT PRIMARY KEY,
              batch_id TEXT NOT NULL,
              machine_serial TEXT NOT NULL,
              product_id INTEGER NOT NULL,
              product_name TEXT NOT NULL,
              old_price REAL NOT NULL,
              new_price REAL NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              requested_at TEXT NOT NULL,
              confirmed_at TEXT NOT NULL DEFAULT '',
              result_message TEXT NOT NULL DEFAULT '',
              software_version TEXT NOT NULL DEFAULT '',
              FOREIGN KEY (machine_serial) REFERENCES machines(serial)
            );
            """
        )

        ensure_column(conn, "machines", "name", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "profile_id", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "profile_title", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "version", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "admin_machine_id", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "security_install_fingerprint", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "security_install_fingerprint_status", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "security_install_fingerprint_created_at", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "coin_profile", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "coin_profile_label", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "bill_profile", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "bill_profile_label", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "machines", "cloud_enabled", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "machines", "updated_at", "TEXT NOT NULL DEFAULT ''")

        ensure_column(conn, "products", "ms", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "products", "calibration_ms", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "products", "active", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "products", "category", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "products", "updated_at", "TEXT NOT NULL DEFAULT ''")

        ensure_column(conn, "sales", "sale_id", "TEXT")
        ensure_column(conn, "sales", "request_id", "TEXT")
        ensure_column(conn, "sales", "payment_method", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "sales", "currency", "TEXT NOT NULL DEFAULT 'MXN'")
        ensure_column(conn, "sales", "source", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "sales", "app_version", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "sales", "channel", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "sales", "relay", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "sales", "local_sale_counter", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "sales", "dispatch_status", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "sales", "sold_at", "TEXT NOT NULL DEFAULT ''")

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_sale_id
            ON sales(sale_id)
            WHERE sale_id IS NOT NULL AND sale_id <> ''
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_price_updates_pending
            ON price_updates(machine_serial, status, requested_at)
            """
        )

        if ENABLE_DEMO_DATA:
            seed_demo_data(conn)


def seed_demo_data(conn: DatabaseConnection) -> None:
    timestamp = now_iso()

    for machine in DEMO_MACHINES:
        register_machine(
            conn,
            MachineCreate(
                serial=machine["serial"],
                name=machine["name"],
                model=machine["model"],
                profile_id=machine["profile_id"],
                profile_title=machine["profile_title"],
                location=machine["location"],
                status=machine["status"],
                version="demo",
                cloud_enabled=True,
                products=[ProductUpsert(**product) for product in DEFAULT_PRODUCTS],
            ),
        )

    sales_count = conn.execute("SELECT COUNT(*) AS total FROM sales").fetchone()["total"]
    if sales_count == 0:
        demo_sales = [
            (DEMO_MACHINE_CODE, "DEMO-SALE-1", 1, "Pinol", "MEI", "mei", 30, 1.5),
            (DEMO_MACHINE_CODE, "DEMO-SALE-2", 2, "Cloro", "Terminal", "terminal", 40, 1.5),
            ("2222333344445555", "DEMO-SALE-3", 5, "Multiusos", "Terminal", "terminal", 40, 1.5),
            ("2222333344445555", "DEMO-SALE-4", 7, "Aromatizante", "MEI", "mei", 35, 1.0),
            ("3333444455556666", "DEMO-SALE-5", 4, "Jabon para ropa", "Terminal", "terminal", 50, 1.5),
            ("4444555566667777", "DEMO-SALE-6", 9, "Limpiavidrios", "MEI", "mei", 40, 1.5),
        ]
        conn.executemany(
            """
            INSERT INTO sales (
              machine_serial, sale_id, product_id, product_name, method, payment_method,
              amount, units, currency, source, app_version, sold_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'MXN', 'demo-seed', 'demo', ?, ?)
            ON CONFLICT DO NOTHING
            """,
            [sale + (timestamp, timestamp) for sale in demo_sales],
        )

    alerts_count = conn.execute("SELECT COUNT(*) AS total FROM alerts").fetchone()["total"]
    if alerts_count == 0:
        conn.execute(
            """
            INSERT INTO alerts (machine_serial, type, title, detail, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                DEMO_MACHINE_CODE,
                "warning",
                "Nivel bajo de producto: Cloro",
                "Revisar contenedor antes del siguiente corte.",
                1,
                timestamp,
            ),
        )


def get_machine_or_404(conn: DatabaseConnection, serial: str) -> Dict[str, Any]:
    if not ENABLE_DEMO_DATA and is_demo_serial(serial):
        raise HTTPException(status_code=404, detail="Maquina no encontrada")
    machine = conn.execute("SELECT * FROM machines WHERE serial = ?", (serial,)).fetchone()
    if not machine:
        raise HTTPException(status_code=404, detail="Maquina no encontrada")
    return machine


def upsert_machine_product(
    conn: DatabaseConnection,
    serial: str,
    product_id: int,
    payload: ProductPatch | ProductUpsert | Dict[str, Any],
) -> Dict[str, Any]:
    existing = conn.execute(
        "SELECT * FROM products WHERE machine_serial = ? AND product_id = ?",
        (serial, product_id),
    ).fetchone()
    values = payload.model_dump(exclude_none=True) if isinstance(payload, BaseModel) else dict(payload)
    timestamp = now_iso()

    next_name = safe_text(values.get("name"), existing["name"] if existing else f"Producto {product_id}")
    next_relay = int(values.get("relay", existing["relay"] if existing else product_id) or product_id)
    next_price = float(values.get("price", existing["price"] if existing else 0) or 0)
    next_dispense_size = float(values.get("dispense_size", existing["dispense_size"] if existing else 1) or 1)
    next_ms = int(values.get("ms", existing["ms"] if existing else 0) or 0)
    next_calibration_ms = int(values.get("calibration_ms", existing["calibration_ms"] if existing else next_ms) or next_ms)
    next_active = bool_to_int(values.get("active"), bool(existing["active"]) if existing else True)
    next_category = safe_text(values.get("category"), existing["category"] if existing else "")

    conn.execute(
        """
        INSERT INTO products (
          machine_serial, product_id, name, relay, price, dispense_size,
          ms, calibration_ms, active, category, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(machine_serial, product_id) DO UPDATE SET
          name = excluded.name,
          relay = excluded.relay,
          price = excluded.price,
          dispense_size = excluded.dispense_size,
          ms = excluded.ms,
          calibration_ms = excluded.calibration_ms,
          active = excluded.active,
          category = excluded.category,
          updated_at = excluded.updated_at
        """,
        (
            serial,
            product_id,
            next_name,
            next_relay,
            next_price,
            next_dispense_size,
            next_ms,
            next_calibration_ms,
            next_active,
            next_category,
            timestamp,
        ),
    )

    row = conn.execute(
        "SELECT * FROM products WHERE machine_serial = ? AND product_id = ?",
        (serial, product_id),
    ).fetchone()
    return serialize_product(row)


def upsert_machine_products(conn: DatabaseConnection, serial: str, products: List[ProductUpsert]) -> List[Dict[str, Any]]:
    return [upsert_machine_product(conn, serial, product.product_id, product) for product in products]


def register_machine(conn: DatabaseConnection, payload: MachineCreate) -> Dict[str, Any]:
    if not is_16_digit_code(payload.serial):
        raise HTTPException(status_code=400, detail="La serie debe tener 16 digitos")

    existing = conn.execute("SELECT * FROM machines WHERE serial = ?", (payload.serial,)).fetchone()
    timestamp = now_iso()

    next_model = safe_text(payload.model, existing["model"] if existing else "MC10")
    next_name = safe_text(payload.name, existing["name"] if existing else next_model)
    next_profile_id = safe_text(payload.profile_id, existing["profile_id"] if existing else "")
    next_profile_title = safe_text(payload.profile_title, existing["profile_title"] if existing else next_model)
    next_location = safe_text(payload.location, existing["location"] if existing else "Ubicacion pendiente")
    next_status = safe_text(payload.status, existing["status"] if existing else "En linea")
    next_version = safe_text(payload.version, existing["version"] if existing else "")
    next_admin_machine_id = safe_text(payload.admin_machine_id, existing["admin_machine_id"] if existing else "")
    next_security_install_fingerprint = safe_text(
        payload.security_install_fingerprint,
        existing["security_install_fingerprint"] if existing else "",
    )
    next_security_install_fingerprint_status = safe_text(
        payload.security_install_fingerprint_status,
        existing["security_install_fingerprint_status"] if existing else "",
    )
    next_security_install_fingerprint_created_at = safe_text(
        payload.security_install_fingerprint_created_at,
        existing["security_install_fingerprint_created_at"] if existing else "",
    )
    next_coin_profile = first_text(payload.coin_profile, payload.meiCoinProfile, fallback=existing["coin_profile"] if existing else "")
    next_coin_profile_label = first_text(
        payload.coin_profile_label,
        payload.meiCoinProfileLabel,
        fallback=existing["coin_profile_label"] if existing else "",
    )
    next_bill_profile = first_text(payload.bill_profile, payload.meiBillProfile, fallback=existing["bill_profile"] if existing else "")
    next_bill_profile_label = first_text(
        payload.bill_profile_label,
        payload.meiBillProfileLabel,
        fallback=existing["bill_profile_label"] if existing else "",
    )
    next_cloud_enabled = bool_to_int(payload.cloud_enabled, bool(existing["cloud_enabled"]) if existing else True)
    created_at = existing["created_at"] if existing else timestamp

    conn.execute(
        """
        INSERT INTO machines (
          serial, name, model, profile_id, profile_title, location,
          status, version, admin_machine_id, security_install_fingerprint,
          security_install_fingerprint_status, security_install_fingerprint_created_at,
          coin_profile, coin_profile_label, bill_profile, bill_profile_label,
          cloud_enabled, last_seen, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(serial) DO UPDATE SET
          name = excluded.name,
          model = excluded.model,
          profile_id = excluded.profile_id,
          profile_title = excluded.profile_title,
          location = excluded.location,
          status = excluded.status,
          version = excluded.version,
          admin_machine_id = excluded.admin_machine_id,
          security_install_fingerprint = excluded.security_install_fingerprint,
          security_install_fingerprint_status = excluded.security_install_fingerprint_status,
          security_install_fingerprint_created_at = excluded.security_install_fingerprint_created_at,
          coin_profile = excluded.coin_profile,
          coin_profile_label = excluded.coin_profile_label,
          bill_profile = excluded.bill_profile,
          bill_profile_label = excluded.bill_profile_label,
          cloud_enabled = excluded.cloud_enabled,
          last_seen = excluded.last_seen,
          updated_at = excluded.updated_at
        """,
        (
            payload.serial,
            next_name,
            next_model,
            next_profile_id,
            next_profile_title,
            next_location,
            next_status,
            next_version,
            next_admin_machine_id,
            next_security_install_fingerprint,
            next_security_install_fingerprint_status,
            next_security_install_fingerprint_created_at,
            next_coin_profile,
            next_coin_profile_label,
            next_bill_profile,
            next_bill_profile_label,
            next_cloud_enabled,
            timestamp,
            created_at,
            timestamp,
        ),
    )

    if payload.products:
        upsert_machine_products(conn, payload.serial, payload.products)

    machine = conn.execute("SELECT * FROM machines WHERE serial = ?", (payload.serial,)).fetchone()
    return serialize_machine(machine)


def touch_machine(
    conn: DatabaseConnection,
    serial: str,
    *,
    status: Optional[str] = None,
    version: Optional[str] = None,
    admin_machine_id: Optional[str] = None,
    security_install_fingerprint: Optional[str] = None,
    security_install_fingerprint_status: Optional[str] = None,
    security_install_fingerprint_created_at: Optional[str] = None,
    coin_profile: Optional[str] = None,
    coin_profile_label: Optional[str] = None,
    bill_profile: Optional[str] = None,
    bill_profile_label: Optional[str] = None,
) -> Dict[str, Any]:
    if not is_16_digit_code(serial):
        raise HTTPException(status_code=400, detail="La serie debe tener 16 digitos")

    machine = get_machine_or_404(conn, serial)
    timestamp = now_iso()
    next_status = safe_text(status, machine["status"])
    next_version = safe_text(version, machine["version"])
    next_admin_machine_id = safe_text(admin_machine_id, machine["admin_machine_id"])
    next_security_install_fingerprint = safe_text(security_install_fingerprint, machine["security_install_fingerprint"])
    next_security_install_fingerprint_status = safe_text(
        security_install_fingerprint_status,
        machine["security_install_fingerprint_status"],
    )
    next_security_install_fingerprint_created_at = safe_text(
        security_install_fingerprint_created_at,
        machine["security_install_fingerprint_created_at"],
    )
    next_coin_profile = safe_text(coin_profile, machine["coin_profile"])
    next_coin_profile_label = safe_text(coin_profile_label, machine["coin_profile_label"])
    next_bill_profile = safe_text(bill_profile, machine["bill_profile"])
    next_bill_profile_label = safe_text(bill_profile_label, machine["bill_profile_label"])
    conn.execute(
        """
        UPDATE machines SET
          status = ?,
          version = ?,
          admin_machine_id = ?,
          security_install_fingerprint = ?,
          security_install_fingerprint_status = ?,
          security_install_fingerprint_created_at = ?,
          coin_profile = ?,
          coin_profile_label = ?,
          bill_profile = ?,
          bill_profile_label = ?,
          last_seen = ?,
          updated_at = ?
        WHERE serial = ?
        """,
        (
            next_status,
            next_version,
            next_admin_machine_id,
            next_security_install_fingerprint,
            next_security_install_fingerprint_status,
            next_security_install_fingerprint_created_at,
            next_coin_profile,
            next_coin_profile_label,
            next_bill_profile,
            next_bill_profile_label,
            timestamp,
            timestamp,
            serial,
        ),
    )
    updated = conn.execute("SELECT * FROM machines WHERE serial = ?", (serial,)).fetchone()
    return serialize_machine(updated)


def machine_summary(conn: DatabaseConnection, serial: str) -> Dict[str, Any]:
    machine = get_machine_or_404(conn, serial)
    totals = conn.execute(
        """
        SELECT
          COALESCE(SUM(amount), 0) AS total_today,
          COALESCE(SUM(CASE WHEN method = 'MEI' THEN amount ELSE 0 END), 0) AS mei_total,
          COALESCE(SUM(CASE WHEN method = 'Terminal' THEN amount ELSE 0 END), 0) AS terminal_total,
          COUNT(*) AS products_sold,
          COALESCE(SUM(units), 0) AS liters
        FROM sales
        WHERE machine_serial = ?
        """,
        (serial,),
    ).fetchone()
    active_alerts = conn.execute(
        "SELECT COUNT(*) AS total FROM alerts WHERE machine_serial = ? AND active = 1",
        (serial,),
    ).fetchone()["total"]

    return {
        "machine": serialize_machine(machine),
        "summary": {
            "totalToday": float(totals["total_today"] or 0),
            "meiTotal": float(totals["mei_total"] or 0),
            "terminalTotal": float(totals["terminal_total"] or 0),
            "productsSold": int(totals["products_sold"] or 0),
            "liters": float(totals["liters"] or 0),
            "alerts": int(active_alerts or 0),
        },
    }


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "time": now_iso()}


@app.post("/auth/login")
def login(payload: LoginRequest) -> Dict[str, Any]:
    code = "".join(character for character in payload.code if character.isdigit())

    if code == OWNER_ACCESS_CODE:
        return {"role": "owner", "code": code}

    if not is_16_digit_code(code):
        raise HTTPException(status_code=401, detail="Codigo no valido")

    with get_db() as conn:
        machine = touch_machine(conn, code)
    return {"role": "client", "code": code, "machine": machine}


@app.get("/machines")
def list_machines(_: None = Depends(verify_owner_access)) -> List[Dict[str, Any]]:
    with get_db() as conn:
        if ENABLE_DEMO_DATA:
            rows = conn.execute("SELECT * FROM machines ORDER BY created_at DESC").fetchall()
        else:
            placeholders = ",".join("?" for _ in DEMO_MACHINE_CODES)
            rows = conn.execute(
                f"SELECT * FROM machines WHERE serial NOT IN ({placeholders}) ORDER BY created_at DESC",
                tuple(DEMO_MACHINE_CODES),
            ).fetchall() if DEMO_MACHINE_CODES else conn.execute("SELECT * FROM machines ORDER BY created_at DESC").fetchall()
    return [serialize_machine(row) for row in rows]


@app.post("/machines")
def create_machine(payload: MachineCreate) -> Dict[str, Any]:
    with get_db() as conn:
        machine = register_machine(conn, payload)
    return machine


@app.post("/machines/{serial}/heartbeat")
def heartbeat(serial: str, payload: Optional[MachineStatusPatch] = None) -> Dict[str, Any]:
    payload = payload or MachineStatusPatch()
    with get_db() as conn:
        machine = touch_machine(
            conn,
            serial,
            status=payload.status or "En linea",
            version=payload.version,
            admin_machine_id=payload.admin_machine_id,
            security_install_fingerprint=payload.security_install_fingerprint,
            security_install_fingerprint_status=payload.security_install_fingerprint_status,
            security_install_fingerprint_created_at=payload.security_install_fingerprint_created_at,
            coin_profile=first_text(payload.coin_profile, payload.meiCoinProfile),
            coin_profile_label=first_text(payload.coin_profile_label, payload.meiCoinProfileLabel),
            bill_profile=first_text(payload.bill_profile, payload.meiBillProfile),
            bill_profile_label=first_text(payload.bill_profile_label, payload.meiBillProfileLabel),
        )
    return {"machine": machine, "online": True}


@app.patch("/machines/{serial}/status")
def update_machine_status(serial: str, payload: MachineStatusPatch) -> Dict[str, Any]:
    with get_db() as conn:
        machine = touch_machine(
            conn,
            serial,
            status=payload.status,
            version=payload.version,
            admin_machine_id=payload.admin_machine_id,
            security_install_fingerprint=payload.security_install_fingerprint,
            security_install_fingerprint_status=payload.security_install_fingerprint_status,
            security_install_fingerprint_created_at=payload.security_install_fingerprint_created_at,
            coin_profile=first_text(payload.coin_profile, payload.meiCoinProfile),
            coin_profile_label=first_text(payload.coin_profile_label, payload.meiCoinProfileLabel),
            bill_profile=first_text(payload.bill_profile, payload.meiBillProfile),
            bill_profile_label=first_text(payload.bill_profile_label, payload.meiBillProfileLabel),
        )
    return machine


@app.get("/machines/{serial}/summary")
def get_machine_summary(serial: str) -> Dict[str, Any]:
    with get_db() as conn:
        return machine_summary(conn, serial)


@app.get("/owner/summary")
def get_owner_summary(_: None = Depends(verify_owner_access)) -> Dict[str, Any]:
    with get_db() as conn:
        if ENABLE_DEMO_DATA:
            rows = conn.execute("SELECT * FROM machines ORDER BY created_at DESC").fetchall()
        else:
            placeholders = ",".join("?" for _ in DEMO_MACHINE_CODES)
            rows = conn.execute(
                f"SELECT * FROM machines WHERE serial NOT IN ({placeholders}) ORDER BY created_at DESC",
                tuple(DEMO_MACHINE_CODES),
            ).fetchall() if DEMO_MACHINE_CODES else conn.execute("SELECT * FROM machines ORDER BY created_at DESC").fetchall()
        machines = [serialize_machine(row) for row in rows]
        summaries = [machine_summary(conn, machine["serial"]) for machine in machines]

    totals = {
        "totalToday": sum(item["summary"]["totalToday"] for item in summaries),
        "meiTotal": sum(item["summary"]["meiTotal"] for item in summaries),
        "terminalTotal": sum(item["summary"]["terminalTotal"] for item in summaries),
        "productsSold": sum(item["summary"]["productsSold"] for item in summaries),
        "liters": sum(item["summary"]["liters"] for item in summaries),
        "alerts": sum(item["summary"]["alerts"] for item in summaries),
        "online": sum(1 for item in summaries if item["machine"]["status"] == "En linea"),
        "totalMachines": len(summaries),
    }
    return {"summary": totals, "machines": summaries}


@app.get("/machines/{serial}/products")
def list_products(serial: str) -> List[Dict[str, Any]]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        rows = conn.execute(
            """
            SELECT
              p.*,
              COUNT(s.id) AS quantity,
              COALESCE(SUM(s.units), 0) AS units,
              COALESCE(SUM(CASE WHEN s.method = 'MEI' THEN s.amount ELSE 0 END), 0) AS mei_sales,
              COALESCE(SUM(CASE WHEN s.method = 'Terminal' THEN s.amount ELSE 0 END), 0) AS terminal_sales,
              MAX(CASE WHEN COALESCE(s.sold_at, '') <> '' THEN s.sold_at ELSE s.created_at END) AS last_sale_at
            FROM products p
            LEFT JOIN sales s
              ON s.machine_serial = p.machine_serial
             AND s.product_id = p.product_id
            WHERE p.machine_serial = ?
            GROUP BY
              p.machine_serial, p.product_id, p.name, p.relay, p.price,
              p.dispense_size, p.ms, p.calibration_ms, p.active, p.category, p.updated_at
            ORDER BY p.product_id
            """,
            (serial,),
        ).fetchall()
    return [serialize_product(row) for row in rows]


@app.patch("/machines/{serial}/products/{product_id}/price")
def update_product(serial: str, product_id: int, payload: ProductPatch) -> Dict[str, Any]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        updated = upsert_machine_product(conn, serial, product_id, payload)
    return updated


@app.post("/machines/{serial}/price-updates")
def create_price_updates(
    serial: str,
    payload: PriceUpdateBatchCreate,
    _: None = Depends(verify_owner_access),
) -> Dict[str, Any]:
    batch_id = str(uuid4())
    timestamp = now_iso()
    created: List[Dict[str, Any]] = []

    with get_db() as conn:
        get_machine_or_404(conn, serial)
        product_ids = [change.product_id for change in payload.changes]
        if len(product_ids) != len(set(product_ids)):
            raise HTTPException(status_code=400, detail="No repitas un producto en el mismo cambio")

        for change in payload.changes:
            product = conn.execute(
                "SELECT * FROM products WHERE machine_serial = ? AND product_id = ?",
                (serial, change.product_id),
            ).fetchone()
            if not product:
                raise HTTPException(status_code=404, detail=f"Producto {change.product_id} no encontrado")

            # El cambio más reciente reemplaza cualquier solicitud anterior que
            # todavía no haya sido aplicada para el mismo producto.
            conn.execute(
                """
                UPDATE price_updates
                SET status = 'cancelled', confirmed_at = ?, result_message = ?
                WHERE machine_serial = ? AND product_id = ? AND status = 'pending'
                """,
                (timestamp, "Reemplazado por un cambio más reciente", serial, change.product_id),
            )

            update_id = str(uuid4())
            row = conn.execute(
                """
                INSERT INTO price_updates (
                  id, batch_id, machine_serial, product_id, product_name,
                  old_price, new_price, status, requested_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                RETURNING *
                """,
                (
                    update_id,
                    batch_id,
                    serial,
                    change.product_id,
                    product["name"],
                    float(product["price"] or 0),
                    round(float(change.new_price), 2),
                    timestamp,
                ),
            ).fetchone()
            created.append(serialize_price_update(row))

    return {"batch_id": batch_id, "status": "pending", "updates": created}


@app.get("/machines/{serial}/price-updates")
def list_price_updates(
    serial: str,
    _: None = Depends(verify_owner_access),
) -> List[Dict[str, Any]]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        rows = conn.execute(
            """
            SELECT * FROM price_updates
            WHERE machine_serial = ?
            ORDER BY requested_at DESC
            LIMIT 100
            """,
            (serial,),
        ).fetchall()
    return [serialize_price_update(row) for row in rows]


@app.get("/machines/{serial}/price-updates/pending")
def list_pending_price_updates(serial: str) -> List[Dict[str, Any]]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        rows = conn.execute(
            """
            SELECT * FROM price_updates
            WHERE machine_serial = ? AND status = 'pending'
            ORDER BY requested_at ASC
            """,
            (serial,),
        ).fetchall()
    return [serialize_price_update(row) for row in rows]


@app.post("/machines/{serial}/price-updates/{update_id}/confirm")
def confirm_price_update(
    serial: str,
    update_id: str,
    payload: PriceUpdateConfirm,
) -> Dict[str, Any]:
    timestamp = now_iso()
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        update = conn.execute(
            "SELECT * FROM price_updates WHERE id = ? AND machine_serial = ?",
            (update_id, serial),
        ).fetchone()
        if not update:
            raise HTTPException(status_code=404, detail="Cambio de precio no encontrado")

        # Las confirmaciones repetidas son seguras: devolvemos el estado ya
        # almacenado sin volver a modificar el producto.
        if update["status"] != "pending":
            return serialize_price_update(update)

        next_status = "applied" if payload.applied else "error"
        if payload.applied:
            conn.execute(
                """
                UPDATE products SET price = ?, updated_at = ?
                WHERE machine_serial = ? AND product_id = ?
                """,
                (float(update["new_price"]), timestamp, serial, int(update["product_id"])),
            )

        row = conn.execute(
            """
            UPDATE price_updates
            SET status = ?, confirmed_at = ?, result_message = ?, software_version = ?
            WHERE id = ? AND machine_serial = ?
            RETURNING *
            """,
            (
                next_status,
                timestamp,
                safe_text(payload.message, "Aplicado correctamente" if payload.applied else "No se pudo aplicar"),
                safe_text(payload.software_version, ""),
                update_id,
                serial,
            ),
        ).fetchone()
    return serialize_price_update(row)


@app.get("/machines/{serial}/sales")
def list_sales(serial: str) -> List[Dict[str, Any]]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        rows = conn.execute(
            """
            SELECT *
            FROM sales
            WHERE machine_serial = ?
            ORDER BY
              CASE WHEN COALESCE(sold_at, '') <> '' THEN sold_at ELSE created_at END DESC,
              id DESC
            LIMIT 100
            """,
            (serial,),
        ).fetchall()
    return [serialize_sale(row) for row in rows]


@app.post("/machines/{serial}/sales")
def create_sale(serial: str, payload: SaleCreate) -> Dict[str, Any]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)

        if payload.sale_id:
            existing_sale = conn.execute(
                "SELECT * FROM sales WHERE sale_id = ? LIMIT 1",
                (payload.sale_id,),
            ).fetchone()
            if existing_sale:
                return serialize_sale(existing_sale)

        product = None
        if payload.product_id is not None:
            product = conn.execute(
                "SELECT * FROM products WHERE machine_serial = ? AND product_id = ?",
                (serial, payload.product_id),
            ).fetchone()

        if payload.product_id is not None and product is None:
            upsert_machine_product(
                conn,
                serial,
                payload.product_id,
                {
                    "name": payload.product_name,
                    "relay": payload.relay if payload.relay is not None else payload.channel,
                    "price": payload.amount,
                    "dispense_size": payload.units,
                },
            )
            product = conn.execute(
                "SELECT * FROM products WHERE machine_serial = ? AND product_id = ?",
                (serial, payload.product_id),
            ).fetchone()

        product_id = payload.product_id
        product_name = payload.product_name or (product["name"] if product else "Venta manual")
        amount = payload.amount if payload.amount is not None else (product["price"] if product else 0)
        units = payload.units if payload.units is not None else (product["dispense_size"] if product else 1)
        timestamp = now_iso()
        sold_at = safe_text(payload.sold_at, timestamp)
        payment_method = safe_text(payload.payment_method, payload.method.lower())
        relay = int(payload.relay if payload.relay is not None else (product["relay"] if product else payload.channel or 0) or 0)
        channel = int(payload.channel if payload.channel is not None else relay)
        local_sale_counter = int(payload.local_sale_counter or 0)
        dispatch_status = safe_text(payload.dispatch_status, "completed")

        sale = conn.execute(
            """
            INSERT INTO sales (
              machine_serial, sale_id, request_id, product_id, product_name, method,
              payment_method, amount, units, currency, source, app_version,
              channel, relay, local_sale_counter, dispatch_status, sold_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING *
            """,
            (
                serial,
                payload.sale_id,
                payload.request_id,
                product_id,
                product_name,
                payload.method,
                payment_method,
                amount,
                units,
                safe_text(payload.currency, "MXN"),
                safe_text(payload.source, "panel-local"),
                safe_text(payload.app_version, ""),
                channel,
                relay,
                local_sale_counter,
                dispatch_status,
                sold_at,
                timestamp,
            ),
        ).fetchone()
        conn.execute(
            "UPDATE machines SET status = ?, last_seen = ?, updated_at = ? WHERE serial = ?",
            ("En linea", timestamp, timestamp, serial),
        )
    return serialize_sale(sale)


@app.get("/machines/{serial}/alerts")
def list_alerts(serial: str) -> List[Dict[str, Any]]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        rows = conn.execute(
            "SELECT * FROM alerts WHERE machine_serial = ? ORDER BY created_at DESC, id DESC LIMIT 100",
            (serial,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


@app.post("/machines/{serial}/alerts/clear")
def clear_alerts(serial: str, _: None = Depends(verify_owner_access)) -> Dict[str, Any]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        conn.execute("UPDATE alerts SET active = 0 WHERE machine_serial = ?", (serial,))
    return {"cleared": True, "serial": serial}


@app.post("/machines/{serial}/alerts")
def create_alert(serial: str, payload: AlertCreate) -> Dict[str, Any]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        timestamp = now_iso()
        alert = conn.execute(
            """
            INSERT INTO alerts (machine_serial, type, title, detail, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING *
            """,
            (serial, payload.type, payload.title, payload.detail, int(payload.active), timestamp),
        ).fetchone()
    return row_to_dict(alert)
