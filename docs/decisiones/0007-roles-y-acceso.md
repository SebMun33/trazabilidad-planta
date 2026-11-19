# 0007 — Roles, ingreso por nombre y notas

- Estado: aceptada
- Fecha: 2026-11-18

## Contexto

En planta nadie quiere tipear contraseñas, y los operarios no van a volver a
ingresar cada vez que registran algo. En cambio, la oficina está publicada en
internet. Además, los permisos tenían que poder entenderse y asignarse sin
mirar casillas sueltas, y hacía falta un canal para dejar observaciones y
preguntas sobre un trabajo.

## Decisión

**Roles con juegos fijos de permisos** (`cuentas/roles.py`). Cada usuario tiene
uno; en el admin se elige de una lista y nunca se tocan permisos sueltos:

| Rol | Permisos |
|---|---|
| Operario | registrar avances, escribir notas (kiosco, sin contraseña) |
| Oficina técnica | ver, preparar pendientes, escribir notas, anular registros, cerrar el día, ver importes |
| Contabilidad | ver e importes (solo lectura) |
| Staff | todo, admin incluido, salvo ver o editar superusuarios |

El superusuario no es un rol: es la cuenta personal del dueño del sistema. Los
permisos se declaran en un modelo sin tabla (`cuentas.Permisos`) y los grupos se
sincronizan con el código después de cada `migrate`.

**Probar como operario.** El superusuario tiene un botón que abre el kiosco en
otra pestaña como el usuario «operario» (se crea la primera vez, sin
contraseña). En la nube el kiosco solo responde en este modo; como ahí no corre
el proceso de sincronización, se sincroniza dentro de cada pedido: lo
registrado se envía en el momento y la lista se trae de nuevo cada 30 s o con
«Actualizar lista». Ese usuario
está oculto para todos menos el superusuario (admin y kiosco de planta). Lo que
registra va a la base real con `dispositivo = 'prueba'` y se muestra marcado
«prueba»; «Deshacer pruebas» anula todos sus registros de una vez. En los
análisis de dbt conviene excluir `dispositivo = 'prueba'`.

Los importes de las cotizaciones (costos y precios de FoxPro) requieren el
permiso `ver_importes`. Los operarios nunca lo tienen y la copia del kiosco no
incluye importes.

**Ingreso por nombre.** Se escribe el nombre (sin importar mayúsculas ni tildes);
si el usuario tiene contraseña, se pide en un segundo paso. Los usuarios sin
contraseña **no** pueden entrar por la web: registran desde el kiosco, que solo
responde en la PC de planta. Así, adivinar un nombre desde internet no alcanza
para registrar avances. Hay un bloqueo de 15 minutos después de 5 intentos
fallidos. Los nombres son únicos sin contar mayúsculas (índice en la base) ni
tildes (validación del admin).

**Operario automático.** Un usuario con rol Operario crea (o vincula por nombre)
su fila en `planta.operario` mediante `operario.usuario_id`; si cambia de rol o
se desactiva, deja de aparecer en el kiosco y su historia queda. La tabla de
operarios sigue siendo la que referencian los eventos y el data warehouse.

**Quién lo hizo.** En el kiosco, cada registro tiene un «¿Quién lo hizo?»
(por defecto, el que ingresó): cualquiera puede anotar lo que hizo otro. Se
guardan los dos: el evento lleva al operario que hizo el trabajo y
`registrado_por`, a quien lo cargó.

**Notas** (`planta.nota`, solo agregar filas): observación, sugerencia o
pregunta sobre un trabajo u operación, y respuestas. Cada una guarda autor y
fecha y hora. Desde el kiosco se escriben también sin conexión (cola propia,
`nota_id` idempotente).

**Avisos preparados** (`planta/servicios/avisos.py`): al grabarse una nota se
avisa a Oficina técnica y Staff por los canales de `AVISOS_CANALES`. Por defecto
solo se registra en el log; el mail (`CanalCorreo`, con `EMAIL_URL`) se activa
por configuración, y WhatsApp se agrega como otra clase de canal.

## Consecuencias

- Para un operario, «entrar» es elegir su nombre: no hay autenticación real en
  el kiosco. La protección es física (la PC de planta) y de red (Gunicorn en
  127.0.0.1, el kiosco no se publica).
- Los operarios dejan de cargarse en el admin de operarios (queda de solo
  lectura): se crean como usuarios con rol Operario.
- Cambiar un juego de permisos es un cambio de código revisado y testeado, no
  una edición en el admin.
