"""Datos de ejemplo FICTICIOS para desarrollo, demo y tests.

Llena `planta_demo` (que solo existe en Postgres local/CI, ver
ops/dev/planta_ref_demo.sql) y el maestro de operarios. Ningún dato es real.
"""

from datetime import date, timedelta

from django.db import connection

from .models import Operario

MAQUINAS = [
    (101, "Torno CNC grande", "CNC grande"),
    (102, "Torno CNC chico", "CNC chico"),
    (103, "Centro de mecanizado vertical", "Centro mec."),
    (104, "Torno revólver", "Revólver"),
    (105, "Agujereadora de pie", "Agujereadora"),
    (106, "Laminadora de roscas", "Laminadora"),
    (107, "Amoladora", "Amoladora"),
]

CLIENTES = [
    (1, "Metalúrgica Andina SA"),
    (2, "Hidráulica del Litoral SRL"),
    (3, "Agromáquinas Pampa SA"),
    (4, "Bombas Patagónicas SA"),
]

PLANOS = [
    ("BJ-100", "Buje de bronce Ø40"),
    ("EJ-220/A", "Eje de transmisión 1045"),
    ("PR 15-3", "Perno roscado M16"),
    ("SEP-08", "Separador de acero"),
    ("MZ-500 REV2", "Maza de rueda"),
]

# (plano, renglón, operación, máquina, descripción, piezas/hora). Como en FoxPro,
# un plano puede repetir el número de operación (MZ-500 REV2 tiene dos secuencias).
RUTAS = [
    ("BJ-100", 1, 1, 102, "Tornear exterior e interior", 20),
    ("BJ-100", 2, 2, 105, "Agujero de lubricación", 60),
    ("EJ-220/A", 1, 1, 101, "Desbaste y terminación", 8),
    ("EJ-220/A", 2, 2, 103, "Fresar chavetero", 12),
    ("EJ-220/A", 3, 3, 107, "Rectificar asiento de rodamiento", 15),
    ("PR 15-3", 1, 1, 104, "Cortar y tornear", 90),
    ("PR 15-3", 2, 2, 106, "Laminar rosca", 300),
    ("SEP-08", 1, 1, 102, None, 120),
    ("MZ-500 REV2", 1, 1, 101, "Tornear cara y alojamientos", 4),
    ("MZ-500 REV2", 2, 2, 103, "Agujeros de bulones", 6),
    ("MZ-500 REV2", 3, 3, 105, "Roscar agujeros", 10),
    ("MZ-500 REV2", 4, 1, 104, "Segunda secuencia: tornear contracara", 5),
]

OPERARIOS = ["Lucía Demo", "Martín Demo", "Carla Demo"]


def _pedidos(hoy: date):
    # (pedido, renglon, oc, dias_atras, cliente, plano, cantidad, entregado)
    return [
        (3001, 1, "OC-7781", 20, 1, "EJ-220/A", 40, 10),
        (3001, 2, "OC-7781", 20, 1, "BJ-100", 200, 0),
        (3002, 1, "4410", 9, 2, "PR 15-3", 1000, 0),
        (3003, 1, "A-55", 4, 3, "MZ-500 REV2", 12, 0),
        (3004, 1, "991", 60, 4, "SEP-08", 500, 500),  # entregado: no aparece
    ]


def _cotizaciones(hoy: date):
    # (cotizacion, renglon, dias_atras, cliente, plano, cantidad, tiene_pedido)
    return [
        (2101, 1, 3, 2, "SEP-08", 300, False),
        (2101, 2, 3, 2, "BJ-100", 50, False),
        (2102, 1, 15, 4, "EJ-220/A", 10, True),  # ya tiene pedido: no aparece
    ]


def cargar_demo(hoy: date | None = None) -> dict[str, int]:
    """Carga (o recarga) los datos ficticios. Idempotente."""
    hoy = hoy or date.today()
    with connection.cursor() as cur:
        cur.execute(
            "TRUNCATE planta_demo.maquinas, planta_demo.clientes, planta_demo.planos,"
            " planta_demo.pedidos_lineas, planta_demo.cotizaciones_lineas,"
            " planta_demo.rutas, planta_demo.cargas"
        )
        cur.executemany("INSERT INTO planta_demo.maquinas VALUES (%s, %s, %s)", MAQUINAS)
        cur.executemany("INSERT INTO planta_demo.clientes VALUES (%s, %s)", CLIENTES)
        cur.executemany("INSERT INTO planta_demo.planos VALUES (%s, %s)", PLANOS)
        cur.executemany("INSERT INTO planta_demo.rutas VALUES (%s, %s, %s, %s, %s, %s)", RUTAS)
        cur.executemany(
            "INSERT INTO planta_demo.pedidos_lineas VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (p, r, oc, hoy - timedelta(days=d), c, pl, q, e)
                for p, r, oc, d, c, pl, q, e in _pedidos(hoy)
            ],
        )
        cur.executemany(
            "INSERT INTO planta_demo.cotizaciones_lineas VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [
                (co, r, hoy - timedelta(days=d), c, pl, q, tp)
                for co, r, d, c, pl, q, tp in _cotizaciones(hoy)
            ],
        )
        cur.execute("INSERT INTO planta_demo.cargas (fin) VALUES (now())")

    for nombre in OPERARIOS:
        Operario.objects.get_or_create(nombre=nombre)

    return {
        "maquinas": len(MAQUINAS),
        "pedidos": len(_pedidos(hoy)),
        "cotizaciones": len(_cotizaciones(hoy)),
        "operarios": len(OPERARIOS),
    }
