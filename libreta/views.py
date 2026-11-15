from datetime import timedelta
from urllib.parse import quote

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from cuentas.decorators import tendero_requerido
from .forms import (AbonoForm, ClienteForm, DetalleFormSet, FiadoForm, PinForm,
                    ProductoForm, TiendaForm, total_de_formset)
from .models import Abono, Cliente, Fiado
from .templatetags.pesos import pesos

POR_PAGINA = 12


def _paginar(request, queryset):
    return Paginator(queryset, POR_PAGINA).get_page(request.GET.get("pagina"))


def _movimientos(cliente):
    """Fiados y abonos en orden cronológico, con el saldo después de cada uno."""
    items = [
        {"tipo": "fiado", "fecha": f.fecha, "detalle": f.resumen() or f.nota, "valor": f.total, "obj": f}
        for f in cliente.fiados.prefetch_related("detalles")
    ] + [
        {"tipo": "abono", "fecha": a.fecha, "detalle": a.get_metodo_display() + (f" · {a.nota}" if a.nota else ""),
         "valor": a.valor, "obj": a}
        for a in cliente.abonos.all()
    ]
    items.sort(key=lambda m: m["fecha"])
    saldo = 0
    for m in items:
        saldo += m["valor"] if m["tipo"] == "fiado" else -m["valor"]
        m["saldo"] = saldo
    items.reverse()  # el más reciente primero
    return items


def _url_consulta(request, cliente):
    return request.build_absolute_uri(reverse("libreta:consulta", args=[cliente.codigo_acceso]))


# ================================================================ panel

@tendero_requerido
def panel(request):
    tienda = request.tienda
    clientes = tienda.clientes.con_saldo()
    con_deuda = clientes.filter(saldo__gt=0)
    inicio_mes = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    abonos_mes = Abono.objects.filter(cliente__tienda=tienda, fecha__gte=inicio_mes)

    fiados = Fiado.objects.filter(cliente__tienda=tienda).select_related("cliente")[:8]
    abonos = Abono.objects.filter(cliente__tienda=tienda).select_related("cliente")[:8]
    recientes = sorted(
        [{"tipo": "fiado", "obj": f, "fecha": f.fecha, "valor": f.total} for f in fiados]
        + [{"tipo": "abono", "obj": a, "fecha": a.fecha, "valor": a.valor} for a in abonos],
        key=lambda m: m["fecha"], reverse=True,
    )[:7]

    contexto = {
        "total_por_cobrar": con_deuda.aggregate(t=Sum("saldo"))["t"] or 0,
        "n_con_deuda": con_deuda.count(),
        "n_clientes": clientes.filter(activo=True).count(),
        "abonos_mes_total": abonos_mes.aggregate(t=Sum("valor"))["t"] or 0,
        "abonos_mes_n": abonos_mes.count(),
        "n_atrasados": tienda.clientes.atrasados().count(),
        "mayores_deudas": con_deuda.order_by("-saldo")[:6],
        "recientes": recientes,
        "hoy": timezone.localtime(),
    }
    return render(request, "libreta/panel.html", contexto)


# ================================================================ clientes

FILTROS_CLIENTES = {
    "todos": ("Todos", lambda qs: qs.con_saldo().filter(activo=True)),
    "con_deuda": ("Con deuda", lambda qs: qs.con_deuda().filter(activo=True)),
    "atrasados": ("Atrasados", lambda qs: qs.atrasados().filter(activo=True)),
    "sobre_limite": ("Sobre el límite", lambda qs: qs.sobre_limite().filter(activo=True)),
    "archivados": ("Archivados", lambda qs: qs.con_saldo().filter(activo=False)),
}


@tendero_requerido
def clientes_lista(request):
    filtro = request.GET.get("filtro", "todos")
    if filtro not in FILTROS_CLIENTES:
        filtro = "todos"
    q = request.GET.get("q", "").strip()
    orden = request.GET.get("orden", "nombre")

    clientes = FILTROS_CLIENTES[filtro][1](request.tienda.clientes.all())
    if q:
        clientes = clientes.filter(Q(nombre__icontains=q) | Q(cedula__icontains=q) | Q(telefono__icontains=q))
    clientes = clientes.order_by("-saldo", "nombre") if orden == "saldo" else clientes.order_by("nombre")

    contexto = {
        "pagina": _paginar(request, clientes),
        "filtros": [(clave, texto) for clave, (texto, _) in FILTROS_CLIENTES.items()],
        "filtro": filtro, "q": q, "orden": orden,
    }
    return render(request, "libreta/clientes_lista.html", contexto)


