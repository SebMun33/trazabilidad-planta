"""Modelos de dominio.

Las tablas de `planta` las crea la migración 0001 con DDL explícito (ver
docs/decisiones/0005-esquemas-y-search-path.md); por eso estos modelos son
`managed = False`. Las vistas de `planta_ref` las publica dbt.

Todas las tablas de `planta`, salvo `operario`, son de solo agregar filas: la
base lo impide con permisos (el rol de la app no tiene UPDATE ni DELETE) y con
un trigger (ni siquiera el dueño puede modificar filas).
"""

import uuid

from django.db import models
from django.db.models.functions import Now


class Urgencia(models.IntegerChoices):
    NORMAL = 1, "Normal"
    ALTA = 2, "Alta"
    URGENTE = 3, "Urgente"


# =============================================================================
# planta (registro original)
# =============================================================================
class Operario(models.Model):
    """Maestro de operarios. Única tabla de `planta` que admite UPDATE (nombre, activo)."""

    operario_id = models.AutoField(primary_key=True)
    nombre = models.TextField(unique=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        managed = False
        db_table = "operario"
        ordering = ["nombre"]
        verbose_name_plural = "operarios"

    def __str__(self) -> str:
        return self.nombre


class Trabajo(models.Model):
    """Identidad de un trabajo pendiente. Sus datos viven en las revisiones."""

    trabajo_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    creado_en = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        managed = False
        db_table = "trabajo"

    def __str__(self) -> str:
        return str(self.trabajo_id)


class TrabajoRevision(models.Model):
    """Versión de un trabajo: alta, cambio o retiro. La vigente es la de mayor número."""

    class Tipo(models.TextChoices):
        ALTA = "alta", "Alta"
        CAMBIO = "cambio", "Cambio"
        RETIRO = "retiro", "Retiro"

    class Origen(models.TextChoices):
        PEDIDO = "pedido", "Pedido de FoxPro"
        COTIZACION = "cotizacion", "Cotización de FoxPro"
        MANUAL = "manual", "Carga manual"

    revision_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    trabajo = models.ForeignKey(
        Trabajo, on_delete=models.DO_NOTHING, db_column="trabajo_id", related_name="revisiones"
    )
    revision = models.PositiveIntegerField()
    tipo = models.TextField(choices=Tipo.choices)
    origen = models.TextField(choices=Origen.choices)
    origen_ref = models.TextField(null=True, blank=True)
    pedido_id = models.IntegerField(null=True, blank=True)
    cotizacion_id = models.IntegerField(null=True, blank=True)
    plano = models.TextField()
    plano_descripcion = models.TextField(null=True, blank=True)
    cliente_id = models.IntegerField(null=True, blank=True)
    cliente_nombre = models.TextField(null=True, blank=True)
    cantidad = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    urgencia = models.SmallIntegerField(choices=Urgencia.choices, default=Urgencia.NORMAL)
    fecha_entrega_estimada = models.DateField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    creado_por = models.TextField()
    creado_en = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        managed = False
        db_table = "trabajo_revision"
        ordering = ["trabajo_id", "revision"]
        verbose_name = "revisión de trabajo"
        verbose_name_plural = "revisiones de trabajo"

    def __str__(self) -> str:
        return f"{self.plano} (rev. {self.revision})"


class TrabajoOperacion(models.Model):
    """Operación (paso de la hoja de ruta) de una revisión.

    `operacion_id` es estable entre revisiones: si una operación no cambia, la
    revisión nueva copia su id. Los eventos se registran contra ese id.
    """

    trabajo_operacion_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    revision = models.ForeignKey(
        TrabajoRevision,
        on_delete=models.DO_NOTHING,
        db_column="revision_id",
        related_name="operaciones",
    )
    operacion_id = models.UUIDField(default=uuid.uuid4)
    operacion_nro = models.PositiveSmallIntegerField()
    maquina_id = models.IntegerField(null=True, blank=True)
    descripcion = models.TextField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "trabajo_operacion"
        ordering = ["revision_id", "operacion_nro"]
        verbose_name = "operación de trabajo"
        verbose_name_plural = "operaciones de trabajo"

    def __str__(self) -> str:
        return f"Op. {self.operacion_nro}"


class Evento(models.Model):
    """Lo que pasó en planta: empezó, pausó o terminó una operación, o se anuló un evento."""

    class Tipo(models.TextChoices):
        EMPEZADO = "empezado", "Empezado"
        PAUSADO = "pausado", "Pausado"
        TERMINADO = "terminado", "Terminado"
        ANULACION = "anulacion", "Anulación"

    # El id lo genera la app antes de grabar: el INSERT es idempotente.
    evento_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tipo = models.TextField(choices=Tipo.choices)
    trabajo = models.ForeignKey(
        Trabajo, on_delete=models.DO_NOTHING, db_column="trabajo_id", related_name="eventos"
    )
    operacion_id = models.UUIDField(null=True, blank=True)
    maquina_id = models.IntegerField(null=True, blank=True)
    operario = models.ForeignKey(
        Operario,
        on_delete=models.DO_NOTHING,
        db_column="operario_id",
        null=True,
        blank=True,
        related_name="eventos",
    )
    ocurrido_en = models.DateTimeField()
    registrado_en = models.DateTimeField(db_default=Now(), editable=False)
    cantidad = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    anula_evento = models.ForeignKey(
        "self",
        on_delete=models.DO_NOTHING,
        db_column="anula_evento_id",
        null=True,
        blank=True,
        related_name="anulaciones",
    )
    registrado_por = models.TextField(null=True, blank=True)
    dispositivo = models.TextField()

    class Meta:
        managed = False
        db_table = "evento"
        ordering = ["ocurrido_en"]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} {self.ocurrido_en:%d/%m %H:%M}"


