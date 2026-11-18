# 0002 — Eventos en vez de estados

- Estado: aceptada
- Fecha: 2026-11-10

## Contexto

La forma habitual de seguir un trabajo es una columna `estado` que se va
actualizando («en proceso», «terminado»). Eso choca con la decisión
[0001](0001-solo-agregar-filas.md) y además pierde información: cuánto duró
cada operación, cuántas pausas tuvo y quién la hizo. También complica el kiosco
sin conexión, porque dos actualizaciones del mismo estado pueden pisarse.

## Decisión

- En planta se registran **hechos**: `empezado`, `pausado`, `terminado`, con
  operación, operario, máquina, hora en que ocurrió y hora en que se registró.
- El estado se **deriva** en `planta/servicios/estado.py`:
  - eventos vigentes = todos los eventos menos los anulados;
  - el estado de una operación es el de su último evento vigente
    (sin eventos: «Pendiente»);
  - el de un trabajo sale de su última revisión y de sus operaciones:
    «Retirado», «Terminado en planta» (todas terminadas), «En proceso» (alguna
    empezada) o «En cola».
- La función que deriva el estado por operación es **pura** (recibe la lista de
  eventos), así la usan igual la oficina, contra Postgres, y el kiosco, contra
  su copia local más su cola de envío
  ([0006](0006-kiosco-sin-conexion.md)).
- Las operaciones tienen un `operacion_id` estable entre revisiones: si la
  oficina cambia la hoja de ruta, los eventos ya registrados siguen apuntando a
  la misma operación.

## Consecuencias

- Tiempos reales por operación, pausas y operario salen directo de los eventos.
- Calcular el estado cuesta una consulta más que leer una columna. Con el
  volumen de la planta (decenas de trabajos activos) no importa; si creciera,
  se puede materializar una vista sin cambiar el modelo.
- Una regla de negocio nueva (por ejemplo, «no terminar sin haber empezado»)
  se valida contra el estado derivado, en un solo lugar.
