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
                from django.db import transaction
                try:
                    with transaction.atomic():
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
class TransactionUploadView(LoginRequiredMixin, View):
    """
    Handles CSV file upload for bulk transaction import supporting both
    standard CSV template and NayaPay exported statements.
    """
    template_name = 'upload_transactions.html'

    def get(self, request):
        stats = request.session.pop('upload_stats', {
            'total_rows': 0,
            'successful': 0,
            'errors': [],
            'processed': False
        })
        
        # Get recently imported transactions for preview
        transaction_ids = request.session.pop('imported_transaction_ids', [])
        if transaction_ids:
            transactions = Transaction.objects.filter(
                id__in=transaction_ids,
                user=request.user
            ).order_by('-date')[:50]  # Limit to 50 for display
        else:
            transactions = None

        has_existing_transactions = Transaction.objects.filter(user=request.user).exists()
            
        context = {
            'stats': stats,
            'transactions': transactions,
            'has_existing_transactions': has_existing_transactions,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        import_type = request.POST.get('import_type', 'template')
        
        files = request.FILES.getlist('file')
        if not files or len(files) == 0:
            messages.error(request, "No files selected for import.")
            return redirect('upload_transactions')

        import os
        import hashlib
        from django.conf import settings
        from .models import UploadedFile
        from .parser import process_nayapay_csv

        # Initialize accumulated stats
        accumulated_stats = {
            'total_rows': 0,
            'successful': 0,
            'duplicates': 0,
            'errors': [],
            'processed': True
        }
        imported_transaction_ids = []

        if import_type == 'nayapay':
            temp_dir = os.path.join(settings.BASE_DIR, 'media', 'temp_uploads')
            os.makedirs(temp_dir, exist_ok=True)

            for file_obj in files:
                if not file_obj.name.endswith('.csv'):
                    messages.error(request, f"Skipped '{file_obj.name}': Unsupported file format. Please upload a .csv file.")
                    continue

                uploaded_file_record = UploadedFile.objects.create(
                    user=request.user,
                    filename=file_obj.name
                )
                temp_file_path = os.path.join(temp_dir, f"user_{request.user.id}_{file_obj.name}")

                try:
                    with open(temp_file_path, 'wb+') as destination:
                        for chunk in file_obj.chunks():
                            destination.write(chunk)

                    records_created, skipped_duplicates = process_nayapay_csv(temp_file_path, request.user, uploaded_file_record)
                    
                    accumulated_stats['successful'] += records_created
                    accumulated_stats['duplicates'] += skipped_duplicates
                    accumulated_stats['total_rows'] += (records_created + skipped_duplicates)

                    # Fetch created transaction IDs for preview
                    recent_txs = Transaction.objects.filter(
                        user=request.user, 
                        uploaded_file=uploaded_file_record
                    ).values_list('id', flat=True)
                    imported_transaction_ids.extend(list(recent_txs))

                    if records_created == 0 and skipped_duplicates > 0:
                        uploaded_file_record.delete()

                except Exception as e:
                    uploaded_file_record.delete()
                    accumulated_stats['errors'].append(f"File '{file_obj.name}': {str(e)}")
                finally:
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)

            request.session['upload_stats'] = accumulated_stats
            request.session['imported_transaction_ids'] = imported_transaction_ids

            if accumulated_stats['successful'] > 0:
                msg = f"Successfully parsed NayaPay statement. Formatted and saved {accumulated_stats['successful']} new records."
                if accumulated_stats['duplicates'] > 0:
                    msg += f" Skipped {accumulated_stats['duplicates']} duplicate transactions."
                messages.success(request, msg)
            elif accumulated_stats['duplicates'] > 0:
                messages.info(request, f"Import complete. All {accumulated_stats['duplicates']} transaction(s) were skipped as duplicates.")
            
            for err in accumulated_stats['errors']:
                messages.error(request, err)

            return redirect('upload_transactions')
        
        else:
            # Handle Template CSV upload (generic)
            for file_obj in files:
                if not file_obj.name.endswith('.csv'):
                    messages.error(request, f"Skipped '{file_obj.name}': Unsupported file format. Please upload a .csv file.")
                    continue

                uploaded_file_record = UploadedFile.objects.create(
                    user=request.user,
                    filename=file_obj.name
                )

                try:
                    file_content = file_obj.read().decode('utf-8-sig')
                    csv_reader = csv.DictReader(io.StringIO(file_content))
                    
                    if not csv_reader.fieldnames:
                        accumulated_stats['errors'].append(f"File '{file_obj.name}': Empty file or missing headers.")
                        uploaded_file_record.delete()
                        continue

                    actual_headers = [h.lower().strip() for h in csv_reader.fieldnames]
                    
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
                        accumulated_stats['errors'].append(
                            f"File '{file_obj.name}': Missing required column(s) {', '.join(missing)}."
                        )
                        uploaded_file_record.delete()
                        continue

                    rows = list(csv_reader)
                    accumulated_stats['total_rows'] += len(rows)
                    transactions_to_create = []
                    
                    for row_num, row in enumerate(rows, start=2):
                        if not any(row.values()):
                            continue
                        
                        row_normalized = {
                            k.lower().strip(): v.strip() if v else '' 
                            for k, v in row.items()
                        }
                        
                        date_str = row_normalized.get('date', '')
                        parsed_date = self._parse_date(date_str)
                        if not parsed_date:
                            accumulated_stats['errors'].append(
                                f"File '{file_obj.name}', Row {row_num}: Invalid date '{date_str}'."
                            )
                            continue
                        
                        description = (
                            row_normalized.get('description', '') or 
                            row_normalized.get('raw_description', '')
                        )
                        if not description:
                            accumulated_stats['errors'].append(f"File '{file_obj.name}', Row {row_num}: Description cannot be empty.")
                            continue
                        
                        amount = self._parse_amount(row_normalized.get('amount', ''))
                        if amount is None:
                            accumulated_stats['errors'].append(
                                f"File '{file_obj.name}', Row {row_num}: Invalid amount '{row_normalized.get('amount', '')}'."
                            )
                            continue
                        
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
                        
                        raw_hash_string = f"{request.user.id}|{parsed_date}|{amount}|{description.strip().lower()}"
                        tx_hash = hashlib.sha256(raw_hash_string.encode('utf-8')).hexdigest()
                        
                        if Transaction.objects.filter(user=request.user, tx_hash=tx_hash).exists():
                            accumulated_stats['duplicates'] += 1
                            continue

                        transactions_to_create.append(Transaction(
                            user=request.user,
                            uploaded_file=uploaded_file_record,
                            date=parsed_date,
                            description=description[:255],
                            amount=amount,
                            merchant_name=merchant_name[:100] if merchant_name else None,
                            transaction_type=transaction_type[:50] if transaction_type else None,
                            notes=notes,
                            tx_hash=tx_hash
                        ))
                        accumulated_stats['successful'] += 1
                    
                    created_transactions = []
                    if transactions_to_create:
                        created_transactions = Transaction.objects.bulk_create(transactions_to_create)
                    
                    imported_transaction_ids.extend([t.id for t in created_transactions])

                    if len(transactions_to_create) == 0:
                        uploaded_file_record.delete()

                except UnicodeDecodeError:
                    uploaded_file_record.delete()
                    accumulated_stats['errors'].append(f"File '{file_obj.name}': Unable to read file (encoding error).")
                except Exception as e:
                    uploaded_file_record.delete()
                    accumulated_stats['errors'].append(f"File '{file_obj.name}': {str(e)}")

            request.session['imported_transaction_ids'] = imported_transaction_ids
            request.session['upload_stats'] = accumulated_stats
            
            if accumulated_stats['successful'] > 0:
                msg = f"Successfully imported {accumulated_stats['successful']} transaction(s) using Template!"
                if accumulated_stats['duplicates'] > 0:
                    msg += f" Skipped {accumulated_stats['duplicates']} duplicate(s)."
                messages.success(request, msg)
            elif accumulated_stats['duplicates'] > 0:
                messages.info(request, f"Import complete. All {accumulated_stats['duplicates']} transaction(s) were skipped as duplicates.")
                
            if accumulated_stats['errors']:
                messages.warning(
                    request, 
                    f"{len(accumulated_stats['errors'])} issue(s) occurred during parsing."
                )
                for err in accumulated_stats['errors'][:5]:
                    messages.error(request, err)

            return redirect('upload_transactions')

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

        except ValueError as e:
            messages.error(request, f"Configuration Error: {str(e)}")
        except AIServiceError as e:
            messages.error(request, f"AI Service Error: {str(e)}")
        except Exception as e:
            messages.error(
                request,
                f"AI Sorting encountered an unexpected issue: {str(e)}. Please check your internet connection and try again."
            )

        return redirect('ai_sorting')


class AnalyticsDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'analytics_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        import jwt
        import time
        from django.conf import settings

        secret_key = settings.METABASE_EMBEDDING_SECRET_KEY
        if not secret_key:
            context['embed_error'] = "Metabase Embedding Key is not configured in .env."
            return context

        # Open-source Metabase allows embedding dashboards or questions.
        # Typically, a dashboard is used. Change this ID if your dashboard ID is different.
        dashboard_id = 2 
        
        payload = {
            "resource": {"dashboard": dashboard_id},
            "params": {
                "user_id": self.request.user.id  # Passes logged-in user ID
            },
            "exp": int(time.time()) + (60 * 10)  # Link expires in 10 minutes
        }
        
        try:
            token = jwt.encode(payload, secret_key, algorithm="HS256")
            context['iframe_url'] = f"{settings.METABASE_SITE_URL}/embed/dashboard/{token}#bordered=true&titled=true"
        except Exception as e:
            context['embed_error'] = f"Failed to generate secure embed link: {str(e)}"
            
        return context


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


class DeleteTransactionAPI(LoginRequiredMixin, View):
    """
    Handles AJAX requests to delete a transaction.
    """
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            transaction_id = data.get('transaction_id')
            if not transaction_id:
                return JsonResponse({'status': 'error', 'message': 'Missing transaction ID'}, status=400)
            
            transaction = Transaction.objects.get(id=transaction_id, user=request.user)
            transaction.delete()
            return JsonResponse({
                'status': 'success',
                'message': 'Transaction deleted successfully'
            })
        except Transaction.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Transaction not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class ClearAllTransactionsView(LoginRequiredMixin, View):
    """
    Clears all transactions and uploaded files for the logged-in user.
    """
    def post(self, request, *args, **kwargs):
        from .models import UploadedFile
        try:
            tx_count = Transaction.objects.filter(user=request.user).count()
            Transaction.objects.filter(user=request.user).delete()
            
            file_count = UploadedFile.objects.filter(user=request.user).count()
            UploadedFile.objects.filter(user=request.user).delete()
            
            messages.success(
                request, 
                f"Successfully deleted all data. Cleared {tx_count} transaction(s) and {file_count} upload record(s)."
            )
        except Exception as e:
            messages.error(request, f"Failed to clear history: {str(e)}")
            
        return redirect('upload_transactions')

