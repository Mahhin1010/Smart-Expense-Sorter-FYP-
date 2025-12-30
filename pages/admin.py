from django.contrib import admin
from .models import Category, Transaction, DefaultCategory

admin.site.register(Category)
admin.site.register(DefaultCategory)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'description', 'amount', 'category')
    list_filter = ('user', 'date', 'category')
    search_fields = ('description', 'user__username')
