import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DB_PATH = Path(os.getenv("MC10_DB_PATH", "mc10_cloud.sqlite3"))
OWNER_ACCESS_CODE = os.getenv("MC10_OWNER_CODE", "9876543210987654")
DEMO_MACHINE_CODE = os.getenv("MC10_DEMO_MACHINE_CODE", "1234567890123456")


DEFAULT_PRODUCTS = [
    {"product_id": 1, "name": "Pinol", "relay": 1, "price": 30, "dispense_size": 1.5},
    {"product_id": 2, "name": "Cloro", "relay": 2, "price": 40, "dispense_size": 1.5},
    {"product_id": 3, "name": "Suavizante", "relay": 3, "price": 45, "dispense_size": 1.5},
    {"product_id": 4, "name": "Jabon para ropa", "relay": 4, "price": 50, "dispense_size": 1.5},
    {"product_id": 5, "name": "Multiusos", "relay": 5, "price": 40, "dispense_size": 1.5},
    {"product_id": 6, "name": "Desengrasante", "relay": 6, "price": 50, "dispense_size": 1.5},
    {"product_id": 7, "name": "Aromatizante", "relay": 7, "price": 35, "dispense_size": 1.0},
    {"product_id": 8, "name": "Shampoo para auto", "relay": 8, "price": 50, "dispense_size": 1.5},
    {"product_id": 9, "name": "Limpiavidrios", "relay": 9, "price": 40, "dispense_size": 1.5},
    {"product_id": 10, "name": "Gel antibacterial", "relay": 10, "price": 40, "dispense_size": 1.0},
]


DEMO_MACHINES = [
    {
        "serial": DEMO_MACHINE_CODE,
        "model": "M10 Productos de Limpieza",
        "location": "Monterrey, Nuevo Leon",
        "status": "En linea",
    },
    {
        "serial": "2222333344445555",
        "model": "M10 Productos de Limpieza",
        "location": "San Nicolas, Nuevo Leon",
        "status": "En linea",
    },
    {
        "serial": "3333444455556666",
        "model": "MC10 Limpieza Express",
        "location": "Guadalupe, Nuevo Leon",
        "status": "En linea",
    },
    {
        "serial": "4444555566667777",
        "model": "M10 Productos de Limpieza",
        "location": "Apodaca, Nuevo Leon",
        "status": "Fuera de linea",
    },
]


class LoginRequest(BaseModel):
    code: str = Field(..., min_length=1)


class MachineCreate(BaseModel):
    serial: str = Field(..., min_length=16, max_length=16)
    model: str = "M10 Productos de Limpieza"
    location: str = "Sin ubicacion"
    status: str = "En linea"


class SaleCreate(BaseModel):
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    method: str = "MEI"
    amount: Optional[float] = None
    units: Optional[float] = None


class AlertCreate(BaseModel):
    type: str = "warning"
    title: str
    detail: str = ""
    active: bool = True


