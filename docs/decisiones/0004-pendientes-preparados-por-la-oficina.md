# 0004 — La oficina prepara la lista de pendientes

- Estado: aceptada
- Fecha: 2026-11-10

## Contexto

Podría generarse la lista de trabajos de planta automáticamente con cada
renglón de pedido pendiente de FoxPro. En la práctica no sirve:

- hay pedidos viejos con saldo que nadie va a fabricar;
- a veces se arranca una pieza con la cotización aprobada, antes de que exista
  el pedido en FoxPro;
- hay trabajos que no vienen de ningún sistema (reparaciones, pruebas);
- la oficina decide prioridades, cantidades y entregas que FoxPro no registra.

## Decisión

- Un trabajo entra a planta **solo cuando la oficina lo pasa a pendientes**,
  desde uno de tres orígenes:

  | Origen | Fuente | Se guarda en `origen_ref` |
  |---|---|---|
  | `pedido` | `planta_ref.pedidos_pendientes` | `pedido_linea_id` |
  | `cotizacion` | `planta_ref.cotizaciones_sin_pedido` | `cotizacion_linea_id` |
  | `manual` | carga a mano | — |

- Al preparar, la hoja de ruta estándar del plano (`planta_ref.rutas`) se
  **sugiere** y la oficina la ajusta: agrega, quita o cambia operaciones y
  máquinas, y fija urgencia y fecha de entrega estimada.
- Los datos del origen (plano, cliente, cantidad) se **copian** en la revisión:
  si después cambian en FoxPro, el trabajo conserva lo que se decidió fabricar.
- No puede haber dos trabajos activos para el mismo renglón de origen.
- Los pedidos de más de un año se ocultan por defecto en la lista de origen
  (siguen disponibles con «Ver todos»).

## Consecuencias

- La lista de planta refleja lo que de verdad se va a fabricar, en el orden que
  decide la oficina.
- Pasar a pendientes es un paso manual más por trabajo; a cambio, la oficina
  revisa la hoja de ruta antes de que llegue al kiosco.
- `origen_ref` permite al warehouse unir cada trabajo con su pedido o
  cotización y medir el tiempo desde el pedido hasta la terminación.
