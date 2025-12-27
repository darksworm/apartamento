FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy default config (can be overridden with volume mount)
COPY config.yaml ./

# Create data directory
RUN mkdir -p /app/data

# Run the application
CMD ["uv", "run", "apartamento", "--daemon"]
