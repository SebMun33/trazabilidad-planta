// Kiosco de planta: atajos de teclado, «Deshacer» con cuenta regresiva y
// vuelta automática a «¿Quién sos?» después de un rato sin uso.
(function () {
  "use strict";

  const raiz = document.querySelector(".kiosco");
  if (!raiz) return;

  function activar(elemento) {
    if (!elemento) return false;
    if (elemento.tagName === "A") {
      window.location.href = elemento.href;
    } else {
      elemento.click();
    }
    return true;
  }

  // Números: se acumulan durante un instante (para elegir el 12, escribir 1 y 2).
  let numero = "";
  let temporizador = null;
  function elegirNumero(digito) {
    numero += digito;
    clearTimeout(temporizador);
    const exacto = document.querySelector('[data-numero="' + numero + '"]');
    const hayMas = document.querySelector('[data-numero^="' + numero + '"]:not([data-numero="' + numero + '"])');
    if (exacto && !hayMas) {
      numero = "";
      activar(exacto);
      return;
    }
    temporizador = setTimeout(function () {
      const elegido = document.querySelector('[data-numero="' + numero + '"]');
      numero = "";
      activar(elegido);
    }, 700);
  }

  document.addEventListener("keydown", function (evento) {
    if (evento.ctrlKey || evento.altKey || evento.metaKey) return;
    const enCampo = /^(INPUT|TEXTAREA|SELECT)$/.test(evento.target.tagName);
    if (evento.key === "Escape") {
      if (enCampo) evento.target.blur();
      if (activar(document.querySelector('[data-tecla="Escape"]'))) evento.preventDefault();
      return;
    }
    if (enCampo) return;
    if (/^[0-9]$/.test(evento.key)) {
      evento.preventDefault();
      elegirNumero(evento.key);
      return;
    }
    const tecla = evento.key.length === 1 ? evento.key.toLowerCase() : evento.key;
    if (activar(document.querySelector('[data-tecla="' + tecla + '"]'))) evento.preventDefault();
  });

  // «Deshacer»: muestra los segundos que quedan y se oculta al vencer.
  const deshacer = document.querySelector(".k-deshacer[data-hasta]");
  if (deshacer) {
    const hasta = Number(deshacer.dataset.hasta);
    const restante = deshacer.querySelector(".k-restante");
    const tic = function () {
      const segundos = Math.ceil((hasta - Date.now()) / 1000);
      if (segundos <= 0) {
        deshacer.remove();
        return;
      }
      restante.textContent = "(" + segundos + " s)";
      setTimeout(tic, 500);
    };
    tic();
  }

  // Sin actividad, vuelve a la pantalla de elegir operario.
  const espera = Number(raiz.dataset.inactividad || 0) * 1000;
  const inicio = raiz.dataset.inicio;
  if (espera > 0 && inicio && window.location.pathname !== inicio) {
    let reloj = setTimeout(function () { window.location.href = inicio; }, espera);
    ["keydown", "mousemove", "mousedown", "wheel"].forEach(function (tipo) {
      document.addEventListener(tipo, function () {
        clearTimeout(reloj);
        reloj = setTimeout(function () { window.location.href = inicio; }, espera);
      }, { passive: true });
    });
  }
})();
