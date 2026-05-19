# SMART TRANSACTION SORTER: TECHNICAL IMPLEMENTATION SPEC
**Target Audience:** Cursor / AI Coding Assistant
**Role:** System Architect & Lead Developer
**Context Version:** 2.1 (Focus: AI Integration & BI Layer)

---

## 1. PROJECT ARCHITECTURAL SCOPE
A Django-based ETL pipeline that transforms unstructured Pakistani digital wallet CSVs into categorized financial intelligence.

### Core Logic Flow:
1. **Ingestion:** User uploads CSV -> Pandas validates headers -> Rows saved to `Transaction` (category = NULL).
2. **Classification:** Trigger AI -> Fetch NULL categories -> API Call (Gemini) -> Parse JSON -> Bulk Update DB.
3. **Visualization:** Metabase reads PostgreSQL -> Generates iFrames -> Django embeds in Dashboard.

---

## 2. DATA CONTRACTS (STRICT SCHEMAS)

### A. The AI Input/Output Contract
When calling the AI, the prompt must enforce this exact JSON structure to ensure the Python parser doesn't crash.

**LLM System Prompt Constraint:**
"You are a JSON-only response engine. Categorize the following transactions based on the provided Taxonomy. 
Return ONLY a JSON array of objects: `[{"id": <int>, "category": <string>}]`."

### B. Database Schema Reference
* **Category Model:** `id` (PK), `name` (unique), `description` (optional).
* **Transaction Model:** `id` (PK), `date`, `description`, `amount`, `comments`, `category_id` (FK to Category).

---

## 3. DEVELOPMENT ROADMAP (USE CASES FOR CURSOR)

### UC-AI-01: The Batching Service
**Task:** Build a service in `ai_engine.py` to handle data preparation.
- **Logic:** Query `Transaction` where `category_id` is null.
- **Requirement:** Limit batches to 50 records to maintain LLM context quality and avoid timeout.
- **Output:** A Python list of dictionaries: `{'id': trans.id, 'desc': trans.description}`.

### UC-AI-02: Gemini API Integration
**Task:** Implement the `google-generativeai` SDK.
- **Model:** `gemini-1.5-flash` (Optimized for speed/cost).
- **Security:** Use `os.getenv("GEMINI_API_KEY")`.
- **Validation:** Write a validator to check if the AI-returned "category name" exists in our `Category` table before updating.

### UC-AI-03: The "Bulk Update" Logic
**Task:** Efficiently update the database.
- **Constraint:** DO NOT use a for-loop with `.save()`. 
- **Solution:** Use `django.db.models.bulk_update`. This is critical for performance during large CSV imports.

### UC-BI-01: Metabase Integration
**Task:** Prepare the `analytics_dashboard.html`.
- **Logic:** Add an iframe container that accepts a signed URL or public link from Metabase.
- **UI:** Ensure the dashboard is responsive and uses Tailwind CSS to match the `base.html` styling.

---

## 4. ERROR HANDLING PROTOCOLS (MUST IMPLEMENT)
1. **API Timeout:** If the AI takes >10 seconds, retry once, then fail gracefully with a message: "AI Sorting delayed. Please refresh."
2. **Missing Category:** If the AI suggests a category not in our DB, auto-assign to "Uncategorized" (ID 1).
3. **File Corruption:** If Pandas fails to parse a row, skip that row and log the error; do not stop the entire upload.

---

## 5. REPOSITORY GUIDELINES FOR AI
- **Existing Views:** `TransactionUploadView` is functional. Do not rewrite.
- **Templates:** Use `base.html` for all new pages to maintain navigation and sidebar.
- **Styling:** Use Tailwind CSS utility classes exclusively.
- **Environment:** Use `.env` for all secrets. NEVER suggest hardcoding keys.