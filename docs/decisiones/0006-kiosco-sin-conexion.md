# 0006 — Kiosco que sigue funcionando sin conexión

- Estado: aceptada
- Fecha: 2026-11-11

## Contexto

El kiosco de planta corre en una PC Ubuntu vieja y la base central está en Neon.
Si la conexión a internet se corta, o Neon tarda en despertar, los operarios
igual tienen que poder registrar que empezaron, pausaron o terminaron una
operación. Además, Neon cobra por horas de cómputo: un kiosco consultando cada
pocos segundos todo el día no dejaría suspender el cómputo nunca.

## Decisión

- Las pantallas del kiosco **solo usan una base local SQLite** (`local`):
  - `Foto`: última copia de trabajos activos (y terminados del último día),
    operarios, máquinas y días cerrados.
  - `EventoPendiente`: cola de salida. Cada registro se valida contra el estado
    local y se graba primero acá.
- Un **proceso aparte** (`manage.py sincronizar_kiosco`, servicio de systemd):
  - Envía la cola en orden. El `evento_id` lo genera el kiosco y el `INSERT` usa
    `ON CONFLICT DO NOTHING`: reenviar es inofensivo.
  - Si la base central rechaza un evento (por ejemplo, un trabajo inexistente),
    lo marca como rechazado y sigue con los demás; el kiosco lo muestra.
  - Renueva la copia cada minuto **solo mientras el kiosco se usa** (último uso
    hace menos de 10 minutos) y cierra la conexión al terminar, para que Neon
    pueda suspenderse.
- El estado local es la copia más los eventos del kiosco que la copia todavía no
  incluye, con las **mismas reglas de derivación** que la oficina
  (`planta.servicios.estado.eventos_vigentes` y `estado_por_operacion`).
- «Deshacer» (60 s) graba una anulación en la cola; el evento original no se toca.
- Las pantallas no piden contraseña: solo responden a 127.0.0.1/::1 (Chromium en
  modo kiosco en la misma PC) y Gunicorn escucha solo en 127.0.0.1.

## Consecuencias

- Los cambios de oficina tardan hasta un minuto en verse en el kiosco (o más si
  no hay conexión); la barra muestra la hora de la copia y avisa si es vieja.
- Con un solo kiosco, las reglas validadas localmente alcanzan. Con varios
  kioscos podrían cruzarse dos «Empecé» de la misma operación sin conexión: la
  oficina lo ve en registros y puede anular uno.
- Los tests verifican que ninguna pantalla del kiosco consulte la base central.
