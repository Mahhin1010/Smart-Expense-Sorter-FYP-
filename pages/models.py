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

class DefaultCategory(models.Model):
    """
    Global default categories managed by Admins.
    These appear as suggestions for all users in the Manage Categories view.
    """
    name = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Default Categories"
        ordering = ['name']

    def __str__(self):
        return self.name 


class Transaction(models.Model):
    """
    Transaction model for storing uploaded financial transactions.
    Each transaction is linked to a user (owner) and optionally to a category.
    Used by UC-3.1 (Upload Transaction CSV) and UC-3.2 (AI Sorting).
    """
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='transactions',
        help_text="Owner of this transaction"
    )
    category = models.ForeignKey(
        Category, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='transactions',
        help_text="Category assigned by AI or user"
    )
    date = models.DateField(help_text="Transaction date")
    description = models.CharField(max_length=255, help_text="Transaction description from bank")
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Transaction amount (positive or negative)"
    )
    notes = models.TextField(
        null=True, 
        blank=True,
        help_text="Optional notes or memo"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
    
    def __str__(self):
        return f"{self.date} - {self.description[:30]} ({self.amount})"
