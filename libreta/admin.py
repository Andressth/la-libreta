from django.contrib import admin
from django.db.models import Count

from cuentas.admin import SoloAdministradoresMixin, SoloLecturaMixin
from .models import Abono, Cliente, DetalleFiado, Fiado, Producto, Tienda
from .templatetags.pesos import pesos


@admin.register(Tienda)
class TiendaAdmin(SoloAdministradoresMixin, admin.ModelAdmin):
    list_display = ("nombre", "tendero", "municipio", "telefono", "num_clientes", "por_cobrar", "creada_en")
    search_fields = ("nombre", "municipio", "tendero__username", "tendero__first_name")
    list_filter = ("municipio",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n_clientes=Count("clientes"))

    @admin.display(description="Clientes", ordering="n_clientes")
    def num_clientes(self, obj):
        return obj.n_clientes

    @admin.display(description="Por cobrar")
    def por_cobrar(self, obj):
        total = sum(c.saldo for c in obj.clientes.con_deuda())
        return pesos(total)


@admin.register(Cliente)
class ClienteAdmin(SoloLecturaMixin, admin.ModelAdmin):
    list_display = ("nombre", "tienda", "cedula", "telefono", "limite_credito", "activo")
    list_filter = ("tienda", "activo")
    search_fields = ("nombre", "cedula")


@admin.register(Producto)
class ProductoAdmin(SoloLecturaMixin, admin.ModelAdmin):
    list_display = ("nombre", "tienda", "precio", "activo")
    list_filter = ("tienda", "activo")
    search_fields = ("nombre",)


class DetalleFiadoInline(admin.TabularInline):
    model = DetalleFiado
    extra = 0
    readonly_fields = ("producto", "descripcion", "cantidad", "precio_unitario", "subtotal")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Fiado)
class FiadoAdmin(SoloLecturaMixin, admin.ModelAdmin):
    list_display = ("id", "cliente", "tienda", "fecha", "total")
    list_filter = ("cliente__tienda",)
    date_hierarchy = "fecha"
    inlines = [DetalleFiadoInline]

    @admin.display(description="Tienda")
    def tienda(self, obj):
        return obj.cliente.tienda


@admin.register(Abono)
class AbonoAdmin(SoloLecturaMixin, admin.ModelAdmin):
    list_display = ("id", "cliente", "fecha", "valor", "metodo")
    list_filter = ("metodo", "cliente__tienda")
    date_hierarchy = "fecha"
