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


class UploadedFile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_files')
    filename = models.CharField(max_length=255)
    upload_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Uploaded Files"

    def __str__(self):
        return f"{self.filename} ({self.upload_date})"


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
    uploaded_file = models.ForeignKey(
        UploadedFile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
        help_text="File from which this transaction was imported"
    )
    date = models.DateField(help_text="Transaction date")
    description = models.CharField(max_length=255, help_text="Transaction description from bank")
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Transaction amount (positive or negative)"
    )
    merchant_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Merchant or payee name (e.g. Carrefour, Uber, K-Electric)"
    )
    transaction_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Transaction type (e.g. POS Swipe, Bill Payment, Wallet Transfer)"
    )
    notes = models.TextField(
        null=True, 
        blank=True,
        help_text="Optional notes or memo"
    )
    ai_confidence = models.FloatField(
        null=True,
        blank=True,
        help_text="AI classification confidence score (0.0 to 1.0)"
    )
    is_ai_categorized = models.BooleanField(
        default=False,
        help_text="True if category was assigned by the AI engine"
    )
    ai_suggested_category = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Category suggested by AI when it falls into Uncategorized"
    )
    transaction_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Extracted unique transaction reference ID"
    )
    tx_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        help_text="SHA-256 hash of core fields to detect duplicates"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
    
    def __str__(self):
        return f"{self.date} - {self.description[:30]} ({self.amount})"
