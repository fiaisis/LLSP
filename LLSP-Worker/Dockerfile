FROM ghcr.io/fiaisis/mantid:6.14.0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml pyproject.toml
RUN pip install .
COPY celery_app.py celery_app.py
ENTRYPOINT []
CMD ["celery", "-A", "celery_app.app", "worker", "--loglevel=INFO", "--concurrency=1"]