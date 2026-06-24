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
    
    gemini_model = models.CharField(max_length=50, default='gemini-2.0-flash')
    openai_model = models.CharField(max_length=50, default='gpt-4.1-nano')
    deepseek_model = models.CharField(max_length=50, default='deepseek-chat')


    def __str__(self):
        return f"{self.user.username}'s Profile"

# Signals to auto-create profile
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    profile, _ = UserProfile.objects.get_or_create(user=instance)
    profile.save()
