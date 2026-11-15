import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import DecimalField, F, Q, Subquery, OuterRef, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

DINERO = {"max_digits": 12, "decimal_places": 0}  # pesos colombianos, sin centavos
CERO = Value(Decimal("0"), output_field=DecimalField(**DINERO))
DIAS_ATRASO = 30
ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I para evitar confusiones

solo_numeros = RegexValidator(r"^\d+$", "Escribe solo números, sin puntos ni espacios.")


def generar_codigo():
    """Código corto y único con el que el cliente consulta su cuenta."""
    while True:
        codigo = "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(6))
        if not Cliente.objects.filter(codigo_acceso=codigo).exists():
            return codigo


class Tienda(models.Model):
    tendero = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tienda"
    )
    nombre = models.CharField(max_length=100)
    direccion = models.CharField("dirección", max_length=150)
    municipio = models.CharField(max_length=80)
    telefono = models.CharField("teléfono", max_length=15, validators=[solo_numeros])
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ClienteQuerySet(models.QuerySet):
    """Consultas reutilizables. El saldo NO se guarda: se calcula."""

    def con_saldo(self):
        total_fiado = (
            Fiado.objects.filter(cliente=OuterRef("pk"))
            .values("cliente").annotate(t=Sum("total")).values("t")
        )
        total_abonado = (
            Abono.objects.filter(cliente=OuterRef("pk"))
            .values("cliente").annotate(t=Sum("valor")).values("t")
        )
        ultimo_abono = Abono.objects.filter(cliente=OuterRef("pk")).order_by("-fecha").values("fecha")[:1]
        primer_fiado = Fiado.objects.filter(cliente=OuterRef("pk")).order_by("fecha").values("fecha")[:1]
        return self.annotate(
            total_fiado=Coalesce(Subquery(total_fiado), CERO),
            total_abonado=Coalesce(Subquery(total_abonado), CERO),
            ultimo_abono=Subquery(ultimo_abono),
            primer_fiado=Subquery(primer_fiado),
        ).annotate(saldo=F("total_fiado") - F("total_abonado"))

    def con_deuda(self):
        return self.con_saldo().filter(saldo__gt=0)

    def atrasados(self, dias=DIAS_ATRASO):
        """Con deuda y sin abonar en los últimos `dias` días."""
        corte = timezone.now() - timedelta(days=dias)
        return self.con_deuda().filter(
            Q(ultimo_abono__lt=corte) | Q(ultimo_abono__isnull=True, primer_fiado__lt=corte)
        )

    def sobre_limite(self):
        return self.con_saldo().filter(saldo__gt=F("limite_credito"))


