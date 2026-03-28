FROM python:3.12-slim AS base

WORKDIR /app

# Install dependencies first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install the framework itself in development mode
RUN pip install --no-cache-dir -e .

EXPOSE 8000

# Production command
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
