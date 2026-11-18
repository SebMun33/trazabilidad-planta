# 0001 — El registro de planta solo agrega filas

- Estado: aceptada
- Fecha: 2026-11-10

## Contexto

Lo que pasa en planta (quién empezó qué operación, cuándo la terminó, cuántas
piezas) es la base para medir tiempos y, más adelante, para cruzarlo con los
pedidos en el data warehouse. Si una fila se puede editar o borrar, se pierde
la historia: no se sabe qué decía antes, quién lo cambió ni por qué. Además, un
error de carga en el kiosco tiene que poder corregirse sin que nadie toque la
base a mano.

## Decisión

- Las tablas del esquema `planta` (`trabajo`, `trabajo_revision`,
  `trabajo_operacion`, `evento`, `cierre_dia`, `nota`) **solo admiten `INSERT`**.
- Dos barreras independientes:
  1. El rol de la app en ejecución (`app_planta`) no tiene `UPDATE` ni `DELETE`
     sobre esas tablas.
  2. Un trigger (`planta.impedir_modificacion`) rechaza `UPDATE` y `DELETE`
     incluso al dueño de las tablas (`app_planta_owner`).
- Las correcciones también son filas nuevas:
  - un evento mal cargado se **anula** con un evento `anulacion` que apunta al
    original (cada evento se anula una sola vez, por índice único);
  - un cambio en un trabajo es una **revisión** nueva; retirarlo es una revisión
    de tipo `retiro`;
  - reabrir un día cerrado es un movimiento `reapertura`.
- **Excepción: `planta.operario`.** Es un maestro, no un hecho: admite `UPDATE`
  de `nombre`, `activo` y `usuario_id` (permisos por columna), y nunca `DELETE`.
  Desactivar a un operario conserva todos sus eventos.
- Los identificadores (`uuid`) los genera la app antes de grabar, para que los
  reenvíos sean idempotentes (`ON CONFLICT DO NOTHING`).

## Consecuencias

- La historia completa queda en la base: auditoría y métricas salen de una
  consulta, sin tablas de log aparte.
- El estado actual no se guarda: hay que calcularlo (ver
  [0002](0002-eventos-en-vez-de-estados.md)).
- La base crece siempre. Con el volumen de una tornería (decenas de eventos por
  día) son pocos MB por año.
- Un dato mal cargado nunca desaparece: queda anulado y visible en «Registros».
- Los tests verifican que `app_planta` no puede modificar ni borrar, y que el
  trigger frena al dueño.
