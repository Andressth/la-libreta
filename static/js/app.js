/* La Libreta - JavaScript del sitio (sin librerías). */

const pesos = (n) => "$" + Math.round(n || 0).toLocaleString("es-CO").replace(/,/g, ".");
const leerJSON = (id) => {
  const el = document.getElementById(id);
  return el ? JSON.parse(el.textContent) : {};
};

/* ---------- Menú lateral en el celular ---------- */
(() => {
  const boton = document.querySelector("[data-abrir-menu]");
  const menu = document.getElementById("menu-lateral");
  const velo = document.querySelector("[data-velo]");
  if (!boton || !menu) return;
  const cambiar = (abrir) => {
    menu.classList.toggle("abierta", abrir);
    velo.hidden = !abrir;
    boton.setAttribute("aria-expanded", abrir);
  };
  boton.addEventListener("click", () => cambiar(!menu.classList.contains("abierta")));
  velo.addEventListener("click", () => cambiar(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") cambiar(false); });
})();

/* ---------- Copiar enlace ---------- */
document.querySelectorAll("[data-copiar]").forEach((boton) => {
  boton.addEventListener("click", async () => {
    const campo = document.querySelector(boton.dataset.copiar);
    try {
      await navigator.clipboard.writeText(campo.value);
    } catch {
      campo.select();
      document.execCommand("copy");
    }
    const texto = boton.textContent;
    boton.textContent = "¡Copiado!";
    setTimeout(() => (boton.textContent = texto), 1800);
  });
});

/* ---------- Confirmación antes de enviar ---------- */
document.querySelectorAll("form[data-confirmar]").forEach((form) => {
  form.addEventListener("submit", (e) => {
    if (!confirm(form.dataset.confirmar)) e.preventDefault();
  });
});

/* ---------- Formulario de fiado ---------- */
(() => {
  const form = document.getElementById("form-fiado");
  if (!form) return;
  const clientes = leerJSON("datos-clientes");
  const productos = leerJSON("datos-productos");
  const filas = [...form.querySelectorAll("[data-fila]")];
  const selCliente = form.querySelector("select[name=cliente]");
  const totalEl = form.querySelector("[data-total]");
  const previa = form.querySelector("[data-vista-previa]");
  const botonAgregar = form.querySelector("[data-agregar-fila]");

  const campo = (fila, nombre) => fila.querySelector(`[name$="-${nombre}"]`);
  const tieneDatos = (fila) =>
    campo(fila, "producto").value || campo(fila, "descripcion").value || campo(fila, "precio_unitario").value ||
    fila.querySelector(".error-campo");

  // Mostrar solo las filas con datos (o la primera); el resto aparece con "Agregar otro producto".
  filas.forEach((fila, i) => (fila.hidden = i > 0 && !tieneDatos(fila)));
  const actualizarBoton = () => (botonAgregar.hidden = !filas.some((f) => f.hidden));
  botonAgregar.addEventListener("click", () => {
    const siguiente = filas.find((f) => f.hidden);
    if (siguiente) {
      siguiente.hidden = false;
      campo(siguiente, "producto").focus();
    }
    actualizarBoton();
  });

  const recalcular = () => {
    let total = 0;
    filas.forEach((fila) => {
      const cantidad = parseInt(campo(fila, "cantidad").value) || 0;
      const precio = parseFloat(campo(fila, "precio_unitario").value) || 0;
      const subtotal = cantidad * precio;
      fila.querySelector("[data-subtotal]").textContent = pesos(subtotal);
      total += subtotal;
    });
    totalEl.textContent = pesos(total);

    const c = clientes[selCliente.value];
    if (!c) {
      previa.textContent = "Escoge un cliente para ver cómo queda su saldo.";
      previa.classList.remove("vista-previa--mal");
      return;
    }
    const nuevo = c.saldo + total;
    const pasa = nuevo > c.limite;
    previa.classList.toggle("vista-previa--mal", pasa);
    previa.innerHTML =
      `Debe ahora <strong>${pesos(c.saldo)}</strong>. Con este fiado quedará en <strong>${pesos(nuevo)}</strong> ` +
      `de ${pesos(c.limite)} de límite.` +
      (pasa ? "<br><strong>Supera su límite de crédito.</strong> Te pediremos confirmar." : "");
  };

  filas.forEach((fila) => {
    campo(fila, "producto").addEventListener("change", (e) => {
      const p = productos[e.target.value];
      const precio = campo(fila, "precio_unitario");
      const desc = campo(fila, "descripcion");
      if (p) {
        precio.value = p.precio;
        desc.value = "";
        desc.placeholder = p.nombre;
      } else {
        precio.value = "";
        desc.placeholder = "Descripción (valor libre)";
        desc.focus();
      }
      recalcular();
    });
    ["cantidad", "precio_unitario"].forEach((n) => campo(fila, n).addEventListener("input", recalcular));
  });
  // Si la página se recargó con productos ya escogidos, mostrar su nombre como ayuda.
  filas.forEach((fila) => {
    const p = productos[campo(fila, "producto").value];
    if (p) campo(fila, "descripcion").placeholder = p.nombre;
  });
  selCliente.addEventListener("change", recalcular);
  actualizarBoton();
  recalcular();
})();

/* ---------- Formulario de abono ---------- */
(() => {
  const form = document.getElementById("form-abono");
  if (!form) return;
  const clientes = leerJSON("datos-clientes");
  const sel = form.querySelector("select[name=cliente]");
  const valor = form.querySelector("input[name=valor]");
  const info = form.querySelector("[data-saldo-cliente]");
  const pagarTodo = form.querySelector("[data-pagar-todo]");

  const mostrar = () => {
    const c = clientes[sel.value];
    pagarTodo.hidden = !c || c.saldo <= 0;
    if (!c) {
      info.textContent = "Escoge un cliente para ver cuánto debe.";
      return;
    }
    const abono = parseFloat(valor.value) || 0;
    info.innerHTML = c.saldo > 0
      ? `Debe <strong>${pesos(c.saldo)}</strong>.` + (abono ? ` Después del abono quedará en <strong>${pesos(Math.max(c.saldo - abono, 0))}</strong>.` : "")
      : "Este cliente no tiene deuda pendiente.";
  };
  pagarTodo.addEventListener("click", () => {
    valor.value = clientes[sel.value].saldo;
    mostrar();
  });
  sel.addEventListener("change", mostrar);
  valor.addEventListener("input", mostrar);
  mostrar();
})();

/* ---------- PIN del cliente: solo números ---------- */
document.querySelectorAll("input.pin").forEach((input) => {
  input.addEventListener("input", () => (input.value = input.value.replace(/\D/g, "").slice(0, 4)));
});
