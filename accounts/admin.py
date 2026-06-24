from django.contrib import admin
from .models import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'ai_provider', 'gemini_model', 'openai_model')
    search_fields = ('user__username', 'user__email')
