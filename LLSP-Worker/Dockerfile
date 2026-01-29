FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml pyproject.toml
RUN pip install .
COPY celery_app.py celery_app.py
CMD ["celery", "-A", "celery_app.app", "worker", "-E", "--loglevel=INFO", "--concurrency=1"]