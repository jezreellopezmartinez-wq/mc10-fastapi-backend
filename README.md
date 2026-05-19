# MC10 FastAPI Backend

Backend inicial para MC Vending System usando FastAPI y SQLite local.

## Ejecutar localmente

```bash
cd mc10-fastapi-backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Luego abre:

```text
http://127.0.0.1:8000/docs
```

## Códigos demo

Dueño:

```text
9876543210987654
```

Máquina demo:

```text
1234567890123456
```

## Seguridad del dueño

Los endpoints privados de dueño requieren el header:

```text
X-MC10-Owner-Code: 9876543210987654
```

En producción cambia el código con la variable de entorno:

```bash
MC10_OWNER_CODE=tu_codigo_privado
```

El panel web usa el código que el dueño escribe en login y lo manda al backend como header. Así el código privado ya no depende solamente del JavaScript público.

## Endpoints principales

- `GET /health`
- `POST /auth/login`
- `GET /owner/summary` requiere `X-MC10-Owner-Code`
- `GET /machines` requiere `X-MC10-Owner-Code`
- `POST /machines` requiere `X-MC10-Owner-Code`
- `POST /machines/:serial/heartbeat`
- `PATCH /machines/:serial/status` requiere `X-MC10-Owner-Code`
- `GET /machines/:serial/summary`
- `GET /machines/:serial/products`
- `PATCH /machines/:serial/products/:product_id/price` requiere `X-MC10-Owner-Code`
- `GET /machines/:serial/sales`
- `POST /machines/:serial/sales`
- `GET /machines/:serial/alerts`
- `POST /machines/:serial/alerts/clear` requiere `X-MC10-Owner-Code`
- `POST /machines/:serial/alerts`

## Notas

- La base SQLite se crea automáticamente como `mc10_cloud.sqlite3`.
- El backend crea datos demo la primera vez que arranca.
- CORS está abierto para facilitar pruebas con Netlify durante el prototipo.
- Para producción se debe agregar autenticación real, HTTPS, tokens y permisos por usuario.
