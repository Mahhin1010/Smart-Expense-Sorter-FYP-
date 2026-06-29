# pages/urls.py

from django.urls import path
from . import views
from .views import AISortingView, AnalyticsDashboardView, TransactionUploadView, HomeView, ManageCategoriesView, AboutView, FeaturesView, UpdateTransactionCategoryAPI, DeleteTransactionAPI, ClearAllTransactionsView, TransactionHistoryView

urlpatterns = [
    # Route 1: Home page
    path('', HomeView.as_view(), name='home'),
    # Route 1.1: Static pages
    path('about/', AboutView.as_view(), name='about'),
    path('features/', FeaturesView.as_view(), name='features'),

    # Manage Categories (UC 2.1)
    path('categories/', ManageCategoriesView.as_view(), name='manage_categories'),
    
    # Upload Transactions (UC 3.1) - Now using CBV
    path('upload/', TransactionUploadView.as_view(), name='upload_transactions'),

    # AI Sorting (UC 4.1)
    path('ai-sorting/', AISortingView.as_view(), name='ai_sorting'),
    path('api/update-category/', UpdateTransactionCategoryAPI.as_view(), name='api_update_category'),
    path('api/delete-transaction/', DeleteTransactionAPI.as_view(), name='api_delete_transaction'),
    path('clear-transactions/', ClearAllTransactionsView.as_view(), name='clear_all_transactions'),

    # Transaction History
    path('history/', TransactionHistoryView.as_view(), name='transaction_history'),

    # Analytics Dashboard (UC 5.1)
    path('analytics/', AnalyticsDashboardView.as_view(), name='analytics_dashboard'),
]