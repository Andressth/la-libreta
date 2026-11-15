from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """Usuario del sistema. Extiende el usuario de Django y agrega el rol."""

    class Rol(models.TextChoices):
        TENDERO = "tendero", "Tendero"
        ADMIN = "admin", "Administrador"

    rol = models.CharField(max_length=10, choices=Rol.choices, default=Rol.TENDERO)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def save(self, *args, **kwargs):
        # Un superusuario siempre es administrador, y el administrador
        # necesita is_staff para entrar al panel de Django.
        if self.is_superuser:
            self.rol = self.Rol.ADMIN
        if self.rol == self.Rol.ADMIN:
            self.is_staff = True
        super().save(*args, **kwargs)

    @property
    def es_admin(self):
        return self.rol == self.Rol.ADMIN

    @property
    def es_tendero(self):
        return self.rol == self.Rol.TENDERO

    def __str__(self):
        return self.get_full_name() or self.username
