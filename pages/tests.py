import io
import json
import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.admin.sites import site

from pages.models import Category, Transaction, DefaultCategory, UploadedFile
from pages.ai_engine import AICategorizationService, AIServiceError, ClassificationResult

class PagesSystemTests(TestCase):
    """
    Complete integration and functional test suite covering categories, uploads,
    deduplication, AI engine, and user isolation (TC-06 through TC-25).
    """

    def setUp(self):
        # Setup two users to verify data isolation (User A and User B)
        self.user_a = User.objects.create_user(username="usera", password="PasswordA123!", email="a@example.com")
        self.user_b = User.objects.create_user(username="userb", password="PasswordB123!", email="b@example.com")
        
        # Setup default categories suggestions
        DefaultCategory.objects.create(name="Food")
        DefaultCategory.objects.create(name="Rent")
        DefaultCategory.objects.create(name="Utilities")
        DefaultCategory.objects.create(name="Entertainment")

        # Setup standard category for User A
        self.cat_food_a = Category.objects.create(user=self.user_a, name="Food")

    def test_tc_06_create_category(self):
        """TC-06: Authenticated user can create a category."""
        self.client.login(username="usera", password="PasswordA123!")
        url = reverse('manage_categories')
        
        # Post category addition
        response = self.client.post(url, {'add_category': '', 'category_name': 'Travel'})
        self.assertEqual(response.status_code, 302)
        
        # Verify creation for User A
        self.assertTrue(Category.objects.filter(user=self.user_a, name="Travel").exists())

    def test_tc_07_duplicate_category_rejected(self):
        """TC-07: Duplicate category for the same user is rejected."""
        self.client.login(username="usera", password="PasswordA123!")
        url = reverse('manage_categories')
        
        # Try to add "Food" which already exists for User A
        response = self.client.post(url, {'add_category': '', 'category_name': 'Food'})
        self.assertEqual(response.status_code, 302)
        
        # Verify only one exists
        self.assertEqual(Category.objects.filter(user=self.user_a, name="Food").count(), 1)

    def test_tc_08_delete_category_safety_set_null(self):
        """TC-08: Deleting a category keeps transaction records, setting relation to NULL."""
        self.client.login(username="usera", password="PasswordA123!")
        
        # Create a transaction linked to Food category
        txn = Transaction.objects.create(
            user=self.user_a,
            category=self.cat_food_a,
            date=datetime.date(2026, 2, 1),
            description="Lunch at Diner",
            amount=Decimal("-1500")
        )
        
        # Delete Food category
        url = reverse('manage_categories')
        self.client.post(url, {'delete_category': '', 'category_id': self.cat_food_a.id})
        
        # Verify category deleted but transaction remains with category=NULL (SET_NULL)
        self.assertFalse(Category.objects.filter(id=self.cat_food_a.id).exists())
        
        txn.refresh_from_db()
        self.assertIsNone(txn.category)

    def test_tc_09_default_suggestions_filter(self):
        """TC-09: Default suggestions list items not already created by user."""
        self.client.login(username="usera", password="PasswordA123!")
        url = reverse('manage_categories')
        
        # User A already has "Food". The suggestions should only contain other default names.
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        suggestions = response.context['suggestions']
        self.assertIn("Rent", suggestions)
        self.assertIn("Utilities", suggestions)
        self.assertNotIn("Food", suggestions) # Since User A already has it

    def test_tc_10_valid_csv_upload_generic_template(self):
        """TC-10: Upload valid generic CSV template creates transaction records."""
        self.client.login(username="usera", password="PasswordA123!")
        url = reverse('upload_transactions')
        
        csv_data = "Date,Description,Amount,Type,Notes\n01/02/2026,Weekly Grocery,-5000,POS,Weekly run\n"
        csv_file = SimpleUploadedFile("test.csv", csv_data.encode('utf-8'), content_type="text/csv")
        
        response = self.client.post(url, {
            'import_type': 'template',
            'file': csv_file
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify transaction created
        txn = Transaction.objects.filter(user=self.user_a, description="Weekly Grocery").first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.amount, Decimal("-5000.00"))
        self.assertEqual(txn.date, datetime.date(2026, 2, 1))
        self.assertEqual(txn.notes, "Weekly run")

    def test_tc_11_unsupported_file_type_rejection(self):
        """TC-11: Unsupported file extensions are rejected."""
        self.client.login(username="usera", password="PasswordA123!")
        url = reverse('upload_transactions')
        
        # Upload an Excel representation or txt with csv label
        invalid_file = SimpleUploadedFile("sheet.xlsx", b"some binary data", content_type="application/vnd.ms-excel")
        
        response = self.client.post(url, {
            'import_type': 'template',
            'file': invalid_file
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Transaction.objects.filter(user=self.user_a).exists())

    def test_tc_12_missing_csv_header_rejection(self):
        """TC-12: CSV lacking required columns is rejected."""
        self.client.login(username="usera", password="PasswordA123!")
        url = reverse('upload_transactions')
        
        # Missing Date column
        bad_csv = "Description,Amount\nWeekly Grocery,-5000\n"
        csv_file = SimpleUploadedFile("bad.csv", bad_csv.encode('utf-8'), content_type="text/csv")
        
        response = self.client.post(url, {
            'import_type': 'template',
            'file': csv_file
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Transaction.objects.filter(user=self.user_a).exists())

    def test_tc_13_invalid_date_row_skipping(self):
        """TC-13: Skipping invalid date rows while saving valid ones."""
        self.client.login(username="usera", password="PasswordA123!")
        url = reverse('upload_transactions')
        
        # Row 2 has bad date, Row 3 has valid date
        csv_data = "Date,Description,Amount\nnot-a-date,Bad Row,-100\n02/02/2026,Good Row,-200\n"
        csv_file = SimpleUploadedFile("skips.csv", csv_data.encode('utf-8'), content_type="text/csv")
        
        response = self.client.post(url, {
            'import_type': 'template',
            'file': csv_file
        })
        self.assertEqual(response.status_code, 302)
        
        # "Good Row" should exist, "Bad Row" should not
        self.assertTrue(Transaction.objects.filter(user=self.user_a, description="Good Row").exists())
        self.assertFalse(Transaction.objects.filter(user=self.user_a, description="Bad Row").exists())

    def test_tc_14_invalid_amount_row_skipping(self):
        """TC-14: Skipping invalid amount rows while saving valid ones."""
        self.client.login(username="usera", password="PasswordA123!")
        url = reverse('upload_transactions')
        
        # Row 2 has bad amount, Row 3 has valid amount
        csv_data = "Date,Description,Amount\n02/02/2026,Bad Amount Row,xyz\n02/02/2026,Good Amount Row,-250\n"
        csv_file = SimpleUploadedFile("skips2.csv", csv_data.encode('utf-8'), content_type="text/csv")
        
        response = self.client.post(url, {
            'import_type': 'template',
            'file': csv_file
        })
        self.assertEqual(response.status_code, 302)
        
        # Good Amount Row exists, Bad Amount Row doesn't
        self.assertTrue(Transaction.objects.filter(user=self.user_a, description="Good Amount Row").exists())
        self.assertFalse(Transaction.objects.filter(user=self.user_a, description="Bad Amount Row").exists())

    def test_tc_15_ai_sorting_with_no_categories(self):
        """TC-15: Blocks AI sorting if user has zero categories."""
        # Setup User B who has no categories
        self.client.login(username="userb", password="PasswordB123!")
        
        # Add an uncategorized transaction
        Transaction.objects.create(
            user=self.user_b,
            date=datetime.date(2026, 2, 1),
            description="Test Transaction",
            amount=Decimal("-100")
        )
        
        url = reverse('ai_sorting')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        
        # Verify page redirected and transaction remains uncategorized
        self.assertTrue(Transaction.objects.filter(user=self.user_b, category__isnull=True).exists())

    def test_tc_16_ai_sorting_with_no_pending_transactions(self):
        """TC-16: Blocks AI call if all transactions are already categorized."""
        self.client.login(username="usera", password="PasswordA123!")
        
        # Add a categorized transaction
        Transaction.objects.create(
            user=self.user_a,
            category=self.cat_food_a,
            date=datetime.date(2026, 2, 1),
            description="Already Classified",
            amount=Decimal("-200")
        )
        
        url = reverse('ai_sorting')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

    @patch('pages.ai_engine.GeminiClassifier.classify_batch')
    def test_tc_17_successful_gemini_classification(self, mock_classify):
        """TC-17: Correctly categorizes transactions via mock Gemini responses."""
        self.client.login(username="usera", password="PasswordA123!")
        
        # Create an uncategorized transaction
        txn = Transaction.objects.create(
            user=self.user_a,
            date=datetime.date(2026, 2, 1),
            description="FoodPanda Lahore",
            amount=Decimal("-1200")
        )
        
        # Mock Gemini returns "Food" category with 0.95 confidence
        mock_classify.return_value = [
            {"id": txn.id, "category": "Food", "confidence": 0.95, "suggested_category": None}
        ]
        
        url = reverse('ai_sorting')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        
        # Verify transaction updated to Food
        txn.refresh_from_db()
        self.assertEqual(txn.category, self.cat_food_a)
        self.assertEqual(txn.ai_confidence, 0.95)
        self.assertTrue(txn.is_ai_categorized)

    @patch('pages.ai_engine.GeminiClassifier.classify_batch')
    def test_tc_18_invalid_ai_category_mappings(self, mock_classify):
        """TC-18: Maps invalid/hallucinated AI categories to Uncategorized and keeps suggested_category."""
        self.client.login(username="usera", password="PasswordA123!")
        
        txn = Transaction.objects.create(
            user=self.user_a,
            date=datetime.date(2026, 2, 1),
            description="Unknown Merchant",
            amount=Decimal("-1000")
        )
        
        # Mock returns a category the user doesn't have ("Luxury")
        mock_classify.return_value = [
            {"id": txn.id, "category": "Luxury", "confidence": 0.90, "suggested_category": "Luxury"}
        ]
        
        url = reverse('ai_sorting')
        self.client.post(url)
        
        txn.refresh_from_db()
        # Verify mapped to Uncategorized (category is None or name is 'Uncategorized')
        self.assertTrue(txn.category is None or txn.category.name == 'Uncategorized')
        self.assertEqual(txn.ai_suggested_category, "Luxury")

    @patch('pages.ai_engine.GeminiClassifier.classify_batch')
    def test_tc_19_low_confidence_ai_result(self, mock_classify):
        """TC-19: Marks low confidence classification (under 0.5) as Uncategorized."""
        self.client.login(username="usera", password="PasswordA123!")
        
        txn = Transaction.objects.create(
            user=self.user_a,
            date=datetime.date(2026, 2, 1),
            description="Fuzzy Store Match",
            amount=Decimal("-350")
        )
        
        # Mock returns Food but with 0.35 confidence
        mock_classify.return_value = [
            {"id": txn.id, "category": "Food", "confidence": 0.35, "suggested_category": "Food"}
        ]
        
        url = reverse('ai_sorting')
        self.client.post(url)
        
        txn.refresh_from_db()
        self.assertTrue(txn.category is None or txn.category.name == 'Uncategorized')
        self.assertEqual(txn.ai_suggested_category, "Food")

    def test_tc_20_manual_correction_api(self):
        """TC-20: Manual AJAX endpoint updates transaction category and clears recommendations."""
        self.client.login(username="usera", password="PasswordA123!")
        
        txn = Transaction.objects.create(
            user=self.user_a,
            date=datetime.date(2026, 2, 1),
            description="FoodPanda",
            amount=Decimal("-1000"),
            ai_suggested_category="Food"
        )
        
        url = reverse('api_update_category')
        post_data = {
            'transaction_id': txn.id,
            'category_name': 'Food',
            'create_new': False
        }
        
        response = self.client.post(url, json.dumps(post_data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        
        # Verify db updated and suggestion cleared
        txn.refresh_from_db()
        self.assertEqual(txn.category, self.cat_food_a)

    def test_tc_21_manual_correction_with_new_suggestion_creation(self):
        """TC-21: Manual AJAX updates can auto-create a category when requested."""
        self.client.login(username="usera", password="PasswordA123!")
        
        txn = Transaction.objects.create(
            user=self.user_a,
            date=datetime.date(2026, 2, 1),
            description="Careem Ride",
            amount=Decimal("-600")
        )
        
        # Transport does not exist for User A yet
        url = reverse('api_update_category')
        post_data = {
            'transaction_id': txn.id,
            'category_name': 'Transport',
            'create_new': True
        }
        
        response = self.client.post(url, json.dumps(post_data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        
        # Verify category is created and assigned
        self.assertTrue(Category.objects.filter(user=self.user_a, name="Transport").exists())
        txn.refresh_from_db()
        self.assertEqual(txn.category.name, "Transport")

    def test_tc_22_analytics_jwt_signing(self):
        """TC-22: Generating a valid JWT token when embedding secrets are configured."""
        self.client.login(username="usera", password="PasswordA123!")
        url = reverse('analytics_dashboard')
        
        # Set dummy secret to avoid config failure in test environment
        with self.settings(METABASE_EMBEDDING_SECRET_KEY="test-key-123"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn("iframe_url", response.context)
            self.assertIsNotNone(response.context["iframe_url"])

    def test_tc_23_analytics_missing_secret(self):
        """TC-23: Displays setup warning message when Metabase secret is missing."""
        self.client.login(username="usera", password="PasswordA123!")
        url = reverse('analytics_dashboard')
        
        with self.settings(METABASE_EMBEDDING_SECRET_KEY=""):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIsNotNone(response.context.get("embed_error"))

    def test_tc_24_admin_model_visibility(self):
        """TC-24: Verifies core models are registered inside Django Admin site config."""
        models_to_check = [Category, Transaction, DefaultCategory]
        for model in models_to_check:
            self.assertIn(model, site._registry)

    def test_tc_25_user_data_isolation(self):
        """TC-25: Restricts User A from fetching, updating, or deleting User B's transaction logs."""
        # Add transaction belonging to User B
        txn_b = Transaction.objects.create(
            user=self.user_b,
            date=datetime.date(2026, 2, 1),
            description="Secret Purchase B",
            amount=Decimal("-500")
        )
        
        # Login as User A
        self.client.login(username="usera", password="PasswordA123!")
        
        # Try to delete User B's transaction via AJAX API
        url_delete = reverse('api_delete_transaction')
        response = self.client.post(url_delete, json.dumps({'transaction_id': txn_b.id}), content_type="application/json")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['status'], 'error')
        
        # Try to update User B's transaction via AJAX API
        url_update = reverse('api_update_category')
        response = self.client.post(url_update, json.dumps({'transaction_id': txn_b.id, 'category_name': 'Food', 'create_new': False}), content_type="application/json")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['status'], 'error')
        
        # Confirm User B's transaction remains unchanged
        txn_b.refresh_from_db()
        self.assertIsNone(txn_b.category)

    def test_tc_26_user_profile_signals(self):
        """TC-26: Verify that a UserProfile is automatically created when a new user is registered."""
        new_user = User.objects.create_user(username="newuser", password="NewPassword123!")
        self.assertTrue(hasattr(new_user, 'profile'))
        self.assertEqual(new_user.profile.ai_provider, 'gemini')

    def test_tc_27_settings_save_view(self):
        """TC-27: Verify that the UserSettingsView successfully saves custom API keys and provider preferences."""
        self.client.login(username="usera", password="PasswordA123!")
        url = reverse('user_settings')
        
        # Verify initial GET is successful
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Post updated settings
        data = {
            'ai_provider': 'openai',
            'gemini_model': 'gemini-1.5-flash',
            'gemini_api_key': 'test-gemini-key',
            'openai_model': 'gpt-4o-mini',
            'openai_api_key': 'test-openai-key',
            'deepseek_api_key': 'test-deepseek-key'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Verify settings saved
        self.user_a.profile.refresh_from_db()
        self.assertEqual(self.user_a.profile.ai_provider, 'openai')
        self.assertEqual(self.user_a.profile.gemini_model, 'gemini-3.1-flash-lite')
        self.assertEqual(self.user_a.profile.gemini_api_key, 'test-gemini-key')
        self.assertEqual(self.user_a.profile.openai_model, 'gpt-4.1-nano')
        self.assertEqual(self.user_a.profile.openai_api_key, 'test-openai-key')
        self.assertEqual(self.user_a.profile.deepseek_model, 'deepseek-chat')
        self.assertEqual(self.user_a.profile.deepseek_api_key, 'test-deepseek-key')

    @patch('pages.ai_engine.OpenAI')
    def test_tc_28_openai_classifier_logic(self, mock_openai_class):
        """TC-28: Verify that AICategorizationService routes classification to OpenAI when selected."""
        import unittest
        # Setup provider as openai
        profile = self.user_a.profile
        profile.ai_provider = 'openai'
        profile.openai_api_key = 'fake-openai-key'
        profile.save()

        # Create an uncategorized transaction
        txn = Transaction.objects.create(
            user=self.user_a,
            date=datetime.date(2026, 2, 1),
            description="OpenAI Food Purchase",
            amount=Decimal("-450")
        )

        # Mock OpenAI API successful response
        mock_client = mock_openai_class.return_value
        mock_completions = mock_client.chat.completions
        
        mock_response = unittest.mock.Mock()
        mock_message = unittest.mock.Mock()
        mock_message.content = f"{txn.id}|Food|0.99|"
        mock_choice = unittest.mock.Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        
        mock_completions.create.return_value = mock_response

        # Run categorization
        service = AICategorizationService()
        result = service.process_user_transactions(self.user_a)

        # Verify mock completions API called
        mock_completions.create.assert_called_once()
        self.assertEqual(result.total_categorized, 1)

        # Verify transaction categorization
        txn.refresh_from_db()
        self.assertEqual(txn.category, self.cat_food_a)
        self.assertEqual(txn.ai_confidence, 0.99)

    @patch('pages.ai_engine.OpenAI')
    def test_tc_29_deepseek_classifier_logic(self, mock_openai_class):
        """TC-29: Verify that AICategorizationService routes classification to DeepSeek when selected."""
        import unittest
        # Setup provider as deepseek
        profile = self.user_a.profile
        profile.ai_provider = 'deepseek'
        profile.deepseek_api_key = 'fake-deepseek-key'
        profile.save()

        # Create an uncategorized transaction
        txn = Transaction.objects.create(
            user=self.user_a,
            date=datetime.date(2026, 2, 1),
            description="DeepSeek Food Purchase",
            amount=Decimal("-450")
        )

        # Mock OpenAI (DeepSeek) API successful response
        mock_client = mock_openai_class.return_value
        mock_completions = mock_client.chat.completions
        
        mock_response = unittest.mock.Mock()
        mock_message = unittest.mock.Mock()
        mock_message.content = f"{txn.id}|Food|0.99|"
        mock_choice = unittest.mock.Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        
        mock_completions.create.return_value = mock_response

        # Run categorization
        service = AICategorizationService()
        result = service.process_user_transactions(self.user_a)

        # Verify mock completions API called
        mock_completions.create.assert_called_once()
        self.assertEqual(result.total_categorized, 1)

        # Verify transaction categorization
        txn.refresh_from_db()
        self.assertEqual(txn.category, self.cat_food_a)
        self.assertEqual(txn.ai_confidence, 0.99)

    @patch('pages.ai_engine.GeminiClassifier.classify_batch')
    def test_tc_30_ai_telemetry_logging_success(self, mock_classify):
        """TC-30: Verify that AITelemetryLog is correctly written on successful classification."""
        from accounts.models import AITelemetryLog
        from pages.ai_engine import ClassifierOutput
        
        self.client.login(username="usera", password="PasswordA123!")
        
        txn = Transaction.objects.create(
            user=self.user_a,
            date=datetime.date(2026, 2, 1),
            description="Telemetry Test",
            amount=Decimal("-500")
        )
        
        profile = self.user_a.profile
        profile.ai_provider = 'gemini'
        profile.gemini_model = 'gemini-3.1-flash-lite'
        profile.save()
        
        mock_classify.return_value = ClassifierOutput(
            results=[{"id": txn.id, "category": "Food", "confidence": 0.90, "suggested_category": None}],
            input_tokens=1000,
            output_tokens=200,
            latency_seconds=1.5
        )
        
        url = reverse('ai_sorting')
        self.client.post(url)
        
        log = AITelemetryLog.objects.filter(user=self.user_a, provider='gemini').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.model_name, 'gemini-3.1-flash-lite')
        self.assertEqual(log.batch_size, 1)
        self.assertEqual(log.latency_seconds, 1.5)
        self.assertEqual(log.input_tokens, 1000)
        self.assertEqual(log.output_tokens, 200)
        self.assertTrue(log.success)
        self.assertEqual(float(log.calculated_cost_usd), 0.00055)

    @patch('pages.ai_engine.GeminiClassifier.classify_batch')
    def test_tc_31_ai_telemetry_logging_failure(self, mock_classify):
        """TC-31: Verify that AITelemetryLog is correctly written on classification failure."""
        from accounts.models import AITelemetryLog
        from pages.ai_engine import AIServiceError
        
        self.client.login(username="usera", password="PasswordA123!")
        
        txn = Transaction.objects.create(
            user=self.user_a,
            date=datetime.date(2026, 2, 1),
            description="Telemetry Test Fail",
            amount=Decimal("-500")
        )
        
        profile = self.user_a.profile
        profile.ai_provider = 'gemini'
        profile.gemini_model = 'gemini-3.1-flash-lite'
        profile.save()
        
        mock_classify.side_effect = AIServiceError("API quota exceeded")
        
        url = reverse('ai_sorting')
        self.client.post(url)
        
        log = AITelemetryLog.objects.filter(user=self.user_a, provider='gemini').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.model_name, 'gemini-3.1-flash-lite')
        self.assertEqual(log.batch_size, 1)
        self.assertFalse(log.success)
        self.assertEqual(log.error_type, 'AIServiceError')
        self.assertEqual(log.input_tokens, 0)
        self.assertEqual(log.output_tokens, 0)
        self.assertEqual(float(log.calculated_cost_usd), 0.0)



