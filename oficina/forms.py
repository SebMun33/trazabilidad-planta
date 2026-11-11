from django import forms
from django.forms import formset_factory

from planta.models import Maquina, Urgencia


class TrabajoForm(forms.Form):
    plano = forms.CharField(max_length=60)
    plano_descripcion = forms.CharField(label="Descripción", required=False, max_length=200)
    pedido_id = forms.IntegerField(
        label="N.º de pedido",
        required=False,
        min_value=1,
        help_text="Si viene de una cotización, se completa cuando FoxPro genere el pedido.",
    )
    cliente_nombre = forms.CharField(label="Cliente", required=False, max_length=120)
    cantidad = forms.DecimalField(required=False, min_value=0.01, max_digits=12, decimal_places=2)
    urgencia = forms.TypedChoiceField(
        choices=Urgencia.choices,
        coerce=int,
        initial=Urgencia.NORMAL,
        widget=forms.RadioSelect,
    )
    fecha_entrega_estimada = forms.DateField(
        label="Entrega estimada",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    observaciones = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3}), max_length=2000
    )


def opciones_maquina(extra_ids=()):
    opciones = [("", "— Sin máquina asignada —")]
    conocidas = set()
    for m in Maquina.objects.order_by("nombre"):
        opciones.append((str(m.maquina_id), m.nombre))
        conocidas.add(m.maquina_id)
    # Máquinas que ya figuran en la ruta pero no están en el catálogo publicado.
    for mid in sorted({i for i in extra_ids if i and i not in conocidas}):
        opciones.append((str(mid), f"Máquina {mid} (no publicada)"))
    return opciones


class OperacionForm(forms.Form):
    maquina_id = forms.TypedChoiceField(
        label="Máquina", required=False, coerce=int, empty_value=None, choices=()
    )
    descripcion = forms.CharField(label="Proceso", required=False, max_length=300)
    observaciones = forms.CharField(required=False, max_length=1000)
    operacion_id = forms.UUIDField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, opciones=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["maquina_id"].choices = opciones


OperacionFormSet = formset_factory(OperacionForm, extra=0, can_delete=True)


class MotivoForm(forms.Form):
    motivo = forms.CharField(required=False, max_length=500)
