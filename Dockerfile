FROM python:3.11-slim

# Install ffmpeg and nodejs (yt-dlp needs node for JS challenges)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir yt-dlp-get-pot yt-dlp-get-pot-rustypipe

COPY . .

RUN mkdir -p downloads gameplay output temp

EXPOSE 5555

CMD ["python", "server.py"]