@tendero_requerido
def cliente_nuevo(request):
    form = ClienteForm(request.POST or None, tienda=request.tienda)
    if request.method == "POST" and form.is_valid():
        cliente = form.save()
        messages.success(request, f"Cliente {cliente.nombre} registrado.")
        return redirect(cliente)
    return render(request, "libreta/form.html", {
        "form": form, "titulo": "Nuevo cliente", "volver": reverse("libreta:clientes"), "seccion": "clientes",
    })


@tendero_requerido
def cliente_editar(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk, tienda=request.tienda)
    form = ClienteForm(request.POST or None, instance=cliente, tienda=request.tienda)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Datos del cliente actualizados.")
        return redirect(cliente)
    return render(request, "libreta/form.html", {
        "form": form, "titulo": f"Editar a {cliente.nombre}", "volver": cliente.get_absolute_url(), "seccion": "clientes",
    })


@tendero_requerido
def cliente_detalle(request, pk):
    """Estado de cuenta: saldo, límite, historial y opciones para compartir."""
    cliente = get_object_or_404(request.tienda.clientes.con_saldo(), pk=pk)
    movimientos = _movimientos(cliente)
    tipo = request.GET.get("tipo", "todos")
    if tipo in ("fiado", "abono"):
        movimientos = [m for m in movimientos if m["tipo"] == tipo]

    url = _url_consulta(request, cliente)
    nombre_corto = cliente.nombre.split()[0]
    mensaje = (f"Hola {nombre_corto}, le saluda {request.tienda.nombre}. "
               f"Su saldo pendiente es de {pesos(cliente.saldo)}. Puede ver el detalle aquí: {url}")
    contexto = {
        "cliente": cliente,
        "movimientos": movimientos,
        "tipo": tipo,
        "ultimo_abono_obj": cliente.abonos.first(),
        "url_consulta": url,
        "mensaje_whatsapp": mensaje,
        "enlace_whatsapp": f"https://wa.me/{cliente.telefono_whatsapp}?text={quote(mensaje)}",
    }
    return render(request, "libreta/cliente_detalle.html", contexto)


@tendero_requerido
def cliente_eliminar(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk, tienda=request.tienda)
    if request.method == "POST":
        nombre = cliente.nombre
        cliente.delete()
        messages.success(request, f"Se eliminó a {nombre} y todo su historial.")
        return redirect("libreta:clientes")
    return render(request, "libreta/confirmar_eliminar.html", {
        "titulo": f"¿Eliminar a {cliente.nombre}?",
        "aviso": "Se borrarán también todos sus fiados y abonos. Si solo quieres ocultarlo, "
                 "edítalo y desmarca «activo» para archivarlo.",
        "volver": cliente.get_absolute_url(), "seccion": "clientes",
    })


@tendero_requerido
@require_POST
def cliente_regenerar_codigo(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk, tienda=request.tienda)
    cliente.regenerar_codigo()
    messages.success(request, f"Nuevo código de consulta: {cliente.codigo_acceso}. El enlace anterior ya no funciona.")
    return redirect(cliente)


@tendero_requerido
def cliente_qr(request, pk):
    """Imagen SVG del código QR con el enlace de consulta del cliente."""
    cliente = get_object_or_404(Cliente, pk=pk, tienda=request.tienda)
    imagen = qrcode.make(_url_consulta(request, cliente), image_factory=qrcode.image.svg.SvgPathImage,
                         box_size=12, border=2)
    respuesta = HttpResponse(imagen.to_string(), content_type="image/svg+xml")
    if request.GET.get("descargar"):
        respuesta["Content-Disposition"] = f'attachment; filename="qr-{cliente.codigo_acceso}.svg"'
    return respuesta


# ================================================================ productos

@tendero_requerido
def productos_lista(request):
    q = request.GET.get("q", "").strip()
    productos = request.tienda.productos.all()
    if q:
        productos = productos.filter(nombre__icontains=q)
    return render(request, "libreta/productos_lista.html", {"pagina": _paginar(request, productos), "q": q})


@tendero_requerido
def producto_nuevo(request):
    form = ProductoForm(request.POST or None, tienda=request.tienda)
    if request.method == "POST" and form.is_valid():
        producto = form.save()
        messages.success(request, f"Producto {producto.nombre} agregado.")
        return redirect("libreta:productos")
    return render(request, "libreta/form.html", {
        "form": form, "titulo": "Nuevo producto", "volver": reverse("libreta:productos"), "seccion": "productos",
    })


@tendero_requerido
def producto_editar(request, pk):
    producto = get_object_or_404(request.tienda.productos, pk=pk)
    form = ProductoForm(request.POST or None, instance=producto, tienda=request.tienda)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Producto actualizado.")
        return redirect("libreta:productos")
    return render(request, "libreta/form.html", {
        "form": form, "titulo": f"Editar {producto.nombre}", "volver": reverse("libreta:productos"), "seccion": "productos",
    })


