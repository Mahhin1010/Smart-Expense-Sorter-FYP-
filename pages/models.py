from django.db import models
from django.contrib.auth.models import User

class Category(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=50)

    class Meta:
        verbose_name_plural = "Categories"
        unique_together = ('user', 'name')  # Unique per user

    def __str__(self):
        return self.name # Without this The repsoen will be like cat obj1 and cat obj2 this make sure that we get the actual nemas as a reuslt 
