from django.contrib import admin
from .models import Category, Transaction, DefaultCategory, UploadedFile

admin.site.register(Category)
admin.site.register(DefaultCategory)
admin.site.register(UploadedFile)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'date', 'description', 'merchant_name',
        'transaction_type', 'amount', 'category',
        'ai_confidence', 'is_ai_categorized'
    )
    list_filter = ('user', 'date', 'category', 'is_ai_categorized', 'transaction_type')
    search_fields = ('description', 'merchant_name', 'user__username', 'notes')
    list_per_page = 50
    readonly_fields = ('ai_confidence', 'is_ai_categorized', 'created_at')
