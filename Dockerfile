FROM python:3.11-slim

# System deps for audio (ffmpeg) and build tools
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install packages one by one with retries
COPY requirements.txt .

# Install pip with no-cache-dir and longer timeout
RUN pip install --no-cache-dir --default-timeout=1000 pip --upgrade

# Install packages one by one with retries
RUN while read package; do \
      for i in 1 2 3; do \
        if pip install --no-cache-dir --default-timeout=1000 "$package"; then \
          break; \
        elif [ $i -eq 3 ]; then \
          echo "Failed to install $package after 3 attempts" >&2; \
          exit 1; \
        fi; \
        echo "Retrying $package installation..."; \
        sleep 5; \
      done; \
    done < requirements.txt

# Copy source
COPY . .

# Env to avoid Python buffering issues
ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
