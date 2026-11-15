from django.shortcuts import render


def home(request):
    """Página de inicio pública (visitantes y clientes)."""
    return render(request, "core/home.html")
