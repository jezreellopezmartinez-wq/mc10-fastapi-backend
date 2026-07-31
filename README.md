# MC10 FastAPI Backend

Backend para MC Vending System usando FastAPI y PostgreSQL.

## Ejecutar localmente

```bash
cd mc10-fastapi-backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql://usuario:clave@servidor:5432/mc10_cloud'
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Luego abre:

```text
http://127.0.0.1:8000/docs
```

## Códigos demo

Los datos demo ya no se cargan por default. Si quieres activarlos para pruebas, arranca con:

```bash
MC10_ENABLE_DEMO_DATA=1
```

Solo con esa bandera se siembran máquinas y ventas demo.

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

## Cambios importantes del backend real

- `POST /auth/login` ya no crea máquinas nuevas con cualquier código de 16 dígitos.
- una máquina cliente solo entra si ya fue registrada antes por la PC.
- `POST /machines` ya acepta y actualiza el perfil real de la máquina.
- `PATCH /machines/:serial/products/:product_id/price` ahora funciona como `upsert` y guarda:
  - nombre
  - precio
  - relay
  - `dispense_size`
  - `ms`
  - `calibration_ms`
  - `active`
  - `category`
- `POST /machines/:serial/sales` ahora guarda metadata real de venta:
  - `sale_id`
  - `request_id`
  - `payment_method`
  - `currency`
  - `sold_at`
  - `source`
  - `app_version`
  - `channel`
  - `relay`
  - `local_sale_counter`
  - `dispatch_status`
- el listado de productos ya devuelve métricas reales por producto:
  - ventas MEI
  - ventas Terminal
  - cantidad
  - litros/unidades
  - última venta
- el backend ya no depende de productos demo para máquinas reales.

## Endpoints principales

- `GET /health`
- `POST /auth/login`
- `GET /owner/summary` requiere `X-MC10-Owner-Code`
- `GET /machines` requiere `X-MC10-Owner-Code`
- `POST /machines`
- `POST /machines/:serial/heartbeat`
- `PATCH /machines/:serial/status`
- `GET /machines/:serial/summary`
- `GET /machines/:serial/products`
- `PATCH /machines/:serial/products/:product_id/price`
- `GET /machines/:serial/sales`
- `POST /machines/:serial/sales`
- `GET /machines/:serial/alerts`
- `POST /machines/:serial/alerts/clear` requiere `X-MC10-Owner-Code`
- `POST /machines/:serial/alerts`

## Notas

- `DATABASE_URL` es obligatoria. El backend se detiene de forma segura si no está
  configurada.
- Las tablas de PostgreSQL se crean automáticamente al iniciar.
- No guardes la URL ni la contraseña de PostgreSQL en el repositorio.
- Los datos demo solo se crean si `MC10_ENABLE_DEMO_DATA=1`.
- Si una máquina no existe, el login cliente ya no la da de alta solo por escribir una clave.
- Para que una máquina aparezca en la web, primero debe registrarse desde la PC/panel.
- CORS está abierto para facilitar pruebas con Netlify durante el prototipo.
- Para producción se debe agregar autenticación real, HTTPS, tokens y permisos por usuario.
