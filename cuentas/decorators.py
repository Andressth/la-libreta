"""Control de acceso por rol."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def tendero_requerido(vista):
    """Solo tenderos con tienda. Agrega `request.tienda` para filtrar los datos."""

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        usuario = request.user
        if not usuario.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if usuario.es_admin:
            messages.info(request, "Esa sección es para tenderos. Como administrador ves las estadísticas generales.")
            return redirect("cuentas:estadisticas")
        tienda = getattr(usuario, "tienda", None)
        if tienda is None:
            raise PermissionDenied("Tu usuario no tiene una tienda asociada.")
        request.tienda = tienda
        return vista(request, *args, **kwargs)

    return envoltura


def admin_requerido(vista):
    """Solo usuarios con rol administrador."""

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.es_admin:
            raise PermissionDenied("Esta sección es solo para administradores.")
        return vista(request, *args, **kwargs)

    return envoltura
