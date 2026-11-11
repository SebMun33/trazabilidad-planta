# Trazabilidad de planta

Registro del avance de producción en una tornería: la oficina prepara la lista
de trabajos pendientes (desde pedidos y cotizaciones del sistema FoxPro) y los
operarios registran en un kiosco qué operación empiezan, pausan y terminan.

> En construcción. El README completo (problema, arquitectura, capturas y
> decisiones) llega en la etapa de portafolio.

## Desarrollo local

Requisitos: [uv](https://docs.astral.sh/uv/) y Docker.

```bash
cp .env.example .env            # y completar DJANGO_SECRET_KEY
docker compose up -d --wait     # Postgres local con roles, esquemas y vistas de ejemplo
uv sync
bash ops/migrar.sh              # migraciones con el rol dueño
DJANGO_DB_OWNER=1 uv run python manage.py seed_demo   # datos FICTICIOS
uv run pytest
uv run python manage.py runserver
```

## Licencia

[MIT](LICENSE)
