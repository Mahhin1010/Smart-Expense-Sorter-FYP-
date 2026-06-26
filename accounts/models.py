from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    gemini_api_key = models.CharField(max_length=255, blank=True, null=True)
    openai_api_key = models.CharField(max_length=255, blank=True, null=True)
    deepseek_api_key = models.CharField(max_length=255, blank=True, null=True)
    
    PROVIDER_CHOICES = [
        ('gemini', 'Google Gemini AI'),
        ('openai', 'OpenAI'),
        ('deepseek', 'DeepSeek AI'),
    ]
    ai_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='gemini')
    
    gemini_model = models.CharField(max_length=50, default='gemini-2.5-flash')
    openai_model = models.CharField(max_length=50, default='gpt-4.1-nano')
    deepseek_model = models.CharField(max_length=50, default='deepseek-chat')


    def __str__(self):
        return f"{self.user.username}'s Profile"


class AITelemetryLog(models.Model):
    """
    Records every AI API call made during transaction categorization.
    This is the raw telemetry table — the single source of truth for 
    the AI Performance Benchmarking dashboard in Metabase.
    """
    PROVIDER_CHOICES = [
        ('gemini', 'Google Gemini'),
        ('openai', 'OpenAI'),
        ('deepseek', 'DeepSeek'),
    ]

    # === WHO ===
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_telemetry_logs')

    # === WHICH AI ===
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    model_name = models.CharField(max_length=100)         # e.g. "gemini-2.5-flash"

    # === HOW MUCH (Volume) ===
    batch_size = models.IntegerField()                    # Number of transactions in this batch
    
    # === HOW FAST (Speed) ===
    latency_seconds = models.FloatField()                 # API wall-clock time in seconds

    # === HOW EXPENSIVE (Cost) ===
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    calculated_cost_usd = models.DecimalField(max_digits=12, decimal_places=8, default=0)

    # === HOW ACCURATE (Quality) ===
    avg_confidence = models.FloatField(null=True, blank=True)  # Mean confidence across the batch
    success = models.BooleanField(default=True)               # False if the API call failed/raised
    error_type = models.CharField(max_length=50, blank=True)  # e.g. "RateLimit", "Timeout", ""

    # === WHEN ===
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "AI Telemetry Log"
        verbose_name_plural = "AI Telemetry Logs"

    def __str__(self):
        return f"{self.provider}/{self.model_name} @ {self.created_at:%Y-%m-%d %H:%M} — ${self.calculated_cost_usd}"


# Signals to auto-create profile
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    profile, _ = UserProfile.objects.get_or_create(user=instance)
    profile.save()
