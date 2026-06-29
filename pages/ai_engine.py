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
from openai import OpenAI

logger = logging.getLogger(__name__)


# Static pricing dictionary for AI Performance Benchmarking (USD per single token)
AI_PRICING = {
    "deepseek-chat":       {"input": 0.000000140, "output": 0.000000280},
    "deepseek-v4-flash":   {"input": 0.000000140, "output": 0.000000280},
    "gpt-4.1-nano":        {"input": 0.000000100, "output": 0.000000400},
    "gemini-3.1-flash-lite":{"input": 0.000000250, "output": 0.000001500},
    "gemini-2.5-flash":    {"input": 0.000000300, "output": 0.000002500},
    "gemini-2.0-flash":    {"input": 0.000000300, "output": 0.000002500},  # deprecated alias fallback
    "gemini-1.5-flash":    {"input": 0.000000075, "output": 0.000000300},
}



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


@dataclass
class ClassifierOutput:
    """Returned by every classifier's classify_batch() method."""
    results: list[dict]
    input_tokens: int = 0
    output_tokens: int = 0
    latency_seconds: float = 0.0



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

    BATCH_SIZE = 100

    @staticmethod
    def get_uncategorized(user):
        """
        Return QuerySet of transactions without an assigned category.
        Uses select_related to avoid N+1 queries if category is accessed.
        """
        from django.db.models import Q
        from .models import Transaction
        return Transaction.objects.filter(
            Q(category__isnull=True) | Q(category__name='Uncategorized'),
            user=user
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
        Convert a batch of Transaction model instances into a compact pipe-separated string
        to minimize token footprint and cost.
        Format: ID|Description|Merchant|Type|Amount|Comments
        """
        lines = []
        for txn in batch:
            txn_id = txn.id
            desc = (txn.description or '').replace('|', ' ').replace('\n', ' ').strip()
            amount = str(txn.amount)
            merchant = (txn.merchant_name or '').replace('|', ' ').replace('\n', ' ').strip()
            txn_type = (txn.transaction_type or '').replace('|', ' ').replace('\n', ' ').strip()
            comments = (txn.notes or '').replace('|', ' ').replace('\n', ' ').strip()
            
            lines.append(f"{txn_id}|{desc}|{merchant}|{txn_type}|{amount}|{comments}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. GEMINI CLASSIFIER
# ---------------------------------------------------------------------------

class GeminiClassifier:
    """
    Handles all communication with the Google Gemini API.

    Responsibilities:
      - Build the system prompt with the user's category taxonomy.
      - Send structured transaction data and receive classifications.
      - Implement timeout and retry logic.

    Model: gemini-1.5-flash (optimized for speed + cost at scale).
    """

    MODEL_NAME = 'gemini-3.1-flash-lite'
    TIMEOUT_SECONDS = 30

    SYSTEM_PROMPT_TEMPLATE = """You are a financial transaction classifier for Pakistani bank statements.
Classify each transaction into ONE category from the VALID CATEGORIES list.

RULES:
1. You MUST only use category names from the VALID CATEGORIES list.
2. If the transaction DOES NOT fit any valid category:
   - Assign "Uncategorized" to Category.
   - Set confidence below 0.5.
   - Provide a generic 1-2 word recommendation in SuggestedCategory (e.g., "Transport", "Food").
3. If it DOES fit a valid category, leave SuggestedCategory empty.
4. Output format: Respond ONLY with a pipe-separated (|) text block. One line per transaction, matching the exact format:
   ID|Category|Confidence|SuggestedCategory
   No headers, no markdown fences, no extra text.

VALID CATEGORIES:
{categories}

TRANSACTIONS (Format: ID|Description|Merchant|Type|Amount|Comments):
{transactions}"""

    def __init__(self):
        """Initialize the Gemini client."""
        pass

    def _get_model(self, user=None):
        """Lazy-initialize the Gemini model with custom or default API key."""
        api_key = None
        model_name = self.MODEL_NAME

        if user:
            try:
                from accounts.models import UserProfile
                profile = user.profile
                api_key = profile.gemini_api_key
                if profile.gemini_model:
                    model_name = profile.gemini_model
            except Exception as e:
                logger.warning(f"Failed to fetch user profile: {e}")

        if not api_key:
            api_key = getattr(settings, 'GEMINI_API_KEY', None)

        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. "
                "Add it to your .env file or save it in your Settings page."
            )

        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(model_name)

    def classify_batch(self, batch_payload: str, category_names: list, user=None) -> ClassifierOutput:
        """
        Send a batch of transactions to Gemini and return parsed results and usage metrics.
        """
        model = self._get_model(user)

        # Build the prompt
        prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
            categories=json.dumps(category_names),
            transactions=batch_payload
        )

        # Attempt classification with retry logic and exponential backoff
        last_error = None
        retries = 3
        backoff_delays = [5, 15, 30]

        for attempt in range(retries + 1):
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
                    f"(attempt {attempt + 1}/{retries + 1})"
                )

                # Parse the JSON response
                parsed_results = self._parse_response(response.text)
                
                # Extract usage metadata
                usage = getattr(response, 'usage_metadata', None)
                input_tokens = getattr(usage, 'prompt_token_count', 0) if usage else 0
                output_tokens = getattr(usage, 'candidates_token_count', 0) if usage else 0
                
                return ClassifierOutput(
                    results=parsed_results,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_seconds=elapsed
                )

            except json.JSONDecodeError as e:
                last_error = f"AI returned invalid JSON: {str(e)}"
                logger.warning(f"JSON parse failed (attempt {attempt + 1}): {e}")
            except Exception as e:
                err_str = str(e)
                last_error = f"AI service error: {err_str}"
                logger.warning(f"API call failed (attempt {attempt + 1}): {err_str}")
                
                # If we hit a rate limit, print backoff warning
                if "429" in err_str or "quota" in err_str.lower() or "exhausted" in err_str.lower() or "rate" in err_str.lower():
                    logger.warning("Detected Rate Limit (429) or Quota Exceeded. Applying exponential backoff.")

            # Exponential backoff pause before retry
            if attempt < retries:
                sleep_time = backoff_delays[attempt]
                logger.info(f"Retrying Gemini call in {sleep_time} seconds...")
                time.sleep(sleep_time)

        raise AIServiceError(
            f"AI Sorting failed after {retries + 1} attempts. "
            f"Last error: {last_error}"
        )

    def _parse_response(self, response_text: str) -> list[dict]:
        """
        Parse the compact pipe-separated response text into a list of dictionaries.
        Format expected: ID|Category|Confidence|SuggestedCategory
        """
        results = []
        text = response_text.strip()

        # Strip markdown code blocks if the LLM wraps it
        if text.startswith('```'):
            lines = text.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            text = '\n'.join(lines).strip()

        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue

            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3:
                try:
                    txn_id = int(parts[0])
                    category = parts[1]
                    confidence = float(parts[2])
                    suggested = parts[3] if len(parts) > 3 else ''
                    
                    results.append({
                        "id": txn_id,
                        "category": category,
                        "confidence": confidence,
                        "suggested_category": suggested if suggested and suggested.lower() != 'null' else None
                    })
                except ValueError as e:
                    logger.warning(f"Failed to parse line '{line}': {e}")
        return results


# ---------------------------------------------------------------------------
# 3.1. OPENAI CLASSIFIER [NEW]
# ---------------------------------------------------------------------------

class OpenAIClassifier:
    """
    Handles communication with OpenAI's Chat Completions API using official SDK.
    Locks model usage to gpt-4.1-nano.
    """

    def classify_batch(self, batch_payload: str, category_names: list, user) -> ClassifierOutput:
        profile = user.profile
        api_key = profile.openai_api_key
        if not api_key:
            raise ValueError("OpenAI API key is missing. Please add your key in Settings.")

        # Build prompt using same template
        prompt = GeminiClassifier.SYSTEM_PROMPT_TEMPLATE.format(
            categories=json.dumps(category_names),
            transactions=batch_payload
        )

        client = OpenAI(api_key=api_key)

        last_error = None
        retries = 3
        backoff_delays = [5, 15, 30]

        for attempt in range(retries + 1):
            try:
                start_time = time.time()
                response = client.chat.completions.create(
                    model=profile.openai_model or "gpt-4.1-nano",
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0
                )
                
                elapsed = time.time() - start_time
                logger.info(f"OpenAI API call completed in {elapsed:.2f}s (attempt {attempt + 1}/{retries + 1})")

                content = response.choices[0].message.content
                parsed_results = GeminiClassifier()._parse_response(content)
                
                usage = getattr(response, 'usage', None)
                input_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
                output_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
                
                return ClassifierOutput(
                    results=parsed_results,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_seconds=elapsed
                )

            except Exception as e:
                last_error = f"OpenAI error: {str(e)}"
                logger.warning(f"OpenAI call failed (attempt {attempt + 1}): {e}")

            # Backoff before retry
            if attempt < retries:
                sleep_time = backoff_delays[attempt]
                logger.info(f"Retrying OpenAI call in {sleep_time} seconds...")
                time.sleep(sleep_time)

        raise AIServiceError(
            f"AI Sorting failed after {retries + 1} attempts. Last error: {last_error}"
        )


# ---------------------------------------------------------------------------
# 3.2. DEEPSEEK CLASSIFIER [NEW]
# ---------------------------------------------------------------------------

class DeepSeekClassifier:
    """
    Handles communication with DeepSeek's API using the official openai SDK.
    Locks model usage to deepseek-chat.
    """

    def classify_batch(self, batch_payload: str, category_names: list, user) -> ClassifierOutput:
        profile = user.profile
        api_key = profile.deepseek_api_key
        if not api_key:
            api_key = getattr(settings, 'DEEPSEEK_API_KEY', None)

        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is not configured. "
                "Add it to your .env file or save it in your Settings page."
            )

        # Build prompt using same template
        prompt = GeminiClassifier.SYSTEM_PROMPT_TEMPLATE.format(
            categories=json.dumps(category_names),
            transactions=batch_payload
        )

        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

        last_error = None
        retries = 3
        backoff_delays = [5, 15, 30]

        for attempt in range(retries + 1):
            try:
                start_time = time.time()
                response = client.chat.completions.create(
                    model=profile.deepseek_model or "deepseek-chat",
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0
                )
                
                elapsed = time.time() - start_time
                logger.info(f"DeepSeek API call completed in {elapsed:.2f}s (attempt {attempt + 1}/{retries + 1})")

                content = response.choices[0].message.content
                parsed_results = GeminiClassifier()._parse_response(content)
                
                usage = getattr(response, 'usage', None)
                input_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
                output_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
                
                return ClassifierOutput(
                    results=parsed_results,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_seconds=elapsed
                )

            except Exception as e:
                last_error = f"DeepSeek error: {str(e)}"
                logger.warning(f"DeepSeek call failed (attempt {attempt + 1}): {e}")

            # Backoff before retry
            if attempt < retries:
                sleep_time = backoff_delays[attempt]
                logger.info(f"Retrying DeepSeek call in {sleep_time} seconds...")
                time.sleep(sleep_time)

        raise AIServiceError(
            f"AI Sorting failed after {retries + 1} attempts. Last error: {last_error}"
        )





# ---------------------------------------------------------------------------
# 4. RESPONSE VALIDATOR
# ---------------------------------------------------------------------------

class ResponseValidator:
    """
    Validates AI classifications against the user's actual category list.
    Ensures no phantom categories enter the database.
    """

    CONFIDENCE_THRESHOLD = 0.5

    @classmethod
    def validate(cls, ai_results: list[dict], valid_category_names: set) -> list[ClassificationResult]:
        validated = []
        for item in ai_results:
            txn_id = item.get('id')
            category = item.get('category', '')
            confidence = float(item.get('confidence', 0.0))
            suggested = item.get('suggested_category', '')
            if not suggested or suggested.lower() == 'null':
                suggested = None

            if category not in valid_category_names:
                validated.append(ClassificationResult(
                    transaction_id=txn_id,
                    category_name='Uncategorized',
                    confidence=confidence,
                    is_valid=False,
                    error=f"AI suggested '{category}' which is not in user's categories",
                    suggested_category=suggested or category
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

import requests

class AICategorizationService:
    """
    Facade that orchestrates the full classification pipeline.
    """

    def __init__(self):
        self.batcher = TransactionBatcher()
        self.classifier = GeminiClassifier()

    def process_user_transactions(self, user) -> BatchResult:
        from .models import Category, Transaction
        from accounts.models import UserProfile

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

        # Build lookup dict (lowercase keys for case-insensitive matching)
        category_map = {c.name.lower(): c for c in Category.objects.filter(user=user)}

        # Step 2: Get uncategorized transactions
        uncategorized_qs = self.batcher.get_uncategorized(user)
        total_count = uncategorized_qs.count()

        if total_count == 0:
            result.errors.append("No uncategorized transactions found to process.")
            return result

        result.total_processed = total_count

        # Get AI configuration
        profile, _ = UserProfile.objects.get_or_create(user=user)
        ai_provider = profile.ai_provider

        # Step 3-4: Batch and classify
        transactions_to_update = []
        batches = list(self.batcher.create_batches(uncategorized_qs))
        num_batches = len(batches)

        from django.db import transaction

        for idx, batch in enumerate(batches):
            payload = self.batcher.prepare_batch_payload(batch)

            # Determine the model name for logging
            if ai_provider == 'openai':
                model_name = profile.openai_model or "gpt-4.1-nano"
            elif ai_provider == 'deepseek':
                model_name = profile.deepseek_model or "deepseek-chat"
            else:
                model_name = profile.gemini_model or "gemini-3.1-flash-lite"

            try:
                if ai_provider == 'openai':
                    openai_classifier = OpenAIClassifier()
                    classifier_output = openai_classifier.classify_batch(payload, category_names, user)
                elif ai_provider == 'deepseek':
                    deepseek_classifier = DeepSeekClassifier()
                    classifier_output = deepseek_classifier.classify_batch(payload, category_names, user)
                else:
                    classifier_output = self.classifier.classify_batch(payload, category_names, user)

                # Robust check for mocked test compatibility
                if isinstance(classifier_output, ClassifierOutput):
                    ai_results = classifier_output.results
                    input_tokens = classifier_output.input_tokens
                    output_tokens = classifier_output.output_tokens
                    latency = classifier_output.latency_seconds
                else:
                    ai_results = classifier_output
                    input_tokens = 0
                    output_tokens = 0
                    latency = 0.0

                # Sanitize Mock objects from test suites
                if not isinstance(input_tokens, (int, float)) or type(input_tokens).__name__ in ('Mock', 'MagicMock'):
                    input_tokens = 0
                if not isinstance(output_tokens, (int, float)) or type(output_tokens).__name__ in ('Mock', 'MagicMock'):
                    output_tokens = 0
                if not isinstance(latency, (int, float)) or type(latency).__name__ in ('Mock', 'MagicMock'):
                    latency = 0.0

                # Validate results
                validated = ResponseValidator.validate(ai_results, category_name_set)
                batch_map = {txn.id: txn for txn in batch}
                batch_txns_to_update = []

                # Log telemetry and update transactions atomically
                with transaction.atomic():
                    pricing = AI_PRICING.get(model_name, {"input": 0.0, "output": 0.0})
                    cost = (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])
                    confidences = [r.get('confidence', 0.0) for r in ai_results if r.get('confidence') is not None]
                    avg_confidence = sum(confidences) / len(confidences) if confidences else None

                    from accounts.models import AITelemetryLog
                    log_instance = AITelemetryLog.objects.create(
                        user=user,
                        provider=ai_provider,
                        model_name=model_name,
                        batch_size=len(batch),
                        latency_seconds=latency,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        calculated_cost_usd=cost,
                        avg_confidence=avg_confidence,
                        success=True
                    )

                    for classification in validated:
                        txn = batch_map.get(classification.transaction_id)
                        if not txn:
                            continue

                        cat_obj = category_map.get(classification.category_name.lower()) if classification.category_name else None
                        if not cat_obj:
                            cat_obj = category_map.get('uncategorized', uncategorized_cat)

                        txn.category = cat_obj
                        txn.ai_confidence = classification.confidence
                        txn.is_ai_categorized = True
                        txn.ai_suggested_category = classification.suggested_category
                        txn.ai_run = log_instance  # direct FK relationship link
                        batch_txns_to_update.append(txn)

                        if classification.is_valid:
                            result.total_categorized += 1
                        else:
                            result.total_low_confidence += 1

                        result.results.append(classification)

                    if batch_txns_to_update:
                        Transaction.objects.bulk_update(
                            batch_txns_to_update,
                            fields=['category', 'ai_confidence', 'is_ai_categorized', 'ai_suggested_category', 'ai_run'],
                            batch_size=100
                        )
                        transactions_to_update.extend(batch_txns_to_update)

            except AIServiceError as e:
                logger.error(f"Batch classification failed: {e}")
                result.total_errors += len(batch)
                result.errors.append(str(e))

                # Log failed API call telemetry atomically
                from accounts.models import AITelemetryLog
                with transaction.atomic():
                    AITelemetryLog.objects.create(
                        user=user,
                        provider=ai_provider,
                        model_name=model_name,
                        batch_size=len(batch),
                        latency_seconds=0.0,
                        input_tokens=0,
                        output_tokens=0,
                        calculated_cost_usd=0.0,
                        success=False,
                        error_type="AIServiceError"
                    )

            # Add throttling delay between sequential batches
            if idx < num_batches - 1:
                logger.info("Throttling request. Sleeping for 3 seconds...")
                time.sleep(3)

        # Step 5: Log complete status
        if transactions_to_update:
            logger.info(
                f"Successfully processed and updated {len(transactions_to_update)} transactions for user {user.username}"
            )

        return result


# ---------------------------------------------------------------------------
# 6. CUSTOM EXCEPTIONS
# ---------------------------------------------------------------------------

class AIServiceError(Exception):
    """Raised when the AI classification service fails irrecoverably."""
    pass
