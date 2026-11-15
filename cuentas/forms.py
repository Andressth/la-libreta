from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import transaction

from libreta.models import Tienda, solo_numeros
from .models import Usuario


class RegistroTenderoForm(UserCreationForm):
    """Crea el usuario (rol tendero) y su tienda en un solo paso."""

    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    email = forms.EmailField(label="Correo electrónico")

    nombre_tienda = forms.CharField(label="Nombre de la tienda", max_length=100,
                                    widget=forms.TextInput(attrs={"placeholder": "Ej: Tienda Doña Rosa"}))
    direccion = forms.CharField(label="Dirección", max_length=150)
    municipio = forms.CharField(label="Municipio", max_length=80)
    telefono = forms.CharField(label="Teléfono de la tienda", max_length=15, validators=[solo_numeros])

    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ("first_name", "last_name", "email", "username")
        labels = {"username": "Usuario"}
        help_texts = {"username": "Con este nombre vas a ingresar. Sin espacios."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].help_text = "Mínimo 8 caracteres. Que no sea solo números ni una clave común."
        self.fields["password2"].help_text = ""

    @transaction.atomic
    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.rol = Usuario.Rol.TENDERO
        usuario.save()
        Tienda.objects.create(
            tendero=usuario,
            nombre=self.cleaned_data["nombre_tienda"],
            direccion=self.cleaned_data["direccion"],
            municipio=self.cleaned_data["municipio"],
            telefono=self.cleaned_data["telefono"],
        )
        return usuario


class IngresarForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Usuario o contraseña incorrectos. Revisa mayúsculas y minúsculas.",
        "inactive": "Esta cuenta está desactivada. Comunícate con el administrador.",
    }