class CierreDia(models.Model):
    """Validación (o reapertura) de una jornada por el supervisor. Vale el último movimiento."""

    class Tipo(models.TextChoices):
        CIERRE = "cierre", "Cierre"
        REAPERTURA = "reapertura", "Reapertura"

    cierre_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    fecha = models.DateField()
    tipo = models.TextField(choices=Tipo.choices)
    registrado_por = models.TextField()
    registrado_en = models.DateTimeField(db_default=Now(), editable=False)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "cierre_dia"
        ordering = ["fecha", "registrado_en"]
        verbose_name = "cierre del día"
        verbose_name_plural = "cierres del día"

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} {self.fecha:%d/%m/%Y}"


# =============================================================================
# planta_ref (vistas publicadas por dbt; solo lectura)
# =============================================================================
class Maquina(models.Model):
    maquina_id = models.IntegerField(primary_key=True)
    nombre = models.TextField()
    nombre_corto = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = "maquinas"
        ordering = ["nombre"]
        verbose_name = "máquina"

    def __str__(self) -> str:
        return self.nombre


class PedidoPendiente(models.Model):
    """Renglón de pedido de FoxPro con cantidad pendiente."""

    pedido_linea_id = models.TextField(primary_key=True)
    pedido_id = models.IntegerField()
    orden_compra = models.TextField(null=True)
    fecha_pedido = models.DateField(null=True)
    cliente_id = models.IntegerField(null=True)
    cliente = models.TextField(null=True)
    plano = models.TextField()
    plano_descripcion = models.TextField(null=True)
    cantidad_pedida = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    cantidad_entregada = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    cantidad_pendiente = models.DecimalField(max_digits=12, decimal_places=2, null=True)

    class Meta:
        managed = False
        db_table = "pedidos_pendientes"
        ordering = ["-fecha_pedido", "pedido_id"]

    def __str__(self) -> str:
        return f"Pedido {self.pedido_id} - {self.plano}"


class CotizacionSinPedido(models.Model):
    """Renglón de cotización que (según la estimación de dbt) todavía no generó pedido."""

    cotizacion_linea_id = models.TextField(primary_key=True)
    cotizacion_id = models.IntegerField()
    fecha_cotizacion = models.DateField(null=True)
    cliente_id = models.IntegerField(null=True)
    cliente = models.TextField(null=True)
    plano = models.TextField()
    plano_descripcion = models.TextField(null=True)
    cantidad = models.DecimalField(max_digits=12, decimal_places=2, null=True)

    class Meta:
        managed = False
        db_table = "cotizaciones_sin_pedido"
        ordering = ["-fecha_cotizacion", "cotizacion_id"]

    def __str__(self) -> str:
        return f"Cotización {self.cotizacion_id} - {self.plano}"


class Ruta(models.Model):
    """Hoja de ruta estándar del plano (DATA0420 con la máquina de DATA0430).

    La clave es plano + renglón: un plano puede repetir el número de operación.
    """

    ruta_id = models.TextField(primary_key=True)
    plano = models.TextField()
    operacion_nro = models.IntegerField()
    maquina_id = models.IntegerField(null=True)
    descripcion = models.TextField(null=True)
    piezas_hora = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    renglon = models.IntegerField()

    class Meta:
        managed = False
        db_table = "rutas"
        ordering = ["plano", "renglon"]

    def __str__(self) -> str:
        return f"{self.plano} op. {self.operacion_nro}"


class UltimaPublicacion(models.Model):
    """Momento de la última carga de FoxPro a `raw` (de `raw._cargas`)."""

    publicado_en = models.DateTimeField(primary_key=True)

    class Meta:
        managed = False
        db_table = "ultima_publicacion"

    def __str__(self) -> str:
        return f"{self.publicado_en:%d/%m/%Y %H:%M}"
