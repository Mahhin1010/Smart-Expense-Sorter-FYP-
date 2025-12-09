# pages/urls.py

from django.urls import path
from . import views  # This imports views from the current 'pages' app

urlpatterns = [
    # Route 1: Home page (your existing one)
    path('', views.home_view, name='home'),
    path('loops/', views.loop_test_view, name='loop_test'),

    # Route 2: Integer converter (your existing one)
    path('post/<int:post_id>/', views.post_detail_view, name='post_detail_view'),

    # --- 3. ADD THESE NEW URLS ---

    # Route 3: String converter
    # This path connects to your 'user_profile_view' function
    path('user/<str:username>/', views.user_profile_view, name='user_profile'),

    # Route 4: Slug converter
    # This path connects to 'post_slug_view'
    path('blog/<slug:post_slug>/', views.post_slug_view, name='post_by_slug'),

    # Route 5: UUID converter
    # This path connects to your 'item_detail_view' function
    path('item/<uuid:item_uuid>/', views.item_detail_view, name='item_detail'),

    # Manage Categories (UC 2.1)
    path('categories/', views.manage_categories_view, name='manage_categories'),
]