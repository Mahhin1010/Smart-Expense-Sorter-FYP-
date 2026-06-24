from django.urls import reverse_lazy
from django.views.generic import CreateView, View
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.conf import settings
import json
import requests
from .forms import SignUpForm
from .models import UserProfile

class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('home')

    def form_valid(self, form):
        # Auto-login the user after successful signup
        response = super().form_valid(form)
        login(self.request, self.object)
        return response

class UserSettingsView(LoginRequiredMixin, View):
    template_name = 'settings.html'

    def get(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        return render(request, self.template_name, {'profile': profile})

    def post(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        
        # Save provider
        profile.ai_provider = request.POST.get('ai_provider', 'gemini')
        
        # Save Gemini settings
        profile.gemini_model = request.POST.get('gemini_model', 'gemini-2.0-flash')
        profile.gemini_api_key = request.POST.get('gemini_api_key', '').strip() or None
        
        # Save OpenAI settings
        profile.openai_model = request.POST.get('openai_model', 'gpt-4o-mini')
        profile.openai_api_key = request.POST.get('openai_api_key', '').strip() or None
        
        profile.save()
        messages.success(request, "Settings saved successfully!")
        return redirect('user_settings')

class TestAIKeyAPI(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            provider = data.get('provider')
            key = data.get('key', '').strip()
            model_name = data.get('model')
            
            if provider == 'gemini':
                import google.generativeai as genai
                # Fallback to system key if empty
                test_key = key or getattr(settings, 'GEMINI_API_KEY', None)
                if not test_key:
                    return JsonResponse({'status': 'error', 'message': 'No API Key configured.'})
                
                try:
                    genai.configure(api_key=test_key)
                    model = genai.GenerativeModel(model_name or 'gemini-2.0-flash')
                    response = model.generate_content("Say OK", generation_config={"max_output_tokens": 10})
                    if response:
                        return JsonResponse({'status': 'success'})
                except Exception as e:
                    return JsonResponse({'status': 'error', 'message': str(e)})
                    
            elif provider == 'openai':
                if not key:
                    return JsonResponse({'status': 'error', 'message': 'API Key is required.'})
                
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model_name or "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "Say OK"}],
                    "max_tokens": 5
                }
                try:
                    res = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=10
                    )
                    if res.status_code == 200:
                        return JsonResponse({'status': 'success'})
                    else:
                        try:
                            err_msg = res.json().get('error', {}).get('message', 'Unknown error')
                        except:
                            err_msg = res.text
                        return JsonResponse({'status': 'error', 'message': f"OpenAI: {err_msg}"})
                except Exception as e:
                    return JsonResponse({'status': 'error', 'message': str(e)})
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid provider.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"Failed: {str(e)}"})
