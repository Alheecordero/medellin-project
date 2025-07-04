from django import forms
from django.contrib.auth import authenticate
from .models import User

class UserRegisterForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Contraseña',
        required=True,
        widget=forms.PasswordInput(
            attrs={
                'placeholder': 'Contraseña',
                'class': 'form-control',
            }
        )
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        required=True,
        widget=forms.PasswordInput(
            attrs={
                'placeholder': 'Repetir Contraseña',
                'class': 'form-control',
            }
        )
    )

    class Meta:
        model = User
        fields = (
            'email',
            'full_name',
            'ocupation',
            'genero',
            'date_birth',
        )
        widgets = {
            'email': forms.EmailInput(attrs={
                'placeholder': 'Correo electrónico',
                'class': 'form-control',
            }),
            'full_name': forms.TextInput(attrs={
                'placeholder': 'Nombres completos',
                'class': 'form-control',
            }),
            'ocupation': forms.Select(attrs={
                'class': 'form-select',
            }),
            'genero': forms.Select(attrs={
                'class': 'form-select',
            }),
            'date_birth': forms.DateInput(format='%Y-%m-%d', attrs={
                'type': 'date',
                'class': 'form-control',
            }),
        }

    def clean_password2(self):
        if self.cleaned_data.get('password1') != self.cleaned_data.get('password2'):
            self.add_error('password2', 'Las contraseñas no son iguales')


class LoginForm(forms.Form):
    email = forms.CharField(
        label='Correo electrónico',
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Correo electrónico',
        })
    )
    password = forms.CharField(
        label='Contraseña',
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Contraseña',
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')
        if not authenticate(email=email, password=password):
            raise forms.ValidationError('Los datos de usuario no son correctos')
        return cleaned_data


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            'email',
            'full_name',
            'ocupation',
            'genero',
            'date_birth',
            'is_active',
        )
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Correo electrónico',
            }),
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre completo',
            }),
            'ocupation': forms.Select(attrs={
                'class': 'form-select',
            }),
            'genero': forms.Select(attrs={
                'class': 'form-select',
            }),
            'date_birth': forms.DateInput(format='%Y-%m-%d', attrs={
                'type': 'date',
                'class': 'form-control',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }


class UpdatePasswordForm(forms.Form):
    password1 = forms.CharField(
        label='Contraseña actual',
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Contraseña actual',
        })
    )
    password2 = forms.CharField(
        label='Nueva contraseña',
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nueva contraseña',
        })
    )
