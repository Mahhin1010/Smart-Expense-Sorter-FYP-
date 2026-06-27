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
        
        # Save Gemini settings (Hardcoded to gemini-3.1-flash-lite)
        profile.gemini_model = 'gemini-3.1-flash-lite'
        profile.gemini_api_key = request.POST.get('gemini_api_key', '').strip() or None
        
        # Save OpenAI settings (Hardcoded to gpt-4.1-nano)
        profile.openai_model = 'gpt-4.1-nano'
        profile.openai_api_key = request.POST.get('openai_api_key', '').strip() or None
        
        # Save DeepSeek settings (Hardcoded to deepseek-chat)
        profile.deepseek_model = 'deepseek-chat'
        profile.deepseek_api_key = request.POST.get('deepseek_api_key', '').strip() or None
        
        profile.save()
        
        active_model = profile.gemini_model if profile.ai_provider == 'gemini' else (
            profile.openai_model if profile.ai_provider == 'openai' else profile.deepseek_model
        )
        messages.success(request, f"Settings saved! Active provider is now {profile.get_ai_provider_display()} ({active_model}).")
        return redirect('user_settings')


class TestAIKeyAPI(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            provider = data.get('provider')
            key = data.get('key', '').strip()
            
            if provider == 'gemini':
                import google.generativeai as genai
                test_key = key or getattr(settings, 'GEMINI_API_KEY', None)
                if not test_key:
                    return JsonResponse({'status': 'error', 'message': 'No API Key configured.'})
                
                try:
                    genai.configure(api_key=test_key)
                    model = genai.GenerativeModel('gemini-3.1-flash-lite')
                    response = model.generate_content("Say OK", generation_config={"max_output_tokens": 10})
                    if response:
                        return JsonResponse({'status': 'success'})
                except Exception as e:
                    return JsonResponse({'status': 'error', 'message': str(e)})
                    
            elif provider == 'openai':
                if not key:
                    return JsonResponse({'status': 'error', 'message': 'API Key is required.'})
                
                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=key)
                    response = client.chat.completions.create(
                        model="gpt-4.1-nano",
                        messages=[{"role": "user", "content": "Say OK"}],
                        max_tokens=5
                    )
                    if response:
                        return JsonResponse({'status': 'success'})
                except Exception as e:
                    return JsonResponse({'status': 'error', 'message': f"OpenAI: {str(e)}"})
                    
            elif provider == 'deepseek':
                test_key = key or getattr(settings, 'DEEPSEEK_API_KEY', None)
                if not test_key:
                    return JsonResponse({'status': 'error', 'message': 'No API Key configured.'})
                
                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=test_key, base_url="https://api.deepseek.com")
                    response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "user", "content": "Say OK"}],
                        max_tokens=5
                    )
                    if response:
                        return JsonResponse({'status': 'success'})
                except Exception as e:
                    return JsonResponse({'status': 'error', 'message': f"DeepSeek: {str(e)}"})
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid provider.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"Failed: {str(e)}"})