class ProductPatch(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    dispense_size: Optional[float] = None


class MachineStatusPatch(BaseModel):
    status: str = "En linea"


app = FastAPI(title="MC10 Cloud API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [row_to_dict(row) for row in rows]


def is_16_digit_code(value: str) -> bool:
    return value.isdigit() and len(value) == 16


def verify_owner_access(x_mc10_owner_code: Optional[str] = Header(None)) -> None:
    if x_mc10_owner_code != OWNER_ACCESS_CODE:
        raise HTTPException(status_code=401, detail="Acceso de dueño no autorizado")


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS machines (
              serial TEXT PRIMARY KEY,
              model TEXT NOT NULL,
              location TEXT NOT NULL,
              status TEXT NOT NULL,
              last_seen TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
              machine_serial TEXT NOT NULL,
              product_id INTEGER NOT NULL,
              name TEXT NOT NULL,
              relay INTEGER NOT NULL,
              price REAL NOT NULL,
              dispense_size REAL NOT NULL,
              PRIMARY KEY (machine_serial, product_id),
              FOREIGN KEY (machine_serial) REFERENCES machines(serial)
            );

            CREATE TABLE IF NOT EXISTS sales (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              machine_serial TEXT NOT NULL,
              product_id INTEGER,
              product_name TEXT NOT NULL,
              method TEXT NOT NULL,
              amount REAL NOT NULL,
              units REAL NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (machine_serial) REFERENCES machines(serial)
            );

            CREATE TABLE IF NOT EXISTS alerts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              machine_serial TEXT NOT NULL,
              type TEXT NOT NULL,
              title TEXT NOT NULL,
              detail TEXT NOT NULL,
              active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              FOREIGN KEY (machine_serial) REFERENCES machines(serial)
            );
            """
        )
        seed_demo_data(conn)


def seed_demo_data(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()

    for machine in DEMO_MACHINES:
        conn.execute(
            """
            INSERT OR IGNORE INTO machines (serial, model, location, status, last_seen, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                machine["serial"],
                machine["model"],
                machine["location"],
                machine["status"],
                timestamp,
                timestamp,
            ),
        )
        ensure_default_products(conn, machine["serial"])

    sales_count = conn.execute("SELECT COUNT(*) AS total FROM sales").fetchone()["total"]
    if sales_count == 0:
        demo_sales = [
            (DEMO_MACHINE_CODE, 1, "Pinol", "MEI", 30, 1.5),
            (DEMO_MACHINE_CODE, 2, "Cloro", "Terminal", 40, 1.5),
            ("2222333344445555", 5, "Multiusos", "Terminal", 40, 1.5),
            ("2222333344445555", 7, "Aromatizante", "MEI", 35, 1.0),
            ("3333444455556666", 4, "Jabon para ropa", "Terminal", 50, 1.5),
            ("4444555566667777", 9, "Limpiavidrios", "MEI", 40, 1.5),
        ]
        conn.executemany(
            """
            INSERT INTO sales (machine_serial, product_id, product_name, method, amount, units, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [sale + (timestamp,) for sale in demo_sales],
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


def ensure_default_products(conn: sqlite3.Connection, serial: str) -> None:
    product_count = conn.execute(
        "SELECT COUNT(*) AS total FROM products WHERE machine_serial = ?",
        (serial,),
    ).fetchone()["total"]
    if product_count:
        return

    conn.executemany(
        """
        INSERT INTO products (machine_serial, product_id, name, relay, price, dispense_size)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                serial,
                product["product_id"],
                product["name"],
                product["relay"],
                product["price"],
                product["dispense_size"],
            )
            for product in DEFAULT_PRODUCTS
        ],
    )


def get_machine_or_404(conn: sqlite3.Connection, serial: str) -> sqlite3.Row:
    machine = conn.execute("SELECT * FROM machines WHERE serial = ?", (serial,)).fetchone()
    if not machine:
        raise HTTPException(status_code=404, detail="Maquina no encontrada")
    return machine


