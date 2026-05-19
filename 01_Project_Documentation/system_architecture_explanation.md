# Smart Sorter Architecture Deep-Dive

As the architect, I want to give you a clear, high-level overview of exactly how we built this system, where the data goes, and how we are protecting user privacy.

## 1. How is User Data Kept Separate? (Tenant Isolation)

The most critical part of any financial app is data privacy. We achieve strict data separation through **Foreign Key Association** in the database.

If you look at `pages/models.py`, both the `Category` and `Transaction` models have this line:
```python
user = models.ForeignKey(User, on_delete=models.CASCADE)
```
* **What this means:** Every single transaction and category is permanently "stamped" with the ID of the user who created it.
* **How we enforce it:** In `pages/views.py`, every time we query the database, we append `.filter(user=request.user)`. This ensures that even if User B tries to guess the URL or API endpoint for User A's data, the database will return `404 Not Found`.

## 2. The ETL Pipeline: Where Does Data Go?

We have a classic **ETL (Extract, Transform, Load)** pipeline, split into two phases:

### Phase 1: Upload (Extract & Load Raw)
When you upload a CSV file:
1. **Extract:** `TransactionUploadView` reads the CSV file line by line in memory.
2. **Transform (Light):** It parses dates, converts string amounts to decimals, and cleans up empty fields.
3. **Load:** It uses Django's `bulk_create` to blast all these rows into the `Transaction` database table simultaneously. At this point, the `category` is `Null` (Uncategorized).

### Phase 2: AI Sorting (Transform Heavy & Load)
When you click "Process with AI":
1. **Extract:** `AICategorizationService` fetches all `Transaction` rows where `is_ai_categorized = False`.
2. **Transform:** This is the core engine. It batches 25 transactions at a time, sends the raw text to Gemini AI, and receives the categorized JSON back. We then validate the JSON to ensure the AI didn't hallucinate.
3. **Load:** We use Django's `bulk_update` to update the `category`, `ai_confidence`, and `ai_suggested_category` fields in the `Transaction` table.

## 3. What Tables Get Affected and When?

We only have two main data tables:
* **`Category` Table:** 
  - *Affected When:* You manually create a category in "Manage Categories", OR when you click the new "✨ Accept Suggestion" button (which auto-creates the AI's suggested category).
* **`Transaction` Table:** 
  - *Affected When:* You upload a CSV (creates rows). 
  - *Affected When:* The AI runs (updates rows with categories). 
  - *Affected When:* You use the new inline dropdown to manually fix a category (updates a single row).

## 4. Does it Match the Sequence Diagram?

**Yes, almost exactly 100%.** 
If you recall the Sequence Diagram from your `Project_Documentation.md`:
1. `ProcessingPage -> AISorterEngine` (This is our `AISortingView` calling `AICategorizationService`).
2. `AISorterEngine -> AI_Model` (This is our batch call to `gemini-flash-latest`).
3. `AI_Model -> AISorterEngine` (Parsing the JSON response).
4. `AISorterEngine -> Database` (This is our `bulk_update` step).

The only slight deviation/improvement is that instead of updating the database *one by one* in a loop (which the diagram implied), we process the whole batch and use `bulk_update`. This is an architectural optimization we made to protect against database bottlenecks and token timeouts.

## 5. What SDLC (Software Development Life Cycle) Are We Using?

We are using an **Agile / Iterative Prototyping** methodology.

* **Iteration 1 (MVP):** Basic database, user authentication, and basic UI.
* **Iteration 2 (AI Integration):** Hooking up Gemini, figuring out the prompt engineering, and handling the JSON parsing.
* **Iteration 3 (Feedback Loop - Current):** Adding the manual rectification UI, handling low-confidence scenarios, and allowing the AI to suggest new categories.

This is exactly how modern SaaS products are built. Instead of trying to build a massive "Waterfall" system perfectly on the first try, we built the core pipeline, saw that the AI sometimes failed (Uncategorized), and iteratively built a feature to handle that failure smoothly.
