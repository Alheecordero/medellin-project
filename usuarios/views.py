from django.shortcuts import render
from django.core.mail import send_mail
from django.urls import reverse_lazy, reverse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.contrib.auth.views import LogoutView as DjangoLogoutView


from django.views.generic import (
    View,
    CreateView,
    ListView,
    UpdateView,
    DeleteView
)

from django.views.generic.edit import (
    FormView
)

from .forms import (
    UserRegisterForm, 
    LoginForm,
    UserUpdateForm,
    UpdatePasswordForm,
)
#
from .models import User
# 


class UserRegisterView(FormView):
    template_name = 'users/register.html'
    form_class = UserRegisterForm
    success_url = reverse_lazy('usuarios_app:login')  # redirige al login tras registro

    def form_valid(self, form):
        User.objects.create_user(
            form.cleaned_data['email'],
            form.cleaned_data['password1'],
            full_name=form.cleaned_data['full_name'],
            ocupation=form.cleaned_data['ocupation'],
            genero=form.cleaned_data['genero'],
            date_birth=form.cleaned_data['date_birth'],
        )
        # aquí podrías enviar un correo si deseas
        return super().form_valid(form)


class LoginUser(FormView):
    template_name = 'users/login.html'
    form_class = LoginForm
    success_url = reverse_lazy('explorer:mis_favoritos')

    def form_valid(self, form):
        user = authenticate(
            email=form.cleaned_data['email'],
            password=form.cleaned_data['password']
        )
        login(self.request, user)
        return super(LoginUser, self).form_valid(form)


class LogoutView(DjangoLogoutView):
    next_page = reverse_lazy('usuarios_app:login')




class UserUpdateView(UpdateView):
    template_name = "users/update.html"
    model = User
    form_class = UserUpdateForm
    success_url = reverse_lazy('users_app:user-lista')


class UserDeleteView(DeleteView):
    model = User
    success_url = reverse_lazy('users_app:user-lista')


class UpdatePasswordView(LoginRequiredMixin, FormView):
    # template_name = 'users/update.html'
    form_class = UpdatePasswordForm
    success_url = reverse_lazy('users_app:user-login')
    login_url = reverse_lazy('users_app:user-login')

    def form_valid(self, form):
        usuario = self.request.user
        user = authenticate(
            email=usuario.email,
            password=form.cleaned_data['password1']
        )

        if user:
            new_password = form.cleaned_data['password2']
            usuario.set_password(new_password)
            usuario.save()

        logout(self.request)
        return super(UpdatePasswordView, self).form_valid(form)


class UserListView(ListView):
    template_name = "users/lista.html"
    context_object_name = 'usuarios'

    def get_queryset(self):
        return User.objects.usuarios_sistema()
    