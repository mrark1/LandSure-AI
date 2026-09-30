# Landsure AI

Flask-based Land Record Intelligence prototype.

## Local setup

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY="local-development-secret"
python app.py
```

Open http://127.0.0.1:5000

### Production-like local run

```bash
gunicorn app:app
```

## Deploy to Render

1. Push this folder to a GitHub repository.
2. In Render, create a **Web Service** from the repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Add `SECRET_KEY` as an environment variable. `render.yaml` can generate it automatically when used by Render.

## Important prototype limitation

TXT uploads are parsed from their contents. PDF/image uploads currently use demo fallback extraction data; real OCR/document-AI processing should be added before presenting this as a production document-extraction system.

SQLite and local uploads are suitable for a demo/prototype but are not durable production storage on an ephemeral hosting filesystem. For production, migrate the database to PostgreSQL and documents to persistent object storage.
