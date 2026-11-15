from django.urls import path

from . import views

app_name = "libreta"

urlpatterns = [
    # Tendero
    path("panel/", views.panel, name="panel"),
    path("clientes/", views.clientes_lista, name="clientes"),
    path("clientes/nuevo/", views.cliente_nuevo, name="cliente_nuevo"),
    path("clientes/<int:pk>/", views.cliente_detalle, name="cliente_detalle"),
    path("clientes/<int:pk>/editar/", views.cliente_editar, name="cliente_editar"),
    path("clientes/<int:pk>/eliminar/", views.cliente_eliminar, name="cliente_eliminar"),
    path("clientes/<int:pk>/nuevo-codigo/", views.cliente_regenerar_codigo, name="cliente_regenerar_codigo"),
    path("clientes/<int:pk>/qr.svg", views.cliente_qr, name="cliente_qr"),
    path("productos/", views.productos_lista, name="productos"),
    path("productos/nuevo/", views.producto_nuevo, name="producto_nuevo"),
    path("productos/<int:pk>/editar/", views.producto_editar, name="producto_editar"),
    path("productos/<int:pk>/eliminar/", views.producto_eliminar, name="producto_eliminar"),
    path("fiados/", views.fiados_lista, name="fiados"),
    path("fiados/nuevo/", views.fiado_nuevo, name="fiado_nuevo"),
    path("fiados/<int:pk>/", views.fiado_detalle, name="fiado_detalle"),
    path("fiados/<int:pk>/eliminar/", views.fiado_eliminar, name="fiado_eliminar"),
    path("abonos/", views.abonos_lista, name="abonos"),
    path("abonos/nuevo/", views.abono_nuevo, name="abono_nuevo"),
    path("abonos/<int:pk>/eliminar/", views.abono_eliminar, name="abono_eliminar"),
    path("mi-tienda/", views.mi_tienda, name="mi_tienda"),
    # Cliente (sin cuenta)
    path("consultar/", views.consultar_codigo, name="consultar_codigo"),
    path("c/<str:codigo>/", views.consulta, name="consulta"),
    path("c/<str:codigo>/salir/", views.consulta_salir, name="consulta_salir"),
]
