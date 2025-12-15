FROM python:3.12-slim

# Install system dependencies for Chromium
RUN apt-get update && apt-get install -y \
    chromium \
    fonts-liberation libappindicator3-1 libasound2 \
    libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
    libnspr4 libnss3 libxcomposite1 \
    libxdamage1 libxrandr2 xdg-utils wget curl \
    && rm -rf /var/lib/apt/lists/

ENV CHROME_ENV='usr/bin/activate'

WORKDIR /app
COPY ./pyproject.toml /app

# Install Poetry and project dependencies
RUN pip install poetry && poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

# Copy project files
COPY . /app

# Default command, override in docker-compose if needed
CMD [ "python", "src/scraper.py" ]

