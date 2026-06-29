# Smart Transaction Sorter and Analytics System

Smart Transaction Sorter is a Django-based financial transaction management and analytics system. It helps users upload bank or wallet CSV statements, normalize transaction records, categorize spending with AI, and review financial insights through embedded Metabase dashboards.

The project was built as a final-year project with a focus on clean Django architecture, secure configuration, practical CSV ingestion, AI-assisted expense classification, and analytics-ready data storage.

## Core Features

- User registration, login, and session-based access control.
- Personal category management with admin-managed default category suggestions.
- CSV transaction upload using both a standard template and NayaPay-style statement ingestion.
- Duplicate transaction detection using extracted transaction IDs and SHA-256 transaction hashes.
- AI categorization using configurable providers:
  - Google Gemini
  - OpenAI
  - DeepSeek
- User-level AI provider and API key settings.
- AI telemetry logging for provider, model, batch size, latency, token usage, confidence, success status, and estimated cost.
- Inline transaction category updates and transaction deletion APIs.
- Embedded Metabase analytics dashboards using signed JWT embeds.
- Light/dark themed Django templates and static assets.
- Automated Django test coverage for core upload, categorization, API, and analytics behavior.

## Tech Stack

- Backend: Django 5.2
- Database: SQLite for local development, optional PostgreSQL/Supabase through `DATABASE_URL`
- Data processing: pandas
- AI providers: Gemini, OpenAI, DeepSeek-compatible OpenAI SDK flow
- Analytics: Metabase signed embedding
- UI: Django templates, Bootstrap-style layout, custom CSS/JS
- Admin UI: Django Jazzmin

## Repository Structure

```text
.
├── accounts/               # Authentication-related views, forms, profile models, AI settings
├── pages/                  # Main app: categories, uploads, parser, AI engine, analytics views
├── myproject/              # Django project settings, URLs, ASGI/WSGI entry points
├── templates/              # HTML templates
├── static/                 # Source CSS, JS, images, and sample downloadable static files
├── sample_data/uploads/    # Small CSV files for local import testing
├── manage.py
├── requirements.txt
├── .env.example            # Safe environment variable template
├── .gitignore
├── run_system.ps1          # Optional local Django + Metabase startup helper
└── run_system.bat          # Windows wrapper for the PowerShell startup helper
```

## What Is Intentionally Not Committed

The repository is kept clean by excluding local runtime files, generated files, and private data:

- `.env` and other local secret files
- API keys, database URLs, and Metabase embedding secrets
- Virtual environments such as `.venv/`, `venv/`, and `env/`
- Local SQLite databases such as `db.sqlite3`
- Uploaded media and temporary import files
- Collected static output in `staticfiles/`
- Metabase runtime files such as `metabase.jar`, `metabase.db.*`, and `plugins/`
- Development scratch folders, draft documentation folders, and old CSV experiments
- Python cache files such as `__pycache__/` and `*.pyc`

This keeps GitHub focused on source code, configuration templates, migrations, static source assets, tests, and small reproducible sample data.

## Prerequisites

- Python 3.11 or newer
- pip
- Git
- Java 17 or newer if you want to run Metabase locally
- Optional: PostgreSQL/Supabase database for production-like deployment

## Local Setup

Clone the repository and enter the project folder:

```powershell
git clone <repository-url>
cd my_django_project
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create your local environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and add the values needed for your machine.

Run database migrations:

```powershell
python manage.py migrate
```

Start the Django development server:

```powershell
python manage.py runserver
```

Open the app at:

```text
http://127.0.0.1:8000/
```

## Environment Variables

The project reads configuration from `.env` through `python-dotenv`.

| Variable | Required | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Recommended | Secret key for Django signing and security. Use a strong value outside development. |
| `DJANGO_DEBUG` | Recommended | `True` for local development, `False` for production. |
| `DJANGO_ALLOWED_HOSTS` | Production | Comma-separated allowed hosts, for example `localhost,127.0.0.1`. |
| `GEMINI_API_KEY` | Optional | Global fallback key for Gemini categorization. |
| `DEEPSEEK_API_KEY` | Optional | Global fallback key for DeepSeek categorization. |
| `METABASE_SITE_URL` | Optional | Metabase base URL, defaults to `http://localhost:3000`. |
| `METABASE_EMBEDDING_SECRET_KEY` | Required for embeds | Secret used to sign Metabase dashboard embed JWTs. |
| `USE_POSTGRES` | Optional | Set to `True` to use `DATABASE_URL`. |
| `DATABASE_URL` | Optional | PostgreSQL/Supabase connection string. |
| `METABASE_JAR_PATH` | Optional | Path to a local Metabase jar if it is not stored as `metabase.jar` in the root. |

Never commit `.env` or real credentials.

## CSV Uploads

The app supports two upload modes:

- Standard template CSV upload for normalized transaction rows.
- NayaPay-style CSV ingestion with dynamic header detection, description parsing, duplicate checks, and metadata extraction.

Sample files are provided in:

```text
sample_data/uploads/
```

Use those files for local testing and demonstrations. Personal statements, generated benchmark exports, and one-off experiment files should stay outside Git.

## AI Categorization

Users can select an AI provider from the settings page. The system stores provider preferences per user and can use either user-provided API keys or global fallback keys from `.env`.

The AI engine classifies uncategorized transactions into the user's category list. It also records telemetry such as:

- Provider and model
- Batch size
- Latency
- Input/output tokens
- Estimated cost
- Average confidence
- Success or failure status

This telemetry is used by the analytics dashboard to compare AI performance.

## Metabase Analytics

Metabase is integrated through signed embeds. The Django app generates JWT-signed dashboard URLs using:

- `METABASE_SITE_URL`
- `METABASE_EMBEDDING_SECRET_KEY`

The repository does not commit the Metabase jar, local Metabase database, or Metabase plugins because those are local runtime artifacts. To run Metabase locally, download the jar on your own machine and either:

- place it as `metabase.jar` in the project root, or
- set `METABASE_JAR_PATH` to the jar location.

Then run:

```powershell
.\run_system.ps1
```

The script attempts to start Metabase, runs Django migrations, opens the browser, and starts the Django development server.

## Running Tests

Run the full Django test suite:

```powershell
python manage.py test
```

Run Django's configuration check:

```powershell
python manage.py check
```

Both commands should pass before pushing changes.

## Development Workflow

Recommended workflow before committing:

```powershell
git status
python manage.py check
python manage.py test
git add -A
git commit -m "clear, descriptive commit message"
git push origin dev-features
```

Before pushing, confirm that Git does not include:

- `.env`
- `db.sqlite3`
- virtual environments
- `media/`
- `staticfiles/`
- Metabase jar/database/plugin files
- personal CSV exports
- draft documentation or scratch folders

## Notes for Evaluators and Contributors

This repository is structured so a new developer can clone it, install dependencies, create a local `.env`, migrate the database, and run the app without receiving private files or machine-specific artifacts. The committed files represent the project source, schema migrations, static source assets, sample test data, and setup instructions needed to reproduce the system.
