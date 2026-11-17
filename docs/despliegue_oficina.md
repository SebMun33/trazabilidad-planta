# Despliegue de la parte A (oficina) en Render

La oficina es la única parte que se publica en internet. Corre en
[Render](https://render.com) (plan Free) con un dominio propio, y usa la base de
Neon. El kiosco de planta **no** se publica (ver `instalacion_ubuntu.md`).

```
planta.midominio.com.ar ──CNAME (DNS del dominio)──▶ Render (Django + Gunicorn)
                                                         │ DATABASE_URL (app_planta)
                                                         ▼
                                                       Neon
```

## Cómo está armado

- `render.yaml` (Blueprint) define el servicio: build con `uv`, Gunicorn con 2
  workers, chequeo de salud en `/salud/` (no toca la base, así Neon puede
  suspenderse) y región Virginia (la más cercana a Neon São Paulo).
- Settings: `config.settings.prod_oficina` (HTTPS obligatorio, HSTS, cookies
  seguras). El host `*.onrender.com` se agrega solo; el dominio propio va en
  `DJANGO_ALLOWED_HOSTS` y los orígenes CSRF se derivan de los hosts.
- La app corre con el rol `app_planta` (sin `UPDATE`/`DELETE` en `planta`). Las
  migraciones **no** corren en Render: se aplican con el rol dueño desde una PC de
  desarrollo (ver más abajo).
- Plan Free: si nadie entra durante 15 minutos el servicio se suspende y la
  siguiente visita tarda alrededor de un minuto. Pasar a un plan pago (Starter)
  es un cambio en el panel, sin tocar código.

## 1. Crear el servicio

1. Entrar a Render con la cuenta de GitHub y autorizar el repositorio.
2. **New → Blueprint** y elegir el repositorio. Render lee `render.yaml`.
3. Completar las variables marcadas como secretas:

   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` | Conexión **directa** de Neon (sin `-pooler`) con el rol `app_planta` y `?sslmode=require` |
   | `DJANGO_ALLOWED_HOSTS` | El dominio propio, p. ej. `planta.midominio.com.ar` |

   `DJANGO_SECRET_KEY` la genera Render. No hace falta `DATABASE_URL_OWNER`.
4. **Apply**. El primer build tarda unos minutos.
5. Probar `https://trazabilidad-planta-oficina.onrender.com/salud/` (debe decir
   `ok`) y después `/cuentas/login/`.

Cada `git push` a `main` vuelve a desplegar (`autoDeploy`). Los logs están en
el panel del servicio.

## 2. Migraciones

Render Free no tiene comando previo al despliegue, y además la app no tiene
permisos para cambiar tablas. Cuando un cambio trae migraciones, aplicarlas
**antes** de hacer push, desde una PC con el repo:

```bash
# .env con DATABASE_URL_OWNER apuntando a la base de destino (rol app_planta_owner)
bash ops/migrar.sh
```

## 3. Dominio propio (DNS en DonWeb / Ferozo)

1. En Render: servicio → **Settings → Custom Domains → Add** y escribir
   `planta.midominio.com.ar`. Render muestra el destino del CNAME
   (`trazabilidad-planta-oficina.onrender.com`).
2. En el panel de DonWeb (Ferozo): **Dominios →** el dominio **→** zona DNS
   (registros DNS). Agregar:

   | Tipo | Nombre | Valor |
   |---|---|---|
   | CNAME | `planta` | `trazabilidad-planta-oficina.onrender.com` |

   No tocar los registros del dominio principal ni los de correo (MX).
3. Esperar la propagación (minutos a algunas horas). Render verifica el registro
   y emite el certificado HTTPS solo.

## 4. Pasar de la rama `dev-planta` a producción (Neon `main`)

Para probar, `DATABASE_URL` puede apuntar a la rama `dev-planta`. Para usarla en
serio, la base es `main`. Estos pasos los hace el responsable de la base, en
este orden:

1. Roles y esquemas en `main`: correr `ops/01_neon_planta.sql` (ver su
   encabezado) con el rol dueño de Neon.
2. Migraciones contra `main`: `bash ops/migrar.sh` con `DATABASE_URL_OWNER` de
   `main`.
3. Vistas `planta_ref` en `main`: en el proyecto dbt,
   `dbt build -s path:models/planta_ref` con el target de producción (ver
   `integracion_dw.md`).
4. Crear el usuario de oficina (`createsuperuser`) y cargar los operarios en
   `/admin/`.
5. Cambiar `DATABASE_URL` en Render y en la PC de planta por las de `main`.

Opcional: borrar de `main` los esquemas `dev_*` que dejó dbt (unos 110 MB del
plan Free).
