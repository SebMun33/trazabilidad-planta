import uuid
from pathlib import Path

import django.db.models.deletion
import django.db.models.functions.datetime
from django.db import migrations, models

DDL = (Path(__file__).resolve().parent.parent / "sql" / "0004_notas.sql").read_text(
    encoding="utf-8"
)
DDL_REVERSA = """
DROP TABLE IF EXISTS planta.nota;
ALTER TABLE planta.operario DROP COLUMN IF EXISTS usuario_id;
"""

TIPOS = [
    ("observacion", "Observación"),
    ("sugerencia", "Sugerencia"),
    ("pregunta", "Pregunta"),
    ("respuesta", "Respuesta"),
]


class Migration(migrations.Migration):
    dependencies = [("planta", "0003_ruta_renglon")]

    operations = [
        migrations.RunSQL(DDL, DDL_REVERSA),
        migrations.AddField(
            model_name="operario",
            name="usuario_id",
            field=models.IntegerField(blank=True, null=True, unique=True),
        ),
        migrations.CreateModel(
            name="Nota",
            fields=[
                (
                    "nota_id",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("operacion_id", models.UUIDField(blank=True, null=True)),
                ("tipo", models.TextField(choices=TIPOS)),
                ("texto", models.TextField()),
                ("autor", models.TextField()),
                ("usuario_id", models.IntegerField(blank=True, null=True)),
                ("escrita_en", models.DateTimeField()),
                (
                    "registrada_en",
                    models.DateTimeField(
                        db_default=django.db.models.functions.datetime.Now(), editable=False
                    ),
                ),
                ("dispositivo", models.TextField()),
                (
                    "trabajo",
                    models.ForeignKey(
                        db_column="trabajo_id",
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="notas",
                        to="planta.trabajo",
                    ),
                ),
                (
                    "responde_a",
                    models.ForeignKey(
                        blank=True,
                        db_column="responde_a",
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="respuestas",
                        to="planta.nota",
                    ),
                ),
                (
                    "operario",
                    models.ForeignKey(
                        blank=True,
                        db_column="operario_id",
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="notas",
                        to="planta.operario",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "notas",
                "db_table": "nota",
                "ordering": ["escrita_en", "registrada_en"],
                "managed": False,
            },
        ),
    ]
