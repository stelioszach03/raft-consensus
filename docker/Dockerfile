# Use Python 3.10 slim as the base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose ports
# 7000-7002: Raft node RPC
# 8000-8002: API server
EXPOSE 7000-7002 8000-8002

# Set entrypoint to Python
ENTRYPOINT ["python"]