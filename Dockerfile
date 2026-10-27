FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data
WORKDIR /app
RUN useradd --uid 10001 --create-home appuser && mkdir /data && chown appuser:appuser /data
COPY --chown=appuser:appuser planner.py server.py ./
COPY --chown=appuser:appuser static ./static
USER appuser
EXPOSE 8881
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8881/health',timeout=3)"
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8881", "--data-dir", "/data"]
