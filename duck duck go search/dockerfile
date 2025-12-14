FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies (kept minimal)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY duck-duck-go-mcp-server.py /app/

# Install runtime Python dependencies
RUN pip install --no-cache-dir "uvicorn[standard]" starlette "duckduckgo-search" mcp

# Expose the default port used by the script
EXPOSE 8000

# Use ENTRYPOINT so additional args passed to `docker run` are forwarded to the script.
# Default CMD provides a sensible default port that can be overridden at runtime.
ENTRYPOINT ["python", "duck-duck-go-mcp-server.py"]
CMD ["--port", "8000"]
