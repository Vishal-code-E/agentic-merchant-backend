FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy MCP server code
COPY server.py settings.py ./

ENV PYTHONUNBUFFERED=1
ENV BACKEND_BASE_URL=http://backend:8000
ENV API_V1_PREFIX=/api/v1

EXPOSE 8001

# Run with SSE transport for containerized network access
CMD ["python", "server.py", "--transport", "sse", "--port", "8001"]
