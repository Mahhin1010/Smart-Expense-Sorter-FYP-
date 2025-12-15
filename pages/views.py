from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Category
from django.db import IntegrityError
from django.contrib import messages

from django.http import HttpResponse
import datetime # We need this to get the current year for the copyright

# --- 1. UPDATED 'home_view' for your Smart Sorter project ---
def home_view(request):
    
    # --- Data for Navigation Bar (Unchanged) ---
    nav_links_data = [
        {"name": "Home", "url": "#home"},
        {"name": "Features", "url": "#features"},
        {"name": "About", "url": "#about"},
        {"name": "Login", "url": "#login"},
    ]

  
    # We just need the image path and alt text.
    slider_items_data = [
        {
            "image_path": "images/image1.png",
            "alt_text": "Tired of messy transaction files?"
        },
        {
            "image_path": "images/image2.png",
            "alt_text": "Boost your financial productivity"
        },
        {
            "image_path": "images/image3.png",
            "alt_text": "Start sorting now"
        }
    ]

    # --- Data for "How It Works" (Unchanged) ---
    how_it_works_steps_data = [
        {
            "icon": "📤",
            "title": "Upload Your File",
            "description": "Simply drag and drop your transaction files. We support CSV, Excel, PDF, and more. No formatting required!"
        },
        {
            "icon": "🔄",
            "title": "Smart Sorting",
            "description": "Our AI-powered engine automatically cleans, categorizes, and organizes your data with incredible accuracy."
        },
        {
            "icon": "📈",
            "title": "Analyze & Export",
            "description": "Get instant insights with beautiful charts and reports. Export clean data in your preferred format."
        }
    ]

    # --- Data for Footer (Unchanged) ---
    quick_links_data = [
        {"name": "Features", "url": "#features"},
        {"name": "About Us", "url": "#about"},
        {"name": "Pricing", "url": "#pricing"},
        {"name": "Contact", "url": "#contact"},
    ]
    
    social_links_data = [  # <-- GOOD INDENTATION (4 spaces)
        {"name": "LinkedIn", "icon_class": "fab fa-linkedin", "url": "#"},
        {"name": "Facebook", "icon_class": "fab fa-facebook", "url": "#"},
        {"name": "Twitter", "icon_class": "fab fa-twitter", "url": "#"},
        {"name": "Instagram", "icon_class": "fab fa-instagram", "url": "#"},
    ]
    current_year = datetime.date.today().year
    copyright_text = f"© {current_year} Smart Sorter. All rights reserved. | Privacy Policy | Terms of Service"

    
    # Check if we have products, if not create them (Prototype convenience)
    # Product model removed in favor of Category model
    products = []

    # --- Put ALL data into ONE context dictionary ---
    context = {
        "nav_links": nav_links_data,
        "slider_items": slider_items_data,
        "how_it_works_steps": how_it_works_steps_data,
        "quick_links": quick_links_data,
        "social_links": social_links_data,
        "copyright": copyright_text,
        "products": products
    }
    
    return render(request, 'home.html', context)

# --- 2. Loop test view (unchanged) ---
def loop_test_view(request):
    task_list = ['Learn Django models', 'Practice Python loops', 'Build a new feature', 'Test forloop.last']
    context = {'tasks': task_list}
    return render(request, 'loops.html', context)

# --- 3. post_detail_view (unchanged) ---
def post_detail_view(request, post_id):
    return HttpResponse(f"You are viewing the detail page for post ID: {post_id}")

# --- 4. user_profile_view (unchanged) ---
def user_profile_view(request, username):
    return HttpResponse(f"<h1>Profile for: {username}</h1>")

# --- 5. post_slug_view (unchanged) ---
def post_slug_view(request, post_slug):
    return HttpResponse(f"You are viewing the post with slug: {post_slug}")

# --- 6. item_detail_view (unchanged) ---
def item_detail_view(request, item_uuid):
    return HttpResponse(f"Details for item with UUID: {item_uuid}")

# --- 7. Manage Categories View (UC 2.1) ---
@login_required
def manage_categories_view(request):
    # Default suggestions for users to quick-add
    DEFAULT_SUGGESTIONS = ['Groceries', 'Rent', 'Utilities', 'Entertainment', 'Dining Out', 'Transport', 'Healthcare', 'Shopping']
    
    if request.method == 'POST':
        if 'add_category' in request.POST:
            category_name = request.POST.get('category_name', '').strip()
            if category_name:
                try:
                    Category.objects.create(user=request.user, name=category_name)
                    messages.success(request, f"Category '{category_name}' added successfully!")
                except IntegrityError:
                    messages.error(request, f"Category '{category_name}' already exists.")
        
        elif 'delete_category' in request.POST:
            category_id = request.POST.get('category_id')
            try:
                category = Category.objects.get(id=category_id, user=request.user)
                category.delete()
                messages.success(request, "Category deleted successfully.")
            except Category.DoesNotExist:
                messages.error(request, "Category could not be found.")
            
        return redirect('manage_categories')

    # Get user's categories
    user_categories = Category.objects.filter(user=request.user).order_by('name')
    existing_names = set(c.name for c in user_categories)
    
    # Filter suggestions to only show ones the user hasn't added yet
    suggestions = [s for s in DEFAULT_SUGGESTIONS if s not in existing_names]

    context = {
        'categories': user_categories,
        'suggestions': suggestions[:5], # Show top 5 unused suggestions
    }
    return render(request, 'manage_categories.html', context)
