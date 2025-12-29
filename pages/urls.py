# pages/urls.py

from django.urls import path
from . import views
from .views import AISortingView, AnalyticsDashboardView, TransactionUploadView, HomeView, ManageCategoriesView

urlpatterns = [
    # Route 1: Home page
    path('', HomeView.as_view(), name='home'),
    # Manage Categories (UC 2.1)
    path('categories/', ManageCategoriesView.as_view(), name='manage_categories'),
    
    # Upload Transactions (UC 3.1) - Now using CBV
    path('upload/', TransactionUploadView.as_view(), name='upload_transactions'),

    # AI Sorting (UC 4.1)
    path('ai-sorting/', AISortingView.as_view(), name='ai_sorting'),

    # Analytics Dashboard (UC 5.1)
    path('analytics/', AnalyticsDashboardView.as_view(), name='analytics_dashboard'),
]