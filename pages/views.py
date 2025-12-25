from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Category
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, FormView
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

    # --- Data for "How It Works" (Updated with FA icons) ---
    how_it_works_steps_data = [
        {
            "icon": "fa-upload",
            "title": "Upload Your File",
            "description": "Simply drag and drop your transaction files. We support CSV, Excel, PDF, and more. No formatting required!"
        },
        {
            "icon": "fa-sync-alt",
            "title": "Smart Sorting",
            "description": "Our AI-powered engine automatically cleans, categorizes, and organizes your data with incredible accuracy."
        },
        {
            "icon": "fa-chart-line",
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


# --- 8. Upload Transactions View (UC 3.1) - Class-Based View ---
class TransactionUploadView(LoginRequiredMixin, FormView):
    """
    Handles CSV file upload for bulk transaction import.
    Follows OOP best practices using Django's FormView.
    """
    template_name = 'upload_transactions.html'
    form_class = None  # Set dynamically to avoid circular import
    
    # Required CSV headers (case-insensitive matching)
    REQUIRED_HEADERS = ['date', 'description', 'amount']
    OPTIONAL_HEADERS = ['notes']
    
    def get_form_class(self):
        """Lazy import to avoid circular dependency."""
        from .forms import TransactionUploadForm
        return TransactionUploadForm
    
    def get_context_data(self, **kwargs):
        """Add stats and transactions to context."""
        context = super().get_context_data(**kwargs)
        context['stats'] = self.request.session.pop('upload_stats', {
            'total_rows': 0,
            'successful': 0,
            'errors': [],
            'processed': False
        })
        
        # Get recently imported transactions for preview
        transaction_ids = self.request.session.pop('imported_transaction_ids', [])
        if transaction_ids:
            from .models import Transaction
            context['transactions'] = Transaction.objects.filter(
                id__in=transaction_ids,
                user=self.request.user
            ).order_by('-date')[:50]  # Limit to 50 for display
        else:
            context['transactions'] = None
            
        return context
    
    def form_valid(self, form):
        """Process the uploaded CSV file."""
        from .models import Transaction
        import csv
        import io
        from datetime import datetime
        from decimal import Decimal, InvalidOperation
        
        stats = {
            'total_rows': 0,
            'successful': 0,
            'errors': [],
            'processed': False
        }
        
        uploaded_file = form.cleaned_data['file']
        
        try:
            # Read CSV content
            file_content = uploaded_file.read().decode('utf-8-sig')  # Handle BOM
            csv_reader = csv.DictReader(io.StringIO(file_content))
            
            # Normalize headers (lowercase, strip whitespace)
            if csv_reader.fieldnames:
                actual_headers = [h.lower().strip() for h in csv_reader.fieldnames]
            else:
                messages.error(self.request, "CSV file appears to be empty or has no headers.")
                return self.form_invalid(form)
            
            # Validate required headers
            missing_headers = [
                h.capitalize() for h in self.REQUIRED_HEADERS 
                if h not in actual_headers
            ]
            
            if missing_headers:
                messages.error(
                    self.request, 
                    f"Missing required column(s): {', '.join(missing_headers)}. "
                    f"Your CSV must have: Date, Description, Amount, Notes (optional)"
                )
                return self.form_invalid(form)
            
            # Process each row
            rows = list(csv_reader)
            stats['total_rows'] = len(rows)
            transactions_to_create = []
            
            for row_num, row in enumerate(rows, start=2):
                # Skip empty rows
                if not any(row.values()):
                    continue
                
                # Normalize row keys
                row_normalized = {
                    k.lower().strip(): v.strip() if v else '' 
                    for k, v in row.items()
                }
                
                # Parse date (try multiple formats)
                date_str = row_normalized.get('date', '')
                parsed_date = self._parse_date(date_str)
                
                if not parsed_date:
                    stats['errors'].append(
                        f"Row {row_num}: Invalid date '{date_str}'. "
                        "Use formats like YYYY-MM-DD or DD/MM/YYYY."
                    )
                    continue
                
                # Parse description
                description = row_normalized.get('description', '')
                if not description:
                    stats['errors'].append(f"Row {row_num}: Description cannot be empty.")
                    continue
                
                # Parse amount
                amount = self._parse_amount(row_normalized.get('amount', ''))
                if amount is None:
                    stats['errors'].append(
                        f"Row {row_num}: Invalid amount '{row_normalized.get('amount', '')}'. "
                        "Must be a number."
                    )
                    continue
                
                # Get optional notes
                notes = row_normalized.get('notes', '') or None
                
                # Create transaction object
                transactions_to_create.append(Transaction(
                    user=self.request.user,
                    date=parsed_date,
                    description=description[:255],
                    amount=amount,
                    notes=notes
                ))
                stats['successful'] += 1
            
            # Bulk create transactions
            created_transactions = []
            if transactions_to_create:
                created_transactions = Transaction.objects.bulk_create(transactions_to_create)
            
            stats['processed'] = True
            
            # Store transaction IDs in session for preview
            self.request.session['imported_transaction_ids'] = [
                t.id for t in created_transactions
            ]
            self.request.session['upload_stats'] = stats
            
            # Show success/warning messages
            if stats['successful'] > 0:
                messages.success(
                    self.request, 
                    f"Successfully imported {stats['successful']} transaction(s)!"
                )
            
            if stats['errors']:
                messages.warning(
                    self.request, 
                    f"{len(stats['errors'])} row(s) had issues and were skipped."
                )
            
            if stats['successful'] == 0 and not stats['errors']:
                messages.info(self.request, "No transactions were found in the file.")
                
        except UnicodeDecodeError:
            messages.error(
                self.request, 
                "Unable to read file. Please ensure it's saved as UTF-8 encoded CSV."
            )
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request, f"An error occurred while processing: {str(e)}")
            return self.form_invalid(form)
        
        # Redirect to self to show results (PRG pattern)
        return redirect('upload_transactions')
    
    def form_invalid(self, form):
        """Handle invalid form submission."""
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, error)
        return super().form_invalid(form)
    
    def _parse_date(self, date_str):
        """Parse date string trying multiple formats."""
        from datetime import datetime
        date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%m-%d-%Y']
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None
    
    def _parse_amount(self, amount_str):
        """Parse amount string, handling currency symbols."""
        from decimal import Decimal, InvalidOperation
        cleaned = amount_str.replace(',', '').replace('$', '').replace('£', '').replace('€', '')
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None


# Keep the old function for backward compatibility during transition
def upload_transactions_view(request):
    """Deprecated: Use TransactionUploadView instead."""
    return TransactionUploadView.as_view()(request)


# --- 4. NEW Class-Based Views for Modules ---

class AISortingView(LoginRequiredMixin, TemplateView):
    template_name = 'ai_sorting.html'

class AnalyticsDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'analytics_dashboard.html'

