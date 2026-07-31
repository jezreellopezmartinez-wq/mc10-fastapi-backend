from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def api(base_url: str, path: str, owner_code: str) -> Any:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        headers={"Accept": "application/json", "X-MC10-Owner-Code": owner_code},
    )
    try:
        with urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} en {path}: {body}") from error


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output-parent", required=True, type=Path)
    args = parser.parse_args()

    owner_code = os.getenv("MC10_OWNER_CODE", "").strip()
    if not (owner_code.isdigit() and len(owner_code) == 16):
        raise ValueError("MC10_OWNER_CODE no esta configurado correctamente")
    base_url = args.base_url.rstrip("/")
    if base_url != "https://mc10-fastapi-backend.onrender.com":
        raise ValueError("El respaldo de etapa 7 solo admite el backend de produccion")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    root = args.output_parent.resolve() / f"mc10-cloud-pre-cutover-{timestamp}"
    if root.exists():
        raise FileExistsError(root)
    data_root = root / "data"

    health = api(base_url, "/health", owner_code)
    machines = api(base_url, "/machines", owner_code)
    if not isinstance(machines, list):
        raise ValueError("La API no devolvio una lista de maquinas")
    write_json(data_root / "health.json", health)
    write_json(data_root / "machines.json", machines)

    totals = {"machines": len(machines), "products": 0, "sales": 0, "alerts": 0}
    sale_ids: set[str] = set()
    for machine in machines:
        serial = str(machine.get("serial") or "")
        if not (serial.isdigit() and len(serial) == 16):
            raise ValueError(f"Serie no valida recibida: {serial}")
        machine_root = data_root / "machines" / serial
        summary = api(base_url, f"/machines/{serial}/summary", owner_code)
        write_json(machine_root / "summary.json", summary)
        for label in ("products", "sales", "alerts"):
            rows = api(base_url, f"/machines/{serial}/{label}", owner_code)
            if not isinstance(rows, list):
                raise ValueError(f"{label} de {serial} no es una lista")
            for row in rows:
                row.setdefault("machine_serial", serial)
                if label == "sales" and row.get("sale_id"):
                    sale_id = str(row["sale_id"])
                    if sale_id in sale_ids:
                        raise ValueError(f"sale_id duplicado: {sale_id}")
                    sale_ids.add(sale_id)
            totals[label] += len(rows)
            write_json(machine_root / f"{label}.json", rows)

    manifest = {
        "schema": "mc10-cloud-backup-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"api_base_url": base_url},
        "secrets_included": False,
        "totals": totals,
    }
    write_json(root / "manifest.json", manifest)

    checksum_lines = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
            checksum_lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    archive = shutil.make_archive(str(root), "zip", root.parent, root.name)
    print(json.dumps({"backup": str(root), "archive": archive, "totals": totals}, sort_keys=True))


if __name__ == "__main__":
    main()
