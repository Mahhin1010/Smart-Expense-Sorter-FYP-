# pages/urls.py

from django.urls import path
from . import views
from .views import AISortingView, AnalyticsDashboardView, TransactionUploadView

urlpatterns = [
    # Route 1: Home page
    path('', views.home_view, name='home'),
    path('loops/', views.loop_test_view, name='loop_test'),

    # Route 2: Integer converter
    path('post/<int:post_id>/', views.post_detail_view, name='post_detail_view'),

    # Route 3: String converter
    path('user/<str:username>/', views.user_profile_view, name='user_profile'),

    # Route 4: Slug converter
    path('blog/<slug:post_slug>/', views.post_slug_view, name='post_by_slug'),

    # Route 5: UUID converter
    path('item/<uuid:item_uuid>/', views.item_detail_view, name='item_detail'),

    # Manage Categories (UC 2.1)
    path('categories/', views.manage_categories_view, name='manage_categories'),
    
    # Upload Transactions (UC 3.1) - Now using CBV
    path('upload/', TransactionUploadView.as_view(), name='upload_transactions'),

    # AI Sorting (UC 4.1)
    path('ai-sorting/', AISortingView.as_view(), name='ai_sorting'),

    # Analytics Dashboard (UC 5.1)
    path('analytics/', AnalyticsDashboardView.as_view(), name='analytics_dashboard'),
]