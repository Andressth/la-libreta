from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Count, Max, Sum
from django.shortcuts import redirect, render

from libreta.models import Abono, Cliente, Fiado, Tienda
from .decorators import admin_requerido
from .forms import IngresarForm, RegistroTenderoForm
from .models import Usuario


def registro(request):
    """El visitante se registra como tendero y crea su tienda."""
    if request.user.is_authenticated:
        return redirect("cuentas:inicio_segun_rol")
    form = RegistroTenderoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        login(request, usuario)
        messages.success(request, f"¡Bienvenido! Tu tienda {usuario.tienda.nombre} ya está lista. Empieza registrando a tus clientes.")
        return redirect("libreta:panel")
    return render(request, "cuentas/registro.html", {"form": form})


class IngresarView(LoginView):
    template_name = "cuentas/ingresar.html"
    authentication_form = IngresarForm
    redirect_authenticated_user = True


@login_required
def inicio_segun_rol(request):
    """Después de iniciar sesión, cada rol va a su pantalla principal."""
    if request.user.es_admin:
        return redirect("cuentas:estadisticas")
    return redirect("libreta:panel")


@admin_requerido
def estadisticas(request):
    """Estadísticas generales de la plataforma (solo administrador)."""
    total_fiado = Fiado.objects.aggregate(t=Sum("total"))["t"] or 0
    total_abonado = Abono.objects.aggregate(t=Sum("valor"))["t"] or 0

    tiendas = []
    for tienda in Tienda.objects.select_related("tendero").annotate(
        n_clientes=Count("clientes", distinct=True),
        ultimo_fiado=Max("clientes__fiados__fecha"),
    ):
        por_cobrar = tienda.clientes.con_deuda().aggregate(t=Sum("saldo"))["t"] or 0
        tiendas.append({"tienda": tienda, "por_cobrar": por_cobrar})
    tiendas.sort(key=lambda t: t["por_cobrar"], reverse=True)

    contexto = {
        "n_tiendas": len(tiendas),
        "n_tenderos_activos": Usuario.objects.filter(rol=Usuario.Rol.TENDERO, is_active=True).count(),
        "n_tenderos_inactivos": Usuario.objects.filter(rol=Usuario.Rol.TENDERO, is_active=False).count(),
        "n_clientes": Cliente.objects.count(),
        "n_fiados": Fiado.objects.count(),
        "n_abonos": Abono.objects.count(),
        "total_fiado": total_fiado,
        "total_abonado": total_abonado,
        "por_cobrar": total_fiado - total_abonado,
        "tiendas": tiendas,
    }
    return render(request, "cuentas/estadisticas.html", contexto)
