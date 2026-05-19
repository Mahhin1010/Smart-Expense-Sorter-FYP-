"""
AI Classification Engine for Smart Transaction Sorter.

This module implements the core intelligence layer that classifies financial
transactions into user-defined spending categories using Google's Gemini API.

Architecture follows the project's SYSTEM_CONTEXT.md specification:
  1. TransactionBatcher — Fetches uncategorized rows, chunks them for API calls.
  2. GeminiClassifier  — Builds structured prompts, calls Gemini, parses JSON.
  3. ResponseValidator — Ensures AI output maps to valid DB categories.
  4. AICategorizationService — Orchestrates the full pipeline (facade pattern).

Design Decisions:
  - Batch size of 25: Balances token budget vs. round-trip latency.
    At ~40 tokens/transaction, 25 rows = 1,000 input tokens — well within
    Gemini Flash's context window with room for the category taxonomy.
  - Strict JSON contract: The prompt enforces a JSON-only response to prevent
    free-text parsing failures at scale.
  - Graceful degradation: Unknown categories → "Uncategorized"; API timeout →
    retry once then fail gracefully. No data loss on errors.
  - Stateless design: Each call is independent. Safe for concurrent users
    and horizontally scalable behind a task queue (Celery) in production.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. DATA TRANSFER OBJECTS
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    """Immutable result from the AI for a single transaction."""
    transaction_id: int
    category_name: str
    confidence: float
    is_valid: bool = True
    error: Optional[str] = None
    suggested_category: Optional[str] = None


@dataclass
class BatchResult:
    """Aggregated results for a full classification run."""
    total_processed: int = 0
    total_categorized: int = 0
    total_low_confidence: int = 0
    total_errors: int = 0
    results: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# 2. TRANSACTION BATCHER
# ---------------------------------------------------------------------------

class TransactionBatcher:
    """
    Fetches uncategorized transactions and splits them into API-friendly
    batches. Batch size is tuned for Gemini Flash token limits.

    For production scale (10k+ transactions), this would feed a Celery
    task queue. For the FYP demo, synchronous processing is acceptable.
    """

    BATCH_SIZE = 25

    @staticmethod
    def get_uncategorized(user):
        """
        Return QuerySet of transactions without an assigned category.
        Uses select_related to avoid N+1 queries if category is accessed.
        """
        from .models import Transaction
        return Transaction.objects.filter(
            user=user,
            category__isnull=True
        ).order_by('date')

    @classmethod
    def create_batches(cls, queryset):
        """
        Yield successive chunks of BATCH_SIZE from the queryset.
        Materializes each chunk to a list for safe iteration.
        """
        transactions = list(queryset)
        for i in range(0, len(transactions), cls.BATCH_SIZE):
            yield transactions[i:i + cls.BATCH_SIZE]

    @staticmethod
    def prepare_batch_payload(batch):
        """
        Convert a batch of Transaction model instances into the dictionary
        format expected by the Gemini prompt.

        Uses every available signal column for maximum classification accuracy:
          - description (Raw_Description from CSV)
          - merchant_name (strongest signal — e.g. "Carrefour" → Groceries)
          - transaction_type (e.g. "Bill Payment" → likely Utilities)
          - amount (contextual — ₹50k at Al-Fatah → Groceries, not Dining)
          - notes/comments (user-provided context — "rent", "monthly bill")
        """
        payload = []
        for txn in batch:
            entry = {
                'id': txn.id,
                'description': txn.description or '',
                'amount': str(txn.amount),
            }
            # Include optional fields only if they contain data
            if txn.merchant_name:
                entry['merchant'] = txn.merchant_name
            if txn.transaction_type:
                entry['type'] = txn.transaction_type
            if txn.notes:
                entry['comments'] = txn.notes
            payload.append(entry)
        return payload


# ---------------------------------------------------------------------------
# 3. GEMINI CLASSIFIER
# ---------------------------------------------------------------------------

class GeminiClassifier:
    """
    Handles all communication with the Google Gemini API.

    Responsibilities:
      - Build the system prompt with the user's category taxonomy.
      - Send structured transaction data and receive JSON classifications.
      - Enforce strict JSON-only output contract.
      - Implement timeout and retry logic per SYSTEM_CONTEXT.md §4.1.

    Model: gemini-2.0-flash (optimized for speed + cost at scale).
    """

    MODEL_NAME = 'gemini-flash-latest'
    MAX_RETRIES = 1
    TIMEOUT_SECONDS = 30  # Per SYSTEM_CONTEXT.md: fail after 10s, but we
                          # allow 30s for larger batches at scale.

    SYSTEM_PROMPT_TEMPLATE = """You are a financial transaction classifier for Pakistani bank statements and digital wallet exports.

TASK: Classify each transaction into ONE category from the user's list below.

