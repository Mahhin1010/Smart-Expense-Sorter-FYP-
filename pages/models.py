from django.db import models
from django.contrib.auth.models import User

class Category(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=50)

    class Meta:
        verbose_name_plural = "Categories"
        unique_together = ('user', 'name')  # Unique per user

    def __str__(self):
        return self.name