@tendero_requerido
def producto_eliminar(request, pk):
    producto = get_object_or_404(request.tienda.productos, pk=pk)
    if request.method == "POST":
        producto.delete()
        messages.success(request, f"Se eliminó {producto.nombre}. Los fiados anteriores conservan su descripción.")
        return redirect("libreta:productos")
    return render(request, "libreta/confirmar_eliminar.html", {
        "titulo": f"¿Eliminar {producto.nombre}?",
        "aviso": "Los fiados donde aparece no cambian. Si solo quieres que no salga al fiar, desactívalo.",
        "volver": reverse("libreta:productos"), "seccion": "productos",
    })


# ================================================================ fiados

@tendero_requerido
def fiados_lista(request):
    q = request.GET.get("q", "").strip()
    fiados = Fiado.objects.filter(cliente__tienda=request.tienda).select_related("cliente").prefetch_related("detalles")
    if q:
        fiados = fiados.filter(cliente__nombre__icontains=q)
    return render(request, "libreta/fiados_lista.html", {"pagina": _paginar(request, fiados), "q": q})


@tendero_requerido
def fiado_nuevo(request):
    tienda = request.tienda
    inicial = {"cliente": request.GET.get("cliente")} if request.GET.get("cliente") else None
    form = FiadoForm(request.POST or None, initial=inicial, tienda=tienda)
    formset = DetalleFormSet(request.POST or None, instance=Fiado(), prefix="detalles",
                             form_kwargs={"tienda": tienda})
    requiere_confirmacion = False

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        cliente = form.cleaned_data["cliente"]
        total = total_de_formset(formset)
        saldo_nuevo = cliente.calcular_saldo() + total
        if saldo_nuevo > cliente.limite_credito and not form.cleaned_data["confirmar_limite"]:
            requiere_confirmacion = True
            messages.warning(request, f"Con este fiado {cliente.nombre} quedaría debiendo {pesos(saldo_nuevo)} "
                                      f"y su límite es {pesos(cliente.limite_credito)}. Confirma si quieres continuar.")
        else:
            with transaction.atomic():
                fiado = form.save()
                formset.instance = fiado
                formset.save()
                fiado.recalcular_total()
            messages.success(request, f"Fiado de {pesos(fiado.total)} registrado a {cliente.nombre}.")
            return redirect(cliente)

    clientes = tienda.clientes.con_saldo().filter(activo=True)
    contexto = {
        "form": form, "formset": formset, "requiere_confirmacion": requiere_confirmacion,
        "datos_clientes": {str(c.pk): {"saldo": int(c.saldo), "limite": int(c.limite_credito)} for c in clientes},
        "datos_productos": {str(p.pk): {"precio": int(p.precio), "nombre": p.nombre}
                            for p in tienda.productos.filter(activo=True)},
    }
    return render(request, "libreta/fiado_form.html", contexto)


@tendero_requerido
def fiado_detalle(request, pk):
    fiado = get_object_or_404(Fiado.objects.select_related("cliente"), pk=pk, cliente__tienda=request.tienda)
    return render(request, "libreta/fiado_detalle.html", {"fiado": fiado, "detalles": fiado.detalles.all()})


@tendero_requerido
def fiado_eliminar(request, pk):
    fiado = get_object_or_404(Fiado, pk=pk, cliente__tienda=request.tienda)
    cliente = fiado.cliente
    if request.method == "POST":
        fiado.delete()
        messages.success(request, f"Se eliminó el fiado de {pesos(fiado.total)}. El saldo de {cliente.nombre} se recalculó.")
        return redirect(cliente)
    return render(request, "libreta/confirmar_eliminar.html", {
        "titulo": f"¿Eliminar el fiado de {pesos(fiado.total)}?",
        "aviso": f"Úsalo solo si se registró por error. El saldo de {cliente.nombre} bajará en {pesos(fiado.total)}.",
        "volver": reverse("libreta:fiado_detalle", args=[fiado.pk]), "seccion": "fiados",
    })


# ================================================================ abonos

@tendero_requerido
def abonos_lista(request):
    q = request.GET.get("q", "").strip()
    metodo = request.GET.get("metodo", "")
    abonos = Abono.objects.filter(cliente__tienda=request.tienda).select_related("cliente")
    if q:
        abonos = abonos.filter(cliente__nombre__icontains=q)
    if metodo in Abono.Metodo.values:
        abonos = abonos.filter(metodo=metodo)
    return render(request, "libreta/abonos_lista.html", {
        "pagina": _paginar(request, abonos), "q": q, "metodo": metodo, "metodos": Abono.Metodo.choices,
    })