RULES:
1. You MUST only use category names from the VALID CATEGORIES list for the `category` field.
2. Use ALL available fields (merchant, description, type, amount, comments) to make your decision.
3. Merchant name is usually the strongest signal. Example: "Carrefour" → Groceries, "Uber" → Transport.
4. Transaction type is a secondary signal. "Bill Payment" → likely Utilities. "Wallet Transfer" → likely Transfers.
5. Comments/notes from the user override other signals. If comments say "rent", classify as the closest rent-related category.
6. If the transaction DOES NOT fit any valid category:
   - Assign "Uncategorized" to the `category` field.
   - Set confidence below 0.5.
   - Provide a generic 1-2 word recommendation in the `suggested_category` field (e.g., "Transport", "Food").
7. If it DOES fit a valid category, leave `suggested_category` as null or empty string.
8. Return ONLY a valid JSON array. No markdown fences, no explanation, no extra text.

VALID CATEGORIES:
{categories}

TRANSACTIONS:
{transactions}

RESPOND WITH ONLY A JSON ARRAY:
[{{"id": <int>, "category": "<string>", "confidence": <float 0.0-1.0>, "suggested_category": "<string or null>"}}]"""

    def __init__(self):
        """Initialize the Gemini client using the API key from settings."""
        self._model = None

    def _get_model(self):
        """Lazy-initialize the Gemini model (avoids import-time side effects)."""
        if self._model is None:
            import google.generativeai as genai

            api_key = getattr(settings, 'GEMINI_API_KEY', None)
            if not api_key:
                raise ValueError(
                    "GEMINI_API_KEY is not configured. "
                    "Add it to your .env file: GEMINI_API_KEY=your_key_here"
                )

            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(self.MODEL_NAME)
        return self._model

    def classify_batch(self, batch_payload: list, category_names: list) -> list[dict]:
        """
        Send a batch of transactions to Gemini and return parsed results.

        Args:
            batch_payload: List of dicts with transaction data (from Batcher).
            category_names: List of the user's category name strings.

        Returns:
            List of dicts: [{"id": int, "category": str, "confidence": float}]

        Raises:
            AIServiceError: On timeout, API failure, or unparseable response.
        """
        model = self._get_model()

        # Build the prompt
        prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
            categories=json.dumps(category_names),
            transactions=json.dumps(batch_payload, indent=2)
        )

        # Attempt classification with retry logic
        last_error = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                start_time = time.time()

                response = model.generate_content(
                    prompt,
                    generation_config={
                        'temperature': 0.1,  # Low creativity — we want deterministic
                        'max_output_tokens': 2048,
                    }
                )

                elapsed = time.time() - start_time
                logger.info(
                    f"Gemini API call completed in {elapsed:.2f}s "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES + 1})"
                )

                # Parse the JSON response
                return self._parse_response(response.text)

            except json.JSONDecodeError as e:
                last_error = f"AI returned invalid JSON: {str(e)}"
                logger.warning(f"JSON parse failed (attempt {attempt + 1}): {e}")
            except Exception as e:
                last_error = f"AI service error: {str(e)}"
                logger.warning(f"API call failed (attempt {attempt + 1}): {e}")

            # Brief pause before retry
            if attempt < self.MAX_RETRIES:
                time.sleep(1)

        raise AIServiceError(
            f"AI Sorting failed after {self.MAX_RETRIES + 1} attempts. "
            f"Last error: {last_error}"
        )

    def _parse_response(self, response_text: str) -> list[dict]:
        """
        Parse Gemini's raw text output into a structured list.
        Handles common LLM quirks: markdown fences, trailing commas, etc.
        """
        text = response_text.strip()

        # Strip markdown code fences if the LLM wraps output
        if text.startswith('```'):
            lines = text.split('\n')
            # Remove first line (```json) and last line (```)
            text = '\n'.join(lines[1:-1]).strip()

        return json.loads(text)


# ---------------------------------------------------------------------------
# 4. RESPONSE VALIDATOR
# ---------------------------------------------------------------------------

class ResponseValidator:
    """
    Validates AI classifications against the user's actual category list.
    Ensures no phantom categories enter the database.

    Per SYSTEM_CONTEXT.md §4.2:
      - If AI suggests a category not in the DB → assign "Uncategorized".
      - If confidence < threshold → assign "Uncategorized".
    """

    CONFIDENCE_THRESHOLD = 0.5

    @classmethod
    def validate(cls, ai_results: list[dict], valid_category_names: set) -> list[ClassificationResult]:
        """
        Validate each AI result against the user's category list.

        Args:
            ai_results: Raw parsed JSON from Gemini.
            valid_category_names: Set of category name strings from the DB.

        Returns:
            List of ClassificationResult dataclass instances.
        """
        validated = []
        for item in ai_results:
            txn_id = item.get('id')
            category = item.get('category', '')
            confidence = float(item.get('confidence', 0.0))
            suggested = item.get('suggested_category', '')
            if not suggested or suggested.lower() == 'null':
                suggested = None

            # Validate the category exists in the user's list
            if category not in valid_category_names:
                validated.append(ClassificationResult(
                    transaction_id=txn_id,
                    category_name='Uncategorized',
                    confidence=confidence,
                    is_valid=False,
                    error=f"AI suggested '{category}' which is not in user's categories",
                    suggested_category=suggested or category # If it hallucinated a category, treat it as a suggestion
                ))
            elif confidence < cls.CONFIDENCE_THRESHOLD or category == 'Uncategorized':
                validated.append(ClassificationResult(
                    transaction_id=txn_id,
                    category_name='Uncategorized',
                    confidence=confidence,
                    is_valid=False,
                    error=f"Low confidence ({confidence:.0%}) or explicitly uncategorized",
                    suggested_category=suggested
                ))
            else:
                validated.append(ClassificationResult(
                    transaction_id=txn_id,
                    category_name=category,
                    confidence=confidence,
                    suggested_category=None
                ))
        return validated


# ---------------------------------------------------------------------------
# 5. ORCHESTRATION SERVICE (FACADE)
# ---------------------------------------------------------------------------

class AICategorizationService:
    """
    Facade that orchestrates the full classification pipeline.

    Workflow (matches sequence diagram seq_ai_process.png):
      1. Fetch user's categories from DB.
      2. Fetch uncategorized transactions.
      3. Batch transactions into groups of 25.
      4. For each batch: call Gemini → validate → collect results.
      5. Bulk-update the DB with new category assignments.
      6. Return a BatchResult summary.

    This is the ONLY class that views.py should interact with.
    """

    def __init__(self):
        self.batcher = TransactionBatcher()
        self.classifier = GeminiClassifier()

    def process_user_transactions(self, user) -> BatchResult:
        """
        Main entry point. Classifies all uncategorized transactions for a user.

        Args:
            user: Django User model instance.

        Returns:
            BatchResult with counts and per-transaction results.
        """
        from .models import Category, Transaction

        result = BatchResult()

        # Step 1: Get user's categories
        user_categories = Category.objects.filter(user=user)
        category_names = list(user_categories.values_list('name', flat=True))

        if not category_names:
            result.errors.append(
                "No categories found. Please create categories before running AI sorting."
            )
            return result

        # Ensure "Uncategorized" exists as a fallback
        uncategorized_cat, _ = Category.objects.get_or_create(
            user=user, name='Uncategorized'
        )
        category_name_set = set(category_names) | {'Uncategorized'}

        # Build a name→object lookup for bulk_update
        category_map = {c.name: c for c in Category.objects.filter(user=user)}

        # Step 2: Get uncategorized transactions
        uncategorized_qs = self.batcher.get_uncategorized(user)
        total_count = uncategorized_qs.count()

        if total_count == 0:
            result.errors.append("No uncategorized transactions found to process.")
            return result

        result.total_processed = total_count

        # Step 3-4: Batch and classify
        transactions_to_update = []

        for batch in self.batcher.create_batches(uncategorized_qs):
            payload = self.batcher.prepare_batch_payload(batch)

            try:
                ai_results = self.classifier.classify_batch(payload, category_names)
                validated = ResponseValidator.validate(ai_results, category_name_set)

                # Build a lookup of transaction_id → Transaction object
                batch_map = {txn.id: txn for txn in batch}

                for classification in validated:
                    txn = batch_map.get(classification.transaction_id)
                    if not txn:
                        continue

                    cat_obj = category_map.get(classification.category_name)
                    if not cat_obj:
                        cat_obj = category_map.get('Uncategorized', uncategorized_cat)

                    txn.category = cat_obj
                    txn.ai_confidence = classification.confidence
                    txn.is_ai_categorized = True
                    txn.ai_suggested_category = classification.suggested_category
                    transactions_to_update.append(txn)

                    if classification.is_valid:
                        result.total_categorized += 1
                    else:
                        result.total_low_confidence += 1

                    result.results.append(classification)

            except AIServiceError as e:
                logger.error(f"Batch classification failed: {e}")
                result.total_errors += len(batch)
                result.errors.append(str(e))

        # Step 5: Bulk update — critical for performance at scale
        # Per SYSTEM_CONTEXT.md §UC-AI-03: DO NOT use for-loop with .save()
        if transactions_to_update:
            Transaction.objects.bulk_update(
                transactions_to_update,
                fields=['category', 'ai_confidence', 'is_ai_categorized', 'ai_suggested_category'],
                batch_size=100  # Django's internal batch size for the UPDATE query
            )
            logger.info(
                f"Bulk-updated {len(transactions_to_update)} transactions for user {user.username}"
            )

        return result


# ---------------------------------------------------------------------------
# 6. CUSTOM EXCEPTIONS
# ---------------------------------------------------------------------------

class AIServiceError(Exception):
    """Raised when the AI classification service fails irrecoverably."""
    pass