def register_machine(conn: sqlite3.Connection, payload: MachineCreate) -> Dict[str, Any]:
    if not is_16_digit_code(payload.serial):
        raise HTTPException(status_code=400, detail="La serie debe tener 16 digitos")

    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO machines (serial, model, location, status, last_seen, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(serial) DO UPDATE SET
          model = excluded.model,
          location = excluded.location,
          status = excluded.status,
          last_seen = excluded.last_seen
        """,
        (payload.serial, payload.model, payload.location, payload.status, timestamp, timestamp),
    )
    ensure_default_products(conn, payload.serial)
    machine = conn.execute("SELECT * FROM machines WHERE serial = ?", (payload.serial,)).fetchone()
    return row_to_dict(machine)


def touch_machine(conn: sqlite3.Connection, serial: str) -> Dict[str, Any]:
    if not is_16_digit_code(serial):
        raise HTTPException(status_code=400, detail="La serie debe tener 16 digitos")

    existing = conn.execute("SELECT * FROM machines WHERE serial = ?", (serial,)).fetchone()
    timestamp = now_iso()

    if existing:
        conn.execute(
            "UPDATE machines SET status = ?, last_seen = ? WHERE serial = ?",
            ("En linea", timestamp, serial),
        )
    else:
        register_machine(
            conn,
            MachineCreate(
                serial=serial,
                model="M10 Productos de Limpieza",
                location="Ubicacion pendiente",
                status="En linea",
            ),
        )

    machine = conn.execute("SELECT * FROM machines WHERE serial = ?", (serial,)).fetchone()
    return row_to_dict(machine)


def machine_summary(conn: sqlite3.Connection, serial: str) -> Dict[str, Any]:
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
        "machine": row_to_dict(machine),
        "summary": {
            "totalToday": totals["total_today"],
            "meiTotal": totals["mei_total"],
            "terminalTotal": totals["terminal_total"],
            "productsSold": totals["products_sold"],
            "liters": totals["liters"],
            "alerts": active_alerts,
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
        rows = conn.execute("SELECT * FROM machines ORDER BY created_at DESC").fetchall()
    return rows_to_dicts(rows)


@app.post("/machines")
def create_machine(payload: MachineCreate, _: None = Depends(verify_owner_access)) -> Dict[str, Any]:
    with get_db() as conn:
        machine = register_machine(conn, payload)
    return machine


@app.post("/machines/{serial}/heartbeat")
def heartbeat(serial: str) -> Dict[str, Any]:
    with get_db() as conn:
        machine = touch_machine(conn, serial)
    return {"machine": machine, "online": True}


@app.patch("/machines/{serial}/status")
def update_machine_status(
    serial: str,
    payload: MachineStatusPatch,
    _: None = Depends(verify_owner_access),
) -> Dict[str, Any]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        timestamp = now_iso()
        conn.execute(
            "UPDATE machines SET status = ?, last_seen = ? WHERE serial = ?",
            (payload.status, timestamp, serial),
        )
        machine = conn.execute("SELECT * FROM machines WHERE serial = ?", (serial,)).fetchone()
    return row_to_dict(machine)


@app.get("/machines/{serial}/summary")
def get_machine_summary(serial: str) -> Dict[str, Any]:
    with get_db() as conn:
        return machine_summary(conn, serial)


@app.get("/owner/summary")
def get_owner_summary(_: None = Depends(verify_owner_access)) -> Dict[str, Any]:
    with get_db() as conn:
        machines = rows_to_dicts(conn.execute("SELECT * FROM machines ORDER BY created_at DESC").fetchall())
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
            "SELECT * FROM products WHERE machine_serial = ? ORDER BY product_id",
            (serial,),
        ).fetchall()
    return rows_to_dicts(rows)


@app.patch("/machines/{serial}/products/{product_id}/price")
def update_product(
    serial: str,
    product_id: int,
    payload: ProductPatch,
    _: None = Depends(verify_owner_access),
) -> Dict[str, Any]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        product = conn.execute(
            "SELECT * FROM products WHERE machine_serial = ? AND product_id = ?",
            (serial, product_id),
        ).fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        next_name = payload.name if payload.name is not None else product["name"]
        next_price = payload.price if payload.price is not None else product["price"]
        next_dispense = payload.dispense_size if payload.dispense_size is not None else product["dispense_size"]

        conn.execute(
            """
            UPDATE products
            SET name = ?, price = ?, dispense_size = ?
            WHERE machine_serial = ? AND product_id = ?
            """,
            (next_name, next_price, next_dispense, serial, product_id),
        )
        updated = conn.execute(
            "SELECT * FROM products WHERE machine_serial = ? AND product_id = ?",
            (serial, product_id),
        ).fetchone()
    return row_to_dict(updated)


@app.get("/machines/{serial}/sales")
def list_sales(serial: str) -> List[Dict[str, Any]]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        rows = conn.execute(
            "SELECT * FROM sales WHERE machine_serial = ? ORDER BY created_at DESC, id DESC LIMIT 100",
            (serial,),
        ).fetchall()
    return rows_to_dicts(rows)


@app.post("/machines/{serial}/sales")
def create_sale(serial: str, payload: SaleCreate) -> Dict[str, Any]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        product = None
        if payload.product_id is not None:
            product = conn.execute(
                "SELECT * FROM products WHERE machine_serial = ? AND product_id = ?",
                (serial, payload.product_id),
            ).fetchone()

        product_id = payload.product_id
        product_name = payload.product_name or (product["name"] if product else "Venta manual")
        amount = payload.amount if payload.amount is not None else (product["price"] if product else 0)
        units = payload.units if payload.units is not None else (product["dispense_size"] if product else 1)
        timestamp = now_iso()

        conn.execute(
            """
            INSERT INTO sales (machine_serial, product_id, product_name, method, amount, units, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (serial, product_id, product_name, payload.method, amount, units, timestamp),
        )
        conn.execute("UPDATE machines SET status = ?, last_seen = ? WHERE serial = ?", ("En linea", timestamp, serial))
        sale = conn.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 1").fetchone()
    return row_to_dict(sale)


@app.get("/machines/{serial}/alerts")
def list_alerts(serial: str) -> List[Dict[str, Any]]:
    with get_db() as conn:
        get_machine_or_404(conn, serial)
        rows = conn.execute(
            "SELECT * FROM alerts WHERE machine_serial = ? ORDER BY created_at DESC, id DESC LIMIT 100",
            (serial,),
        ).fetchall()
    return rows_to_dicts(rows)


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
        conn.execute(
            """
            INSERT INTO alerts (machine_serial, type, title, detail, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (serial, payload.type, payload.title, payload.detail, int(payload.active), timestamp),
        )
        alert = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 1").fetchone()
    return row_to_dict(alert)
