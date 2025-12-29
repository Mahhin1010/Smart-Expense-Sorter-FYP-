import csv
import io
import datetime
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, FormView, View
from django.db import IntegrityError
from django.contrib import messages
from django.http import HttpResponse

from .models import Category, Transaction
from .forms import TransactionUploadForm

# --- 1. UPDATED 'home_view' for your Smart Sorter project ---
# --- 1. UPDATED 'home_view' for your Smart Sorter project ---
# --- 1. UPDATED 'HomeView' (CBV) ---
class HomeView(TemplateView):
    """
    Renders the landing page using a Class-Based View (TemplateView).
    Strictly follows OOP principles.
    """
    template_name = 'home.html'



# --- 7. Manage Categories View (UC 2.1) ---
# --- 7. Manage Categories View (CBV) ---
class ManageCategoriesView(LoginRequiredMixin, View):
    """
    Handles listing, adding, and deleting categories using strict OOP.
    Separates GET (display) and POST (action) logic.
    """
    def get(self, request):
        # Default suggestions for users to quick-add
        DEFAULT_SUGGESTIONS = ['Groceries', 'Rent', 'Utilities', 'Entertainment', 'Dining Out', 'Transport', 'Healthcare', 'Shopping']
        
        # Get user's categories
        user_categories = Category.objects.filter(user=request.user).order_by('name')
        existing_names = set(c.name for c in user_categories)
        
        # Filter suggestions
        suggestions = [s for s in DEFAULT_SUGGESTIONS if s not in existing_names]

        context = {
            'categories': user_categories,
            'suggestions': suggestions[:5],
        }
        return render(request, 'manage_categories.html', context)

    def post(self, request):
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


# --- 8. Upload Transactions View (UC 3.1) - Class-Based View ---
class TransactionUploadView(LoginRequiredMixin, FormView):
    """
    Handles CSV file upload for bulk transaction import.
    Follows OOP best practices using Django's FormView.
    """
    template_name = 'upload_transactions.html'
    form_class = TransactionUploadForm
    
    # Required CSV headers (case-insensitive matching)
    REQUIRED_HEADERS = ['date', 'description', 'amount']
    OPTIONAL_HEADERS = ['notes']
    
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
            context['transactions'] = Transaction.objects.filter(
                id__in=transaction_ids,
                user=self.request.user
            ).order_by('-date')[:50]  # Limit to 50 for display
        else:
            context['transactions'] = None
            
        return context
    
    def form_valid(self, form):
        """Process the uploaded CSV file."""
        
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
        date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%m-%d-%Y']
        for fmt in date_formats:
            try:
                return datetime.datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None
    
    def _parse_amount(self, amount_str):
        """Parse amount string, handling currency symbols."""
        cleaned = amount_str.replace(',', '').replace('$', '').replace('£', '').replace('€', '')
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None





# --- 4. NEW Class-Based Views for Modules ---

class AISortingView(LoginRequiredMixin, TemplateView):
    template_name = 'ai_sorting.html'

class AnalyticsDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'analytics_dashboard.html'

