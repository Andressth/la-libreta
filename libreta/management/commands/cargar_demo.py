"""
Carga datos de prueba para la demostración.

    python manage.py cargar_demo

Crea el administrador, dos tiendas con sus clientes, productos, fiados y abonos.
Las fechas se calculan desde hoy, así los datos siempre se ven recientes.
Si se ejecuta otra vez, borra los datos de prueba anteriores y los vuelve a crear.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cuentas.models import Usuario
from libreta.models import Abono, Cliente, DetalleFiado, Fiado, Producto, Tienda

CLAVE = "Libreta2026"

PRODUCTOS_ROSA = {
    "Arroz 1 lb": 2800, "Aceite 500 ml": 5200, "Huevos x6": 4800, "Leche 1 L": 4200,
    "Pan francés": 1400, "Gaseosa 1.5 L": 5000, "Galletas": 2200, "Café 250 g": 9800,
    "Azúcar 1 lb": 2600, "Panela": 3000, "Lentejas 1 lb": 3900, "Fríjol 1 lb": 5200,
    "Atún en lata": 7200, "Pasta 250 g": 2300, "Jabón en barra": 3400,
    "Papel higiénico x4": 7800, "Avena 1 lb": 3800, "Chocolate": 6500, "Arepas x5": 3500, "Sal 1 lb": 1500,
}
PRODUCTOS_PROGRESO = {
    "Arroz 1 lb": 2900, "Aceite 1 L": 9800, "Huevos x12": 9200, "Leche 1 L": 4300,
    "Pan tajado": 5600, "Café 500 g": 18500,
}
VALORES_LIBRES = ["Mecato", "Recarga de celular", "Bolsa de hielo", "Velas y fósforos"]


class Command(BaseCommand):
    help = "Carga usuarios y datos de prueba para la demostración de La Libreta."

    def handle(self, *args, **options):
        with transaction.atomic():
            Usuario.objects.filter(username__in=["admin", "rosa", "luis"]).delete()
            self.ahora = timezone.localtime()
            self.n_libre = 0
            self.crear_admin()
            self.crear_tienda_rosa()
            self.crear_tienda_progreso()
        self.stdout.write(self.style.SUCCESS("Datos de prueba cargados."))
        self.stdout.write(f"  Administrador:  usuario admin  contraseña {CLAVE}")
        self.stdout.write(f"  Tendera:        usuario rosa   contraseña {CLAVE}  (Tienda Doña Rosa)")
        self.stdout.write(f"  Tendero:        usuario luis   contraseña {CLAVE}  (Autoservicio El Progreso)")
        carlos = Cliente.objects.get(tienda__nombre="Tienda Doña Rosa", cedula="1098765432")
        self.stdout.write(f"  Cliente de ejemplo: Carlos Pérez, código {carlos.codigo_acceso}, PIN 5432")

    # ---------------------------------------------------------------- utilidades
    def fecha(self, dias, hora=10, minuto=0):
        f = (self.ahora - timedelta(days=dias)).replace(hour=hora, minute=minuto, second=0, microsecond=0)
        return min(f, self.ahora - timedelta(minutes=3))

    def fiar(self, cliente, dias, items, objetivo=None, hora=10, minuto=0, nota=""):
        """items: lista de (nombre_producto, cantidad). Si hay objetivo, completa con un valor libre."""
        fiado = Fiado.objects.create(cliente=cliente, fecha=self.fecha(dias, hora, minuto), nota=nota)
        suma = 0
        for nombre, cantidad in items:
            producto = self.productos[nombre]
            DetalleFiado.objects.create(fiado=fiado, producto=producto, cantidad=cantidad,
                                        precio_unitario=producto.precio)
            suma += cantidad * producto.precio
        if objetivo:
            resto = Decimal(objetivo) - suma
            assert resto >= 0, f"Los productos superan el objetivo en {cliente}"
            if resto:
                descripcion = VALORES_LIBRES[self.n_libre % len(VALORES_LIBRES)]
                self.n_libre += 1
                DetalleFiado.objects.create(fiado=fiado, descripcion=descripcion, cantidad=1, precio_unitario=resto)
        fiado.recalcular_total()
        if objetivo:
            assert fiado.total == objetivo
        return fiado

    def abonar(self, cliente, dias, valor, metodo="efectivo", hora=17, minuto=0, nota=""):
        return Abono.objects.create(cliente=cliente, fecha=self.fecha(dias, hora, minuto), valor=valor,
                                    metodo=metodo, nota=nota)

    def cliente(self, tienda, nombre, cedula, telefono, limite, direccion="", activo=True):
        return Cliente.objects.create(tienda=tienda, nombre=nombre, cedula=cedula, telefono=telefono,
                                      limite_credito=limite, direccion=direccion, activo=activo)

    # ---------------------------------------------------------------- datos
    def crear_admin(self):
        Usuario.objects.create_superuser("admin", "admin@lalibreta.test", CLAVE,
                                         first_name="Administrador", last_name="La Libreta")

    def crear_tienda_rosa(self):
        rosa = Usuario.objects.create_user("rosa", "rosa@lalibreta.test", CLAVE,
                                           first_name="Rosa", last_name="Pérez Duarte")
        tienda = Tienda.objects.create(tendero=rosa, nombre="Tienda Doña Rosa", direccion="Calle 8 # 4-21, barrio Centro",
                                       municipio="Piedecuesta", telefono="3176543210")
        self.productos = {n: Producto.objects.create(tienda=tienda, nombre=n, precio=p) for n, p in PRODUCTOS_ROSA.items()}
        Producto.objects.create(tienda=tienda, nombre="Gas cocinol", precio=4500, activo=False)

        c = self.cliente(tienda, "Carlos Pérez", "1098765432", "3104567890", 120000, "Cra 5 # 12-30, barrio Centro")
        c.codigo_acceso = "8F3K2Q"  # código fijo para la demostración
        c.save(update_fields=["codigo_acceso"])
        self.fiar(c, 55, [("Arroz 1 lb", 4), ("Aceite 500 ml", 2), ("Café 250 g", 1), ("Azúcar 1 lb", 3),
                          ("Leche 1 L", 4), ("Papel higiénico x4", 1), ("Huevos x6", 1)], 68600, nota="Mercado del mes")
        self.abonar(c, 24, 30000, "nequi")
        self.fiar(c, 20, [("Gaseosa 1.5 L", 1), ("Galletas", 1)], 7200, hora=19, minuto=10)
        self.fiar(c, 14, [("Arroz 1 lb", 2), ("Aceite 500 ml", 1), ("Huevos x6", 1), ("Leche 1 L", 2),
                          ("Atún en lata", 1), ("Pasta 250 g", 1), ("Gaseosa 1.5 L", 1)], 38500)
        self.abonar(c, 11, 20000)
        self.fiar(c, 6, [("Leche 1 L", 2), ("Pan francés", 1)], 9800, hora=7, minuto=20)
        self.fiar(c, 0, [("Arroz 1 lb", 2), ("Aceite 500 ml", 1)], 12300, hora=10, minuto=42)

        c = self.cliente(tienda, "Luis Hernández", "91234567", "3157778899", 150000, "Calle 10 # 6-14")
        self.fiar(c, 80, [("Café 250 g", 2), ("Papel higiénico x4", 2), ("Aceite 500 ml", 3), ("Arroz 1 lb", 5),
                          ("Atún en lata", 2)], 95000)
        self.abonar(c, 55, 40000)
        self.fiar(c, 40, [("Fríjol 1 lb", 2), ("Chocolate", 2), ("Leche 1 L", 4), ("Panela", 3)], 52000)
        self.fiar(c, 25, [("Huevos x6", 2), ("Arroz 1 lb", 3), ("Lentejas 1 lb", 1)], 30000)
        self.fiar(c, 1, [("Gaseosa 1.5 L", 1), ("Pan francés", 5)], 15000, hora=17, minuto=12)

        c = self.cliente(tienda, "Marta Gómez", "63456789", "3012345678", 80000, "Calle 9 # 3-40")
        self.fiar(c, 45, [("Arroz 1 lb", 5), ("Aceite 500 ml", 2), ("Huevos x6", 2), ("Café 250 g", 1),
                          ("Avena 1 lb", 2)], 61500)
        self.fiar(c, 30, [("Leche 1 L", 2), ("Pan francés", 3), ("Arepas x5", 2)], 23000)
        self.abonar(c, 20, 20000, "daviplata")
        self.fiar(c, 1, [("Lentejas 1 lb", 1), ("Arroz 1 lb", 1)], 8700, hora=18, minuto=30)

        c = self.cliente(tienda, "Jorge Rincón", "13567890", "3209876543", 100000, "Taller La Cumbre, Cra 7")
        self.fiar(c, 90, [("Gaseosa 1.5 L", 3), ("Galletas", 5), ("Atún en lata", 2)], 45000)
        self.abonar(c, 70, 15000)
        self.fiar(c, 60, [("Café 250 g", 1), ("Azúcar 1 lb", 2), ("Pan francés", 4)], 26500)
        self.fiar(c, 4, [("Galletas", 2)], 4500)

        c = self.cliente(tienda, "Ana Suárez", "1095432109", "3114443322", 70000)
        self.fiar(c, 15, [("Arroz 1 lb", 4), ("Aceite 500 ml", 2), ("Huevos x6", 2), ("Leche 1 L", 2),
                          ("Panela", 1)], 52000)
        self.fiar(c, 8, [("Jabón en barra", 2), ("Papel higiénico x4", 1)], 16500)
        self.abonar(c, 0, 20000, "nequi", hora=9, minuto=15)

        c = self.cliente(tienda, "Pedro Villamizar", "1102345678", "3186665544", 50000)
        self.fiar(c, 30, [("Café 250 g", 1), ("Chocolate", 2), ("Arepas x5", 2)], 29900)
        self.fiar(c, 18, [("Atún en lata", 2), ("Pasta 250 g", 2)], 20000)
        self.abonar(c, 3, 10000)

        c = self.cliente(tienda, "Yolanda Castro", "37890123", "3005556677", 90000)
        self.fiar(c, 5, [("Leche 1 L", 2), ("Huevos x6", 1), ("Pan francés", 3), ("Panela", 1)], 22400)

        c = self.cliente(tienda, "Fabio Quintero", "91456321", "3162223344", 60000)
        self.fiar(c, 50, [("Arroz 1 lb", 3), ("Fríjol 1 lb", 2), ("Aceite 500 ml", 1)], 33000)

        c = self.cliente(tienda, "Diana Patiño", "1098001122", "3137778800", 40000)
        self.fiar(c, 2, [("Avena 1 lb", 2), ("Leche 1 L", 1)], 15800)

        c = self.cliente(tienda, "Sandra Rueda", "63987654", "3045551212", 60000)
        self.fiar(c, 40, [("Café 250 g", 1), ("Azúcar 1 lb", 2)], 18000)
        self.abonar(c, 33, 18000, "transferencia")

        self.cliente(tienda, "Hernán Mantilla", "5678901", "3159990011", 50000)

        c = self.cliente(tienda, "Camila Ortiz", "1097555444", "3123334455", 40000, activo=False)
        self.fiar(c, 100, [("Leche 1 L", 2)], 12000)
        self.abonar(c, 90, 12000)

    def crear_tienda_progreso(self):
        luis = Usuario.objects.create_user("luis", "luis@lalibreta.test", CLAVE,
                                           first_name="Luis", last_name="Ardila Gómez")
        tienda = Tienda.objects.create(tendero=luis, nombre="Autoservicio El Progreso", direccion="Carrera 27 # 31-08",
                                       municipio="Floridablanca", telefono="3208887766")
        self.productos = {n: Producto.objects.create(tienda=tienda, nombre=n, precio=p)
                          for n, p in PRODUCTOS_PROGRESO.items()}
        c = self.cliente(tienda, "Martha Silva", "63111222", "3001112233", 100000)
        self.fiar(c, 12, [("Arroz 1 lb", 4), ("Aceite 1 L", 1), ("Café 500 g", 1)], 40000)
        self.abonar(c, 4, 15000, "nequi")
        c = self.cliente(tienda, "Andrés Rojas", "1098222333", "3014445566", 60000)
        self.fiar(c, 38, [("Huevos x12", 2), ("Leche 1 L", 3)], 31600)
        c = self.cliente(tienda, "Lucía Mendoza", "37444555", "3027778899", 50000)
        self.fiar(c, 3, [("Pan tajado", 1), ("Leche 1 L", 2)], 14200)
