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
from django.conf import settings
from django.http import HttpResponse, JsonResponse
import json

from .models import Category, Transaction, UploadedFile
from .forms import TransactionUploadForm

class HomeView(TemplateView):
    """
    Shows a public landing page to visitors and a lightweight workflow
    dashboard to authenticated users.
    """
    template_name = 'home.html'

    def get_template_names(self):
        if self.request.user.is_authenticated:
            return ['dashboard_home.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not self.request.user.is_authenticated:
            return context

        user = self.request.user
        category_count = Category.objects.filter(user=user).count()
        total_count = Transaction.objects.filter(user=user).count()
        from django.db.models import Q
        uncategorized_count = Transaction.objects.filter(
            Q(category__isnull=True) | Q(category__name='Uncategorized'),
            user=user
        ).count()
        categorized_count = total_count - uncategorized_count

        if category_count == 0:
            next_action = {
                'title': 'Start with categories',
                'description': 'Create a few spending labels so AI sorting has a clean target list.',
                'url_name': 'manage_categories',
                'label': 'Create Categories',
                'icon': 'fa-tags',
            }
        elif total_count == 0:
            next_action = {
                'title': 'Upload your first statement',
                'description': 'Import a NayaPay statement or the standard CSV template to begin.',
                'url_name': 'upload_transactions',
                'label': 'Upload CSV',
                'icon': 'fa-file-import',
            }
        elif uncategorized_count > 0:
            next_action = {
                'title': 'AI sorting is ready',
                'description': f'{uncategorized_count} transaction(s) are waiting for categorization.',
                'url_name': 'ai_sorting',
                'label': 'Run AI Sorting',
                'icon': 'fa-robot',
            }
        else:
            next_action = {
                'title': 'Your data is ready for analysis',
                'description': 'All imported transactions are categorized. Review trends in analytics.',
                'url_name': 'analytics_dashboard',
                'label': 'View Analytics',
                'icon': 'fa-chart-pie',
            }

        profile = getattr(user, 'profile', None)
        if profile is None:
            from accounts.models import UserProfile
            profile, _ = UserProfile.objects.get_or_create(user=user)

        provider_display = profile.get_ai_provider_display()
        provider_key_map = {
            'gemini': (profile.gemini_api_key, getattr(settings, 'GEMINI_API_KEY', None), profile.gemini_model),
            'openai': (profile.openai_api_key, getattr(settings, 'OPENAI_API_KEY', None), profile.openai_model),
            'deepseek': (profile.deepseek_api_key, getattr(settings, 'DEEPSEEK_API_KEY', None), profile.deepseek_model),
        }
        user_key, fallback_key, selected_model = provider_key_map.get(
            profile.ai_provider,
            (None, None, 'Unknown model')
        )

        context.update({
            'category_count': category_count,
            'total_count': total_count,
            'categorized_count': categorized_count,
            'uncategorized_count': uncategorized_count,
            'recent_uploads': UploadedFile.objects.filter(user=user).order_by('-upload_date')[:3],
            'recent_transactions': Transaction.objects.filter(user=user).select_related('category')[:5],
            'latest_ai_log': user.ai_telemetry_logs.first(),
            'next_action': next_action,
            'provider_display': provider_display,
            'selected_model': selected_model,
            'ai_key_configured': bool(user_key or fallback_key),
        })
        return context



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
                if category.name != 'Uncategorized':
                    uncat_obj, _ = Category.objects.get_or_create(user=request.user, name='Uncategorized')
                    Transaction.objects.filter(category=category, user=request.user).update(category=uncat_obj)
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
        has_categories = Category.objects.filter(user=request.user).exclude(name='Uncategorized').exists()
            
        context = {
            'stats': stats,
            'transactions': transactions,
            'has_existing_transactions': has_existing_transactions,
            'has_categories': has_categories,
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
            temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads')
            os.makedirs(temp_dir, exist_ok=True)

            for file_obj in files:
                if not file_obj.name.endswith('.csv'):
                    messages.error(request, f"Skipped '{file_obj.name}': Unsupported file format. Please upload a .csv file.")
                    continue

                uploaded_file_record = UploadedFile.objects.create(
                    user=request.user,
                    filename=file_obj.name
                )
                temp_file_path = os.path.join(temp_dir, f"standard_{request.user.id}_{file_obj.name}")

                try:
                    with open(temp_file_path, 'wb+') as destination:
                        for chunk in file_obj.chunks():
                            destination.write(chunk)

                    from .parser import process_standard_csv
                    records_created, skipped_duplicates, errors = process_standard_csv(
                        temp_file_path, 
                        request.user, 
                        uploaded_file_record
                    )

                    accumulated_stats['successful'] += records_created
                    accumulated_stats['duplicates'] += skipped_duplicates
                    accumulated_stats['total_rows'] += (records_created + skipped_duplicates)
                    accumulated_stats['errors'].extend(errors)

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
        from django.db.models import Q
        uncategorized_count = Transaction.objects.filter(
            Q(category__isnull=True) | Q(category__name='Uncategorized'),
            user=request.user
        ).count()

        total_count = Transaction.objects.filter(user=request.user).count()
        categorized_count = total_count - uncategorized_count

        category_count = Category.objects.filter(user=request.user).count()

        # Get recently classified transactions for results display
        from django.db.models import Case, When, Value, IntegerField
        recent_ai_results = list(Transaction.objects.filter(
            user=request.user,
            is_ai_categorized=True
        ).select_related('category').annotate(
            needs_review=Case(
                When(Q(category__isnull=True) | Q(category__name='Uncategorized'), then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by('needs_review', '-ai_run_id', '-date')[:50])
        
        # Sort in memory: Uncategorized (manual review) first, then absolute amount descending
        recent_ai_results.sort(
            key=lambda t: (
                0 if not t.category or t.category.name == 'Uncategorized' else 1,
                -abs(t.amount)
            )
        )

        # Pass categories for the inline dropdowns
        user_categories = Category.objects.filter(user=request.user).order_by('name')

        from accounts.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        provider_display = profile.get_ai_provider_display()
        if profile.ai_provider == 'gemini':
            model_display = profile.gemini_model or 'gemini-2.0-flash'
        elif profile.ai_provider == 'openai':
            model_display = profile.openai_model or 'gpt-4.1-nano'
        elif profile.ai_provider == 'deepseek':
            model_display = profile.deepseek_model or 'deepseek-chat'
        else:
            model_display = 'unknown'

        context = {
            'uncategorized_count': uncategorized_count,
            'total_count': total_count,
            'categorized_count': categorized_count,
            'category_count': category_count,
            'recent_ai_results': recent_ai_results,
            'user_categories': user_categories,
            'processing_result': request.session.pop('ai_processing_result', None),
            'provider_display': provider_display,
            'model_display': model_display,
            'profile': profile,
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

        from django.db.models import Q
        uncategorized_count = Transaction.objects.filter(
            Q(category__isnull=True) | Q(category__name='Uncategorized'),
            user=request.user
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

            # Get AI provider display info for user notification
            from accounts.models import UserProfile
            try:
                profile = request.user.profile
                provider_display = profile.get_ai_provider_display()
                if profile.ai_provider == 'gemini':
                    model_display = profile.gemini_model or 'gemini-2.0-flash'
                elif profile.ai_provider == 'openai':
                    model_display = profile.openai_model or 'gpt-4.1-nano'
                elif profile.ai_provider == 'deepseek':
                    model_display = profile.deepseek_model or 'deepseek-chat'
                else:
                    model_display = 'unknown'
            except Exception:
                provider_display = "Google Gemini AI"
                model_display = "gemini-2.0-flash"

            if result.total_categorized > 0:
                messages.success(
                    request,
                    f"AI successfully categorized {result.total_categorized} "
                    f"out of {result.total_processed} transactions using {provider_display} ({model_display})!"
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
        import socket
        from urllib.parse import urlparse
        from django.conf import settings

        # Check if local Metabase port is listening
        parsed_url = urlparse(settings.METABASE_SITE_URL)
        host = parsed_url.hostname or 'localhost'
        port = parsed_url.port or 3000
        
        metabase_running = False
        try:
            with socket.create_connection((host, port), timeout=0.8):
                metabase_running = True
        except (socket.timeout, ConnectionRefusedError, OSError):
            metabase_running = False
            
        context['metabase_not_running'] = not metabase_running

        secret_key = settings.METABASE_EMBEDDING_SECRET_KEY
        if not secret_key:
            context['embed_error'] = "Metabase Embedding Key is not configured in .env."
            return context

        # 1. Expense Analysis Dashboard (ID: 2)
        dashboard_id = 2 
        payload = {
            "resource": {"dashboard": dashboard_id},
            "params": {
                "user_id": self.request.user.id  # Passes logged-in user ID
            },
            "exp": int(time.time()) + (60 * 10)  # Link expires in 10 minutes
        }
        
        # 2. AI Performance Telemetry Dashboard (ID: 3)
        current_user_id = str(self.request.user.id)
        current_user_id_int = int(self.request.user.id)
        ai_payload = {
            "resource": {"dashboard": 3},
            "params": {
                "user_id_": current_user_id,
                "userid_(_native_number_)_": current_user_id_int
            },
            "exp": int(time.time()) + (60 * 15)  # 15 minute expiration
        }

        try:
            token = jwt.encode(payload, secret_key, algorithm="HS256")
            context['iframe_url'] = f"{settings.METABASE_SITE_URL}/embed/dashboard/{token}#bordered=false&titled=false&background=false"
            
            ai_token = jwt.encode(ai_payload, secret_key, algorithm="HS256")
            context['ai_iframe_url'] = f"{settings.METABASE_SITE_URL}/embed/dashboard/{ai_token}#bordered=false&titled=false&background=false"
        except Exception as e:
            context['embed_error'] = f"Failed to generate secure embed link: {str(e)}"
            
        context['metabase_builder_url'] = settings.METABASE_SITE_URL
        context['metabase_site_url'] = settings.METABASE_SITE_URL
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
                # Get or create case-insensitively
                category = Category.objects.filter(user=request.user, name__iexact=category_name).first()
                if not category:
                    category = Category.objects.create(user=request.user, name=category_name)
            else:
                # Find the existing category
                category = Category.objects.get(user=request.user, name=category_name)

            # Update the transaction
            original_ai_suggested = transaction.ai_suggested_category
            transaction.category = category
            transaction.ai_suggested_category = None # Clear suggestion once resolved
            transaction.save(update_fields=['category', 'ai_suggested_category'])

            # Bulk update similar transactions if applicable
            from django.db.models import Q
            
            # Find transactions that are uncategorized (null or 'Uncategorized')
            similar_txs = Transaction.objects.filter(
                user=request.user
            ).filter(
                Q(category__isnull=True) | Q(category__name='Uncategorized')
            ).exclude(id=transaction.id)

            similarity_query = Q()
            
            # 1. Match by description
            if transaction.description:
                similarity_query |= Q(description=transaction.description)
                
            # 2. Match by AI suggestion if the user accepted/selected it
            if original_ai_suggested and original_ai_suggested == category.name:
                similarity_query |= Q(ai_suggested_category=original_ai_suggested)

            updated_ids = [transaction.id]
            
            if similarity_query:
                matching_txs = similar_txs.filter(similarity_query)
                for m_tx in matching_txs:
                    m_tx.category = category
                    m_tx.ai_suggested_category = None
                    m_tx.save(update_fields=['category', 'ai_suggested_category'])
                    updated_ids.append(m_tx.id)

            return JsonResponse({
                'status': 'success', 
                'message': f"Category updated to {category.name}",
                'category_id': category.id,
                'category_name': category.name,
                'updated_transaction_ids': updated_ids
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


class TransactionHistoryView(LoginRequiredMixin, TemplateView):
    template_name = 'transaction_history.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Query all user transactions
        tx_qs = Transaction.objects.filter(user=user).select_related('category')

        # Filter by search
        search_query = self.request.GET.get('q', '')
        if search_query:
            tx_qs = tx_qs.filter(description__icontains=search_query)

        # Sort order
        sort_order = self.request.GET.get('sort', 'date_desc')
        if sort_order == 'amount_desc':
            tx_qs = tx_qs.order_by('-amount')
        elif sort_order == 'amount_asc':
            tx_qs = tx_qs.order_by('amount')
        elif sort_order == 'date_asc':
            tx_qs = tx_qs.order_by('date', 'created_at')
        else: # date_desc
            tx_qs = tx_qs.order_by('-date', '-created_at')

        # Limit to 500 rows for high-performance rendering
        transactions = list(tx_qs[:500])
        user_categories = Category.objects.filter(user=user).order_by('name')

        context.update({
            'transactions': transactions,
            'user_categories': user_categories,
            'search_query': search_query,
            'sort_order': sort_order,
        })
        return context
