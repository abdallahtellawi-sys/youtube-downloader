FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PORT=8000
EXPOSE 8000

# Single worker because this app stores download state in memory (downloads dict).
CMD ["sh", "-c", "gunicorn -w 1 -k gthread --threads 8 -b 0.0.0.0:$PORT app:app"]

