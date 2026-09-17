FROM python:3.12-slim
RUN useradd --create-home --uid 10001 mosaic
WORKDIR /app
COPY --chown=mosaic:mosaic . /app
USER mosaic
ENV MOSAIC_HOST=0.0.0.0 PORT=8000 MOSAIC_DB_PATH=/data/mosaic.db
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=2)"
CMD ["python", "app.py", "serve"]
