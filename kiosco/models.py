"""Datos locales del kiosco (SQLite en la PC de planta, base `local`).

El kiosco nunca depende de la conexión con Neon para mostrar ni para registrar:
- `Foto` es la última copia de lo que necesita (trabajos activos, operarios,
  máquinas, días cerrados), traída por el proceso de sincronización.
- `EventoPendiente` es la cola de salida: cada registro se graba acá primero y
  el proceso de sincronización lo inserta en `planta.evento` de forma idempotente
  (mismo `evento_id`, `ON CONFLICT DO NOTHING`).
Ver docs/decisiones/0006-kiosco-sin-conexion.md.
"""

import uuid

from django.db import models


class Foto(models.Model):
    """Copia local del estado de planta. Hay una sola fila (id = 1)."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    datos = models.JSONField()
    obtenida_en = models.DateTimeField()

    class Meta:
        verbose_name = "copia local"

    def __str__(self) -> str:
        return f"Copia local del {self.obtenida_en:%d/%m/%Y %H:%M:%S}"


class EventoPendiente(models.Model):
    """Evento registrado en el kiosco, con su estado de envío a la base central."""

    # `id` da el orden exacto de registro (la hora puede repetirse) y de envío.
    id = models.BigAutoField(primary_key=True)
    evento_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    tipo = models.CharField(max_length=20)
    trabajo_id = models.UUIDField()
    operacion_id = models.UUIDField(null=True, blank=True)
    maquina_id = models.IntegerField(null=True, blank=True)
    operario_id = models.IntegerField(null=True, blank=True)
    ocurrido_en = models.DateTimeField()
    observaciones = models.TextField(blank=True, default="")
    anula_evento_id = models.UUIDField(null=True, blank=True)
    registrado_por = models.CharField(max_length=200)
    creado_en = models.DateTimeField(auto_now_add=True)
    enviado_en = models.DateTimeField(null=True, blank=True)
    rechazado_en = models.DateTimeField(null=True, blank=True)
    intentos = models.PositiveIntegerField(default=0)
    ultimo_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["enviado_en", "rechazado_en"])]

    def __str__(self) -> str:
        return f"{self.tipo} {self.evento_id}"

    @property
    def pendiente(self) -> bool:
        return self.enviado_en is None and self.rechazado_en is None


class Actividad(models.Model):
    """Último uso del kiosco: la sincronización solo trae la copia mientras se usa.

    Así, con el kiosco quieto, no hay consultas y Neon puede suspender el cómputo.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    ultima = models.DateTimeField()

    def __str__(self) -> str:
        return f"Último uso: {self.ultima:%d/%m/%Y %H:%M:%S}"
