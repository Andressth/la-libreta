"""Pruebas de las reglas de negocio y de los permisos por rol.

Ejecutar con:  python manage.py test
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Usuario
from libreta.models import Abono, Cliente, DetalleFiado, Fiado, Producto, Tienda


class BaseLibreta(TestCase):
    def setUp(self):
        self.tendero = Usuario.objects.create_user("rosa", password="clave-segura-123", first_name="Rosa")
        self.tienda = Tienda.objects.create(tendero=self.tendero, nombre="Tienda Rosa", direccion="Calle 1",
                                            municipio="Piedecuesta", telefono="3170000000")
        self.cliente = Cliente.objects.create(tienda=self.tienda, nombre="Carlos Pérez", cedula="1098765432",
                                              telefono="3104567890", limite_credito=Decimal("50000"))
        self.arroz = Producto.objects.create(tienda=self.tienda, nombre="Arroz", precio=Decimal("2800"))

    def fiar(self, cliente, valor, dias=0):
        f = Fiado.objects.create(cliente=cliente, fecha=timezone.now() - timedelta(days=dias))
        DetalleFiado.objects.create(fiado=f, descripcion="Varios", cantidad=1, precio_unitario=valor)
        f.recalcular_total()
        return f

    def datos_fiado(self, cliente, producto_id, cantidad, confirmar=False):
        datos = {
            "cliente": cliente.pk, "nota": "",
            "detalles-TOTAL_FORMS": "1", "detalles-INITIAL_FORMS": "0",
            "detalles-MIN_NUM_FORMS": "1", "detalles-MAX_NUM_FORMS": "1000",
            "detalles-0-producto": producto_id, "detalles-0-descripcion": "",
            "detalles-0-cantidad": str(cantidad), "detalles-0-precio_unitario": "",
        }
        if confirmar:
            datos["confirmar_limite"] = "on"
        return datos


class SaldoTests(BaseLibreta):
    def test_saldo_es_fiados_menos_abonos(self):
        self.fiar(self.cliente, 30000)
        self.fiar(self.cliente, 12300)
        Abono.objects.create(cliente=self.cliente, valor=Decimal("20000"))
        self.assertEqual(self.cliente.calcular_saldo(), Decimal("22300"))
        anotado = Cliente.objects.con_saldo().get(pk=self.cliente.pk)
        self.assertEqual(anotado.saldo, Decimal("22300"))

    def test_atrasado_si_no_abona_en_30_dias(self):
        self.fiar(self.cliente, 10000, dias=40)
        self.assertIn(self.cliente, Cliente.objects.atrasados())
        Abono.objects.create(cliente=self.cliente, valor=Decimal("1000"))
        self.assertNotIn(self.cliente, Cliente.objects.atrasados())

    def test_subtotal_y_total_del_fiado(self):
        f = Fiado.objects.create(cliente=self.cliente)
        DetalleFiado.objects.create(fiado=f, producto=self.arroz, cantidad=3, precio_unitario=self.arroz.precio)
        f.recalcular_total()
        self.assertEqual(f.total, Decimal("8400"))
        self.assertEqual(f.detalles.first().descripcion, "Arroz")


class FiadoVistaTests(BaseLibreta):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.tendero)

    def test_registrar_fiado_con_producto(self):
        r = self.client.post(reverse("libreta:fiado_nuevo"), self.datos_fiado(self.cliente, self.arroz.pk, 2))
        self.assertRedirects(r, self.cliente.get_absolute_url())
        self.assertEqual(self.cliente.calcular_saldo(), Decimal("5600"))

    def test_fiado_sobre_el_limite_pide_confirmacion(self):
        r = self.client.post(reverse("libreta:fiado_nuevo"), self.datos_fiado(self.cliente, self.arroz.pk, 20))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Confirma si quieres continuar")
        self.assertEqual(Fiado.objects.count(), 0)
        r = self.client.post(reverse("libreta:fiado_nuevo"), self.datos_fiado(self.cliente, self.arroz.pk, 20, True))
        self.assertEqual(Fiado.objects.count(), 1)
        self.assertEqual(self.cliente.calcular_saldo(), Decimal("56000"))

    def test_abono_no_puede_superar_el_saldo(self):
        self.fiar(self.cliente, 10000)
        datos = {"cliente": self.cliente.pk, "valor": "15000", "metodo": "efectivo", "nota": ""}
        r = self.client.post(reverse("libreta:abono_nuevo"), datos)
        self.assertContains(r, "no puede ser mayor que el saldo")
        self.assertEqual(Abono.objects.count(), 0)
        datos["valor"] = "10000"
        self.client.post(reverse("libreta:abono_nuevo"), datos)
        self.assertEqual(self.cliente.calcular_saldo(), Decimal("0"))

    def test_qr_es_una_imagen_svg(self):
        r = self.client.get(reverse("libreta:cliente_qr", args=[self.cliente.pk]))
        self.assertEqual(r["Content-Type"], "image/svg+xml")


class PermisosTests(BaseLibreta):
    def setUp(self):
        super().setUp()
        otro = Usuario.objects.create_user("luis", password="clave-segura-123")
        otra_tienda = Tienda.objects.create(tendero=otro, nombre="Otra", direccion="x", municipio="y", telefono="1")
        self.otro_tendero = otro
        self.cliente_ajeno = Cliente.objects.create(tienda=otra_tienda, nombre="Ajeno", cedula="1", telefono="2")
        self.admin = Usuario.objects.create_superuser("admin", "a@a.co", "clave-segura-123")

    def test_visitante_es_enviado_a_ingresar(self):
        r = self.client.get(reverse("libreta:panel"))
        self.assertRedirects(r, reverse("cuentas:ingresar") + "?next=" + reverse("libreta:panel"))

    def test_tendero_no_ve_clientes_de_otra_tienda(self):
        self.client.force_login(self.tendero)
        r = self.client.get(reverse("libreta:cliente_detalle", args=[self.cliente_ajeno.pk]))
        self.assertEqual(r.status_code, 404)
        r = self.client.get(reverse("libreta:clientes"))
        self.assertNotContains(r, "Ajeno")

    def test_tendero_no_entra_a_estadisticas(self):
        self.client.force_login(self.tendero)
        self.assertEqual(self.client.get(reverse("cuentas:estadisticas")).status_code, 403)

    def test_admin_ve_estadisticas_y_no_el_panel_del_tendero(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("cuentas:estadisticas")).status_code, 200)
        self.assertRedirects(self.client.get(reverse("libreta:panel")), reverse("cuentas:estadisticas"))

    def test_admin_no_puede_modificar_fiados_en_el_admin(self):
        f = self.fiar(self.cliente, 1000)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin:libreta_fiado_change", args=[f.pk])).status_code, 200)
        r = self.client.post(reverse("admin:libreta_fiado_delete", args=[f.pk]), {"post": "yes"})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Fiado.objects.filter(pk=f.pk).exists())

    def test_tendero_no_entra_al_admin_de_django(self):
        self.client.force_login(self.tendero)
        r = self.client.get(reverse("admin:index"))
        self.assertEqual(r.status_code, 302)


class ConsultaClienteTests(BaseLibreta):
    def url(self):
        return reverse("libreta:consulta", args=[self.cliente.codigo_acceso])

    def test_pide_pin_y_muestra_saldo(self):
        self.fiar(self.cliente, 12300)
        r = self.client.get(self.url())
        self.assertContains(r, "últimos 4 dígitos")
        self.assertNotContains(r, "$12.300")
        r = self.client.post(self.url(), {"pin": "0000"})
        self.assertContains(r, "no coinciden")
        r = self.client.post(self.url(), {"pin": "5432"}, follow=True)
        self.assertContains(r, "$12.300")

    def test_bloqueo_despues_de_5_intentos(self):
        for _ in range(5):
            r = self.client.post(self.url(), {"pin": "1111"})
        self.assertContains(r, "demasiados intentos")
        r = self.client.post(self.url(), {"pin": "5432"})
        self.assertNotContains(r, "Tu saldo pendiente")

    def test_codigo_regenerado_invalida_el_anterior(self):
        anterior = self.url()
        self.cliente.regenerar_codigo()
        self.assertEqual(self.client.get(anterior).status_code, 404)

    def test_buscar_codigo_desde_el_home(self):
        r = self.client.get(reverse("libreta:consultar_codigo"), {"codigo": self.cliente.codigo_acceso.lower()})
        self.assertRedirects(r, self.url())


class RegistroTests(TestCase):
    def test_registro_crea_usuario_tendero_y_tienda(self):
        datos = {
            "first_name": "Ana", "last_name": "Ruiz", "email": "ana@correo.co", "username": "anaruiz",
            "password1": "MiTienda.2026", "password2": "MiTienda.2026",
            "nombre_tienda": "Tienda Ana", "direccion": "Calle 5", "municipio": "Girón", "telefono": "3001234567",
        }
        r = self.client.post(reverse("cuentas:registro"), datos)
        self.assertRedirects(r, reverse("libreta:panel"))
        usuario = Usuario.objects.get(username="anaruiz")
        self.assertEqual(usuario.rol, Usuario.Rol.TENDERO)
        self.assertEqual(usuario.tienda.nombre, "Tienda Ana")
