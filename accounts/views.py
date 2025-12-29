from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.contrib.auth import login
from .forms import SignUpForm

class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        # Auto-login the user after successful signup
        response = super().form_valid(form)
        login(self.request, self.object)
        return response
