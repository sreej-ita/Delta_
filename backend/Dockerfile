FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code
COPY . .

EXPOSE 8000

# main.py must expose a FastAPI instance named `app`.
# Uses $PORT if the platform provides one (e.g. Render sets this at runtime),
# otherwise falls back to 8000 for local Docker Compose. Shell form (not the
# usual JSON-array CMD) is required here so the env var actually expands.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
