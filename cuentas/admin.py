"""Admin de usuarios: se elige un rol, nunca permisos sueltos.

- La contraseña es opcional: sin contraseña (operarios) el usuario solo puede
  registrar desde el kiosco de planta.
- Staff administra todo salvo los superusuarios: no los ve, no los edita y no
  puede crear uno.
"""

from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from .nombres import normalizar
from .roles import OPCIONES, OPERARIO, ROLES, asignar_rol, etiqueta_de, rol_de

Usuario = get_user_model()


def _validar_nombre_unico(nombre: str, actual=None) -> None:
    otros = Usuario.objects.exclude(pk=actual.pk) if actual and actual.pk else Usuario.objects
    if any(normalizar(u.username) == normalizar(nombre) for u in otros.only("username")):
        raise ValidationError("Ya hay un usuario con ese nombre (sin contar mayúsculas ni tildes).")


class UsuarioForm(forms.ModelForm):
    rol = forms.ChoiceField(choices=OPCIONES, label="Rol")
    contrasena1 = forms.CharField(
        label="Contraseña",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Dejala vacía para un operario: entra solo con su nombre, desde el kiosco.",
    )
    contrasena2 = forms.CharField(
        label="Repetir contraseña",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    quitar_contrasena = forms.BooleanField(
        label="Quitar la contraseña",
        required=False,
        help_text="El usuario pasa a entrar solo con su nombre (únicamente desde el kiosco).",
    )

    class Meta:
        model = Usuario
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {"username": "Nombre (para ingresar)"}
        help_texts = {
            "username": "Sin espacios. Para ingresar no importan mayúsculas ni tildes.",
            "is_active": "Desmarcalo en lugar de borrar el usuario: su historia queda.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.is_superuser:
            # El superusuario no tiene rol: es la cuenta del dueño del sistema.
            del self.fields["rol"]
        else:
            rol = rol_de(self.instance) if self.instance.pk else OPERARIO
            if rol in ROLES:
                self.fields["rol"].initial = rol
        if not self.instance.pk:
            del self.fields["quitar_contrasena"]
        else:
            self.fields["contrasena1"].label = "Contraseña nueva"
            self.fields["contrasena1"].help_text = "Dejala vacía para no cambiarla."

    def clean_username(self):
        nombre = self.cleaned_data["username"]
        _validar_nombre_unico(nombre, self.instance)
        return nombre

    def clean(self):
        datos = super().clean()
        c1, c2 = datos.get("contrasena1"), datos.get("contrasena2")
        if c1 or c2:
            if c1 != c2:
                self.add_error("contrasena2", "Las contraseñas no coinciden.")
            elif datos.get("quitar_contrasena"):
                self.add_error("quitar_contrasena", "Elegí cambiarla o quitarla, no las dos.")
            else:
                try:
                    password_validation.validate_password(c1, self.instance)
                except ValidationError as error:
                    self.add_error("contrasena1", error)
        rol = datos.get("rol")
        sin_contrasena = datos.get("quitar_contrasena") or (
            not c1 and not (self.instance.pk and self.instance.has_usable_password())
        )
        if rol in ROLES and ROLES[rol].usa_contrasena and sin_contrasena:
            self.add_error("contrasena1", f"El rol {ROLES[rol].etiqueta} necesita contraseña.")
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        nueva = self.cleaned_data.get("contrasena1")
        if nueva:
            usuario.set_password(nueva)
        elif not usuario.pk or self.cleaned_data.get("quitar_contrasena"):
            usuario.set_unusable_password()
        if commit:
            usuario.save()
        return usuario


class SinSuperusuarios(admin.SimpleListFilter):
    title = "rol"
    parameter_name = "rol"

    def lookups(self, request, model_admin):
        return OPCIONES

    def queryset(self, request, queryset):
        return queryset.filter(groups__name=self.value()) if self.value() else queryset


admin.site.unregister(Usuario)
admin.site.unregister(Group)  # los grupos son los roles: se manejan desde el código


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioForm
    add_form = UsuarioForm
    list_display = ["username", "nombre_completo", "rol", "tiene_contrasena", "is_active"]
    list_filter = [SinSuperusuarios, "is_active"]
    search_fields = ["username", "first_name", "last_name"]
    ordering = ["username"]
    fieldsets = [
        (None, {"fields": ["username", "rol", "is_active"]}),
        ("Contraseña", {"fields": ["contrasena1", "contrasena2", "quitar_contrasena"]}),
        ("Datos", {"fields": ["first_name", "last_name", "email"]}),
    ]
    add_fieldsets = [
        (None, {"fields": ["username", "rol"]}),
        ("Contraseña", {"fields": ["contrasena1", "contrasena2"]}),
        ("Datos", {"fields": ["first_name", "last_name", "email"]}),
    ]
    filter_horizontal = []

    @admin.display(description="Nombre")
    def nombre_completo(self, obj):
        return obj.get_full_name() or "—"

    @admin.display(description="Rol")
    def rol(self, obj):
        return etiqueta_de(obj)

    @admin.display(description="Contraseña", boolean=True)
    def tiene_contrasena(self, obj):
        return obj.has_usable_password()

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is not None and obj.is_superuser:
            return [(None, {"fields": ["username", "is_active"]}), *fieldsets[1:]]
        return fieldsets

    def get_queryset(self, request):
        usuarios = super().get_queryset(request)
        return usuarios if request.user.is_superuser else usuarios.filter(is_superuser=False)

    def _toca_superusuario(self, request, obj) -> bool:
        return obj is not None and obj.is_superuser and not request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        if self._toca_superusuario(request, obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if self._toca_superusuario(request, obj):
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not obj.is_superuser and form.cleaned_data.get("rol") in ROLES:
            asignar_rol(obj, form.cleaned_data["rol"])

    def save_related(self, request, form, formsets, change):
        # Los grupos los maneja `asignar_rol`: no hay campos m2m en el formulario.
        for formset in formsets:
            self.save_formset(request, form, formset, change=change)
