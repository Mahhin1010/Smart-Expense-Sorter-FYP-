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
from django.http import HttpResponse, JsonResponse
import json

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
        # Fetch default suggestions from the database (controlled by Admin)
        from .models import DefaultCategory # Local import to avoid circular dependency if any
        default_categories = DefaultCategory.objects.values_list('name', flat=True)
        
        # Get user's categories
        user_categories = Category.objects.filter(user=request.user).order_by('name')
        existing_names = set(c.name for c in user_categories)
        
        # Filter suggestions (exclude ones the user already has)
        suggestions = [s for s in default_categories if s not in existing_names]

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
    OPTIONAL_HEADERS = ['notes', 'merchant_name', 'transaction_type', 'comments',
                        'raw_description', 'merchant', 'type']

    # Alias map: common CSV column names → our model field names
    HEADER_ALIASES = {
        'raw_description': 'description',
        'merchant_name': 'merchant_name',
        'merchant': 'merchant_name',
        'transaction_type': 'transaction_type',
        'type': 'transaction_type',
        'comments': 'notes',
        'notes': 'notes',
        'memo': 'notes',
    }
    
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
            
            # Validate required headers (check aliases too)
            description_aliases = {'description', 'raw_description'}
            has_description = bool(description_aliases & set(actual_headers))
            has_date = 'date' in actual_headers
            has_amount = 'amount' in actual_headers
            
            missing = []
            if not has_date:
                missing.append('Date')
            if not has_description:
                missing.append('Description')
            if not has_amount:
                missing.append('Amount')
            
            if missing:
                messages.error(
                    self.request, 
                    f"Missing required column(s): {', '.join(missing)}. "
                    f"Your CSV must have: Date, Description, Amount"
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
                
                # Parse date (try multiple formats including datetime)
                date_str = row_normalized.get('date', '')
                parsed_date = self._parse_date(date_str)
                
                if not parsed_date:
                    stats['errors'].append(
                        f"Row {row_num}: Invalid date '{date_str}'. "
                        "Use formats like YYYY-MM-DD or DD/MM/YYYY."
                    )
                    continue
                
                # Parse description (check aliases)
                description = (
                    row_normalized.get('description', '') or 
                    row_normalized.get('raw_description', '')
                )
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
                
                # Extract optional signal fields via alias mapping
                merchant_name = (
                    row_normalized.get('merchant_name', '') or 
                    row_normalized.get('merchant', '') or None
                )
                transaction_type = (
                    row_normalized.get('transaction_type', '') or 
                    row_normalized.get('type', '') or None
                )
                notes = (
                    row_normalized.get('notes', '') or 
                    row_normalized.get('comments', '') or 
                    row_normalized.get('memo', '') or None
                )
                
                # Create transaction object with all available fields
                transactions_to_create.append(Transaction(
                    user=self.request.user,
                    date=parsed_date,
                    description=description[:255],
                    amount=amount,
                    merchant_name=merchant_name[:100] if merchant_name else None,
                    transaction_type=transaction_type[:50] if transaction_type else None,
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
        """Parse date string trying multiple formats including datetime."""
        date_formats = [
            '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%m-%d-%Y',
            '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S',
            '%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S',
        ]
        for fmt in date_formats:
            try:
                return datetime.datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None
    
    def _parse_amount(self, amount_str):
        """Parse amount string, handling currency symbols including PKR."""
        cleaned = (amount_str
                   .replace(',', '')
                   .replace('$', '')
                   .replace('£', '')
                   .replace('€', '')
                   .replace('₹', '')
                   .replace('PKR', '')
                   .replace('Rs.', '')
                   .replace('Rs', '')
                   .strip())
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None





# --- 4. AI SORTING VIEW (UC 3.2) ---

class AISortingView(LoginRequiredMixin, View):
    """
    Handles the AI-powered transaction classification workflow.

    GET:  Renders the AI Sorting page with stats on uncategorized transactions.
    POST: Triggers the classification pipeline via AICategorizationService.
    """
    template_name = 'ai_sorting.html'

    def get(self, request):
        """Display the AI sorting page with current transaction stats."""
        uncategorized_count = Transaction.objects.filter(
            user=request.user,
            category__isnull=True
        ).count()

        total_count = Transaction.objects.filter(user=request.user).count()

        categorized_count = Transaction.objects.filter(
            user=request.user,
            category__isnull=False
        ).count()

        category_count = Category.objects.filter(user=request.user).count()

        # Get recently classified transactions for results display
        recent_ai_results = Transaction.objects.filter(
            user=request.user,
            is_ai_categorized=True
        ).select_related('category').order_by('-created_at')[:50]

        # Pass categories for the inline dropdowns
        user_categories = Category.objects.filter(user=request.user).order_by('name')

        context = {
            'uncategorized_count': uncategorized_count,
            'total_count': total_count,
            'categorized_count': categorized_count,
            'category_count': category_count,
            'recent_ai_results': recent_ai_results,
            'user_categories': user_categories,
            'processing_result': request.session.pop('ai_processing_result', None),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Trigger AI classification for all uncategorized transactions."""
        from .ai_engine import AICategorizationService, AIServiceError

        # Pre-flight checks
        category_count = Category.objects.filter(user=request.user).count()
        if category_count == 0:
            messages.error(
                request,
                "You need to create spending categories before AI sorting. "
                "Go to Manage Categories first."
            )
            return redirect('ai_sorting')

        uncategorized_count = Transaction.objects.filter(
            user=request.user,
            category__isnull=True
        ).count()

        if uncategorized_count == 0:
            messages.info(request, "All transactions are already categorized!")
            return redirect('ai_sorting')

        # Run the classification pipeline
        try:
            service = AICategorizationService()
            result = service.process_user_transactions(request.user)

            # Store results in session for display after redirect
            request.session['ai_processing_result'] = {
                'total_processed': result.total_processed,
                'total_categorized': result.total_categorized,
                'total_low_confidence': result.total_low_confidence,
                'total_errors': result.total_errors,
                'errors': result.errors[:5],
            }

            if result.total_categorized > 0:
                messages.success(
                    request,
                    f"AI successfully categorized {result.total_categorized} "
                    f"out of {result.total_processed} transactions!"
                )
            if result.total_low_confidence > 0:
                messages.warning(
                    request,
                    f"{result.total_low_confidence} transaction(s) had low confidence "
                    f"and were marked as 'Uncategorized' for manual review."
                )
            if result.total_errors > 0:
                messages.error(
                    request,
                    f"{result.total_errors} transaction(s) could not be processed."
                )
            for error in result.errors[:3]:
                messages.error(request, error)

        except AIServiceError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(
                request,
                "AI Sorting delayed. Please refresh and try again."
            )

        return redirect('ai_sorting')


class AnalyticsDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'analytics_dashboard.html'

class AboutView(TemplateView):
    template_name = 'about.html'

class FeaturesView(TemplateView):
    template_name = 'features.html'

# Auto-reload trigger for .env file update

class UpdateTransactionCategoryAPI(LoginRequiredMixin, View):
    """
    Handles AJAX requests to update a transaction's category inline.
    Can also auto-create a category if 'create_new' is passed.
    """
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            transaction_id = data.get('transaction_id')
            category_name = data.get('category_name')
            create_new = data.get('create_new', False)

            if not transaction_id or not category_name:
                return JsonResponse({'status': 'error', 'message': 'Missing data'}, status=400)

            transaction = Transaction.objects.get(id=transaction_id, user=request.user)
            category_name = category_name.strip()

            if create_new:
                # Get or create the category (ignoring case if possible, but exact match for now)
                category, created = Category.objects.get_or_create(
                    user=request.user, 
                    name=category_name
                )
            else:
                # Find the existing category
                category = Category.objects.get(user=request.user, name=category_name)

            # Update the transaction
            transaction.category = category
            transaction.ai_suggested_category = None # Clear suggestion once resolved
            transaction.save(update_fields=['category', 'ai_suggested_category'])

            return JsonResponse({
                'status': 'success', 
                'message': f"Category updated to {category.name}",
                'category_id': category.id,
                'category_name': category.name
            })

        except Transaction.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Transaction not found'}, status=404)
        except Category.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Category not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
