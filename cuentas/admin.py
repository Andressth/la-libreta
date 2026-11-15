from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from .models import Usuario

admin.site.site_header = "Administración de La Libreta"
admin.site.site_title = "La Libreta"
admin.site.index_title = "Tiendas, usuarios y movimientos"


class SoloAdministradoresMixin:
    """Solo los usuarios con rol administrador pueden entrar a este módulo."""

    def _es_admin(self, request):
        return request.user.is_active and getattr(request.user, "es_admin", False)

    def has_module_permission(self, request):
        return self._es_admin(request)

    def has_view_permission(self, request, obj=None):
        return self._es_admin(request)

    def has_add_permission(self, request):
        return self._es_admin(request)

    def has_change_permission(self, request, obj=None):
        return self._es_admin(request)

    def has_delete_permission(self, request, obj=None):
        return self._es_admin(request)


class SoloLecturaMixin(SoloAdministradoresMixin):
    """El administrador puede ver, pero no crear, editar ni borrar."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Usuario)
class UsuarioAdmin(SoloAdministradoresMixin, UserAdmin):
    list_display = ("username", "get_full_name", "email", "rol", "is_active", "date_joined")
    list_filter = ("rol", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    fieldsets = UserAdmin.fieldsets + (("Rol en La Libreta", {"fields": ("rol",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Rol en La Libreta", {"fields": ("rol",)}),)
    actions = ["activar", "desactivar"]

    @admin.display(description="Nombre")
    def get_full_name(self, obj):
        return obj.get_full_name()

    @admin.action(description="Activar las cuentas seleccionadas")
    def activar(self, request, queryset):
        n = queryset.update(is_active=True)
        self.message_user(request, f"{n} cuenta(s) activada(s).", messages.SUCCESS)

    @admin.action(description="Desactivar las cuentas seleccionadas")
    def desactivar(self, request, queryset):
        n = queryset.exclude(pk=request.user.pk).update(is_active=False)
        self.message_user(request, f"{n} cuenta(s) desactivada(s).", messages.SUCCESS)