class Cliente(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name="clientes")
    nombre = models.CharField(max_length=100)
    cedula = models.CharField("cédula", max_length=15, validators=[solo_numeros])
    telefono = models.CharField("teléfono", max_length=15, validators=[solo_numeros])
    direccion = models.CharField("dirección", max_length=150, blank=True)
    limite_credito = models.DecimalField(
        "límite de crédito", **DINERO, default=Decimal("100000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    codigo_acceso = models.CharField(max_length=8, unique=True, default=generar_codigo, editable=False)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = ClienteQuerySet.as_manager()

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(fields=["tienda", "cedula"], name="cedula_unica_por_tienda"),
        ]

    def __str__(self):
        return self.nombre

    def get_absolute_url(self):
        return reverse("libreta:cliente_detalle", args=[self.pk])

    # ---- saldo y estado ----
    def calcular_saldo(self):
        """Saldo = suma de fiados - suma de abonos (consulta directa)."""
        fiado = self.fiados.aggregate(t=Sum("total"))["t"] or Decimal("0")
        abonado = self.abonos.aggregate(t=Sum("valor"))["t"] or Decimal("0")
        return fiado - abonado

    def _saldo(self):
        # Usa el valor anotado por con_saldo() si existe; si no, lo calcula.
        return getattr(self, "saldo", None) if hasattr(self, "saldo") else self.calcular_saldo()

    @property
    def disponible(self):
        return max(self.limite_credito - self._saldo(), Decimal("0"))

    @property
    def porcentaje_usado(self):
        if not self.limite_credito:
            return 100 if self._saldo() > 0 else 0
        return int(min(100, max(0, self._saldo() * 100 / self.limite_credito)))

    @property
    def esta_atrasado(self):
        saldo = self._saldo()
        if saldo <= 0:
            return False
        corte = timezone.now() - timedelta(days=DIAS_ATRASO)
        ultimo = getattr(self, "ultimo_abono", None)
        if ultimo is None and not hasattr(self, "ultimo_abono"):
            ultimo = self.abonos.order_by("-fecha").values_list("fecha", flat=True).first()
        if ultimo:
            return ultimo < corte
        primero = getattr(self, "primer_fiado", None) or self.fiados.order_by("fecha").values_list("fecha", flat=True).first()
        return bool(primero and primero < corte)

    @property
    def estado(self):
        """(texto, clase CSS) para mostrar la etiqueta de estado."""
        saldo = self._saldo()
        if saldo <= 0:
            return ("Sin deuda", "neutro")
        if saldo > self.limite_credito:
            return ("Sobre el límite", "mal")
        if self.esta_atrasado:
            return ("Atrasado", "mal")
        if self.porcentaje_usado >= 80:
            return ("Cerca del límite", "aviso")
        return ("Al día", "ok")

    # ---- consulta del cliente ----
    def regenerar_codigo(self):
        self.codigo_acceso = generar_codigo()
        self.save(update_fields=["codigo_acceso"])

    def pin_valido(self, pin):
        """El cliente se identifica con los últimos 4 dígitos de su cédula."""
        return len(pin) == 4 and self.cedula[-4:] == pin

    @property
    def telefono_whatsapp(self):
        numero = "".join(c for c in self.telefono if c.isdigit())
        return "57" + numero if len(numero) == 10 else numero


class Producto(models.Model):
    tienda = models.ForeignKey(Tienda, on_delete=models.CASCADE, related_name="productos")
    nombre = models.CharField(max_length=100)
    precio = models.DecimalField(**DINERO, validators=[MinValueValidator(Decimal("0"))])
    activo = models.BooleanField(default=True, help_text="Los productos inactivos no aparecen al fiar.")

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(fields=["tienda", "nombre"], name="producto_unico_por_tienda"),
        ]

    def __str__(self):
        return self.nombre


class Fiado(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="fiados")
    fecha = models.DateTimeField(default=timezone.now)
    total = models.DecimalField(**DINERO, default=Decimal("0"), editable=False)
    nota = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Fiado #{self.pk} - {self.cliente}"

    def recalcular_total(self):
        self.total = self.detalles.aggregate(t=Sum("subtotal"))["t"] or Decimal("0")
        self.save(update_fields=["total"])

    def resumen(self):
        """Texto corto con los productos, por ejemplo: 'Arroz x2, Aceite'."""
        partes = []
        for d in self.detalles.all():
            partes.append(f"{d.descripcion} x{d.cantidad}" if d.cantidad > 1 else d.descripcion)
        return ", ".join(partes)


class DetalleFiado(models.Model):
    fiado = models.ForeignKey(Fiado, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(
        Producto, on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Vacío cuando es un valor libre.",
    )
    descripcion = models.CharField("descripción", max_length=120)
    cantidad = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    precio_unitario = models.DecimalField(**DINERO, validators=[MinValueValidator(Decimal("1"))])
    subtotal = models.DecimalField(**DINERO, editable=False)

    class Meta:
        verbose_name = "detalle de fiado"
        verbose_name_plural = "detalles de fiado"

    def save(self, *args, **kwargs):
        if self.producto and not self.descripcion:
            self.descripcion = self.producto.nombre
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.descripcion} x{self.cantidad}"


class Abono(models.Model):
    class Metodo(models.TextChoices):
        EFECTIVO = "efectivo", "Efectivo"
        NEQUI = "nequi", "Nequi"
        DAVIPLATA = "daviplata", "Daviplata"
        TRANSFERENCIA = "transferencia", "Transferencia"
        OTRO = "otro", "Otro"

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="abonos")
    fecha = models.DateTimeField(default=timezone.now)
    valor = models.DecimalField(**DINERO, validators=[MinValueValidator(Decimal("1"))])
    metodo = models.CharField("método", max_length=15, choices=Metodo.choices, default=Metodo.EFECTIVO)
    nota = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Abono de {self.cliente} por {self.valor}"
