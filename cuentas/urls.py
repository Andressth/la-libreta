from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("registro/", views.registro, name="registro"),
    path("ingresar/", views.IngresarView.as_view(), name="ingresar"),
    path("salir/", LogoutView.as_view(), name="salir"),
    path("inicio/", views.inicio_segun_rol, name="inicio_segun_rol"),
    path("estadisticas/", views.estadisticas, name="estadisticas"),
]
