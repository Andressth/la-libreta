from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory

from .models import Abono, Cliente, DetalleFiado, Fiado, Producto, Tienda
from .templatetags.pesos import pesos


class TiendaForm(forms.ModelForm):
    class Meta:
        model = Tienda
        fields = ["nombre", "direccion", "municipio", "telefono"]


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "cedula", "telefono", "direccion", "limite_credito", "activo"]
        help_texts = {
            "cedula": "Los últimos 4 dígitos sirven al cliente para consultar su cuenta.",
            "limite_credito": "Hasta cuánto le fías. Si un fiado lo supera, el sistema te avisa.",
            "activo": "Si lo desmarcas, el cliente queda archivado y no aparece al fiar.",
        }

    def __init__(self, *args, tienda, **kwargs):
        super().__init__(*args, **kwargs)
        self.tienda = tienda

    def clean_cedula(self):
        cedula = self.cleaned_data["cedula"]
        repetido = Cliente.objects.filter(tienda=self.tienda, cedula=cedula).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Ya tienes un cliente registrado con esta cédula.")
        return cedula

    def save(self, commit=True):
        self.instance.tienda = self.tienda
        return super().save(commit)


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["nombre", "precio", "activo"]

    def __init__(self, *args, tienda, **kwargs):
        super().__init__(*args, **kwargs)
        self.tienda = tienda

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        repetido = Producto.objects.filter(tienda=self.tienda, nombre__iexact=nombre).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Ya existe un producto con ese nombre.")
        return nombre

    def save(self, commit=True):
        self.instance.tienda = self.tienda
        return super().save(commit)


# ---------------------------------------------------------------- fiados

class FiadoForm(forms.ModelForm):
    confirmar_limite = forms.BooleanField(
        required=False, label="Sí, quiero fiarle aunque supere su límite de crédito"
    )

    class Meta:
        model = Fiado
        fields = ["cliente", "nota"]
        widgets = {"nota": forms.TextInput(attrs={"placeholder": "Opcional"})}

    def __init__(self, *args, tienda, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = tienda.clientes.filter(activo=True)
        self.fields["cliente"].empty_label = "Escoge un cliente"


class DetalleFiadoForm(forms.ModelForm):
    class Meta:
        model = DetalleFiado
        fields = ["producto", "descripcion", "cantidad", "precio_unitario"]
        widgets = {
            "descripcion": forms.TextInput(attrs={"placeholder": "Descripción (valor libre)"}),
            "cantidad": forms.NumberInput(attrs={"min": 1}),
            "precio_unitario": forms.NumberInput(attrs={"min": 1, "placeholder": "Precio"}),
        }

    def __init__(self, *args, tienda, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = tienda.productos.filter(activo=True)
        self.fields["producto"].empty_label = "Valor libre"
        self.fields["producto"].required = False
        self.fields["descripcion"].required = False
        self.fields["precio_unitario"].required = False

    def clean(self):
        datos = super().clean()
        producto = datos.get("producto")
        if producto:
            datos["descripcion"] = datos.get("descripcion") or producto.nombre
            if not datos.get("precio_unitario"):
                datos["precio_unitario"] = producto.precio
        else:
            if not datos.get("descripcion"):
                self.add_error("descripcion", "Escribe qué se llevó, o escoge un producto.")
            if not datos.get("precio_unitario"):
                self.add_error("precio_unitario", "Escribe el valor.")
        return datos


DetalleFormSet = inlineformset_factory(
    Fiado, DetalleFiado, form=DetalleFiadoForm,
    extra=8, can_delete=False, min_num=1, validate_min=True,
)


def total_de_formset(formset):
    total = Decimal("0")
    for f in formset.forms:
        if f.cleaned_data and f.cleaned_data.get("precio_unitario"):
            total += f.cleaned_data["cantidad"] * f.cleaned_data["precio_unitario"]
    return total


# ---------------------------------------------------------------- abonos

class AbonoForm(forms.ModelForm):
    class Meta:
        model = Abono
        fields = ["cliente", "valor", "metodo", "nota"]
        widgets = {"nota": forms.TextInput(attrs={"placeholder": "Opcional"})}

    def __init__(self, *args, tienda, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].queryset = tienda.clientes.filter(activo=True)
        self.fields["cliente"].empty_label = "Escoge un cliente"

    def clean(self):
        datos = super().clean()
        cliente, valor = datos.get("cliente"), datos.get("valor")
        if cliente and valor:
            saldo = cliente.calcular_saldo()
            if saldo <= 0:
                self.add_error("cliente", "Este cliente no tiene deuda pendiente.")
            elif valor > saldo:
                self.add_error("valor", f"El abono no puede ser mayor que el saldo pendiente ({pesos(saldo)}).")
        return datos


# ---------------------------------------------------------------- consulta del cliente

class PinForm(forms.Form):
    pin = forms.CharField(
        label="Últimos 4 dígitos de tu cédula", min_length=4, max_length=4,
        widget=forms.TextInput(attrs={
            "inputmode": "numeric", "autocomplete": "off", "pattern": "[0-9]{4}",
            "placeholder": "••••", "class": "pin",
        }),
    )
