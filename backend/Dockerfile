FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code
COPY . .

EXPOSE 8000

# main.py must expose a FastAPI instance named `app`
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]