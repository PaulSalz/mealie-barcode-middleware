FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY docs/ ./docs/
COPY entrypoint.sh /entrypoint.sh

# Bundle OpenDyslexic locally so Appearance does not depend on an external font CDN
# at runtime. The upstream project is SIL-OFL licensed.
RUN mkdir -p /app/app/static/vendor/opendyslexic \
    && python -c "import urllib.request; base='https://raw.githubusercontent.com/antijingoist/opendyslexic/main/compiled/'; urllib.request.urlretrieve(base+'OpenDyslexic-Regular.woff2','/app/app/static/vendor/opendyslexic/OpenDyslexic-Regular.woff2'); urllib.request.urlretrieve(base+'OpenDyslexic-Bold.woff2','/app/app/static/vendor/opendyslexic/OpenDyslexic-Bold.woff2'); urllib.request.urlretrieve('https://raw.githubusercontent.com/antijingoist/opendyslexic/main/OFL.txt','/app/app/static/vendor/opendyslexic/OFL.txt')" \
    && adduser --system --no-create-home appuser \
    && mkdir -p /data \
    && chown appuser /data \
    && apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
