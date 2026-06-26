from django.contrib import admin
from .models import UserProfile, AITelemetryLog

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'ai_provider', 'gemini_model', 'openai_model')
    search_fields = ('user__username', 'user__email')

@admin.register(AITelemetryLog)
class AITelemetryLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'provider', 'model_name', 'batch_size', 'latency_seconds', 'calculated_cost_usd', 'created_at')
    list_filter = ('provider', 'model_name', 'success')
    search_fields = ('user__username',)