@tendero_requerido
def abono_nuevo(request):
    tienda = request.tienda
    inicial = {"cliente": request.GET.get("cliente")} if request.GET.get("cliente") else None
    form = AbonoForm(request.POST or None, initial=inicial, tienda=tienda)
    if request.method == "POST" and form.is_valid():
        abono = form.save()
        saldo = abono.cliente.calcular_saldo()
        texto = "¡Quedó a paz y salvo!" if saldo == 0 else f"Ahora debe {pesos(saldo)}."
        messages.success(request, f"Abono de {pesos(abono.valor)} registrado. {texto}")
        return redirect(abono.cliente)
    clientes = tienda.clientes.con_saldo().filter(activo=True)
    return render(request, "libreta/abono_form.html", {
        "form": form,
        "datos_clientes": {str(c.pk): {"saldo": int(c.saldo), "limite": int(c.limite_credito)} for c in clientes},
    })


@tendero_requerido
def abono_eliminar(request, pk):
    abono = get_object_or_404(Abono, pk=pk, cliente__tienda=request.tienda)
    cliente = abono.cliente
    if request.method == "POST":
        abono.delete()
        messages.success(request, f"Se eliminó el abono de {pesos(abono.valor)}.")
        return redirect(cliente)
    return render(request, "libreta/confirmar_eliminar.html", {
        "titulo": f"¿Eliminar el abono de {pesos(abono.valor)}?",
        "aviso": f"Úsalo solo si se registró por error. El saldo de {cliente.nombre} subirá en {pesos(abono.valor)}.",
        "volver": cliente.get_absolute_url(), "seccion": "abonos",
    })


# ================================================================ mi tienda

@tendero_requerido
def mi_tienda(request):
    form = TiendaForm(request.POST or None, instance=request.tienda)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Datos de la tienda actualizados.")
        return redirect("libreta:mi_tienda")
    return render(request, "libreta/form.html", {
        "form": form, "titulo": "Mi tienda", "volver": reverse("libreta:panel"), "seccion": "tienda",
        "subtitulo": "Estos datos los ve el cliente cuando consulta su cuenta.",
    })


# ================================================================ consulta pública del cliente

MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 10


def consultar_codigo(request):
    """Formulario del Home: el cliente escribe su código."""
    codigo = request.GET.get("codigo", "").strip().upper()
    if codigo and Cliente.objects.filter(codigo_acceso=codigo, activo=True).exists():
        return redirect("libreta:consulta", codigo=codigo)
    messages.error(request, "No encontramos ese código. Revísalo o pídeselo de nuevo al tendero.")
    return redirect(reverse("core:home") + "#consultar")


def consulta(request, codigo):
    """El cliente ve su saldo sin cuenta: enlace/QR + últimos 4 dígitos de la cédula."""
    cliente = get_object_or_404(Cliente.objects.con_saldo().select_related("tienda"),
                                codigo_acceso=codigo.upper(), activo=True)
    clave_ok = f"consulta_ok_{cliente.codigo_acceso}"
    clave_intentos = f"consulta_intentos_{cliente.codigo_acceso}"
    clave_bloqueo = f"consulta_bloqueo_{cliente.codigo_acceso}"

    if request.session.get(clave_ok):
        movimientos = _movimientos(cliente)
        ver_todo = request.GET.get("todo") == "1"
        return render(request, "libreta/consulta_cuenta.html", {
            "cliente": cliente, "tienda": cliente.tienda,
            "movimientos": movimientos if ver_todo else movimientos[:6],
            "hay_mas": len(movimientos) > 6 and not ver_todo,
            "ultimo_abono_obj": cliente.abonos.first(),
        })

    bloqueado_hasta = request.session.get(clave_bloqueo)
    ahora = timezone.now().timestamp()
    bloqueado = bool(bloqueado_hasta and bloqueado_hasta > ahora)
    form = PinForm(request.POST or None)
    if request.method == "POST" and not bloqueado and form.is_valid():
        if cliente.pin_valido(form.cleaned_data["pin"]):
            request.session[clave_ok] = True
            request.session.pop(clave_intentos, None)
            return redirect("libreta:consulta", codigo=cliente.codigo_acceso)
        intentos = request.session.get(clave_intentos, 0) + 1
        request.session[clave_intentos] = intentos
        if intentos >= MAX_INTENTOS:
            request.session[clave_bloqueo] = (timezone.now() + timedelta(minutes=MINUTOS_BLOQUEO)).timestamp()
            request.session[clave_intentos] = 0
            bloqueado = True
        else:
            form.add_error("pin", f"Esos dígitos no coinciden. Te quedan {MAX_INTENTOS - intentos} intentos.")
    return render(request, "libreta/consulta_pin.html", {
        "cliente": cliente, "tienda": cliente.tienda, "form": form,
        "bloqueado": bloqueado, "minutos_bloqueo": MINUTOS_BLOQUEO,
    })


@require_POST
def consulta_salir(request, codigo):
    request.session.pop(f"consulta_ok_{codigo.upper()}", None)
    return redirect("libreta:consulta", codigo=codigo.upper())
