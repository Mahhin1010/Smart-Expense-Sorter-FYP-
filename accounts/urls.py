from django.urls import path
from django.contrib.auth import views as auth_views
from .views import SignUpView, UserSettingsView, TestAIKeyAPI

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('signup/', SignUpView.as_view(), name='signup'),
    path('settings/', UserSettingsView.as_view(), name='user_settings'),
    path('api/test-ai-key/', TestAIKeyAPI.as_view(), name='test_ai_key_api'),
]
