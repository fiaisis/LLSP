FROM python:3.11-slim

WORKDIR /app

RUN pip install pytest requests tenacity

COPY . .

CMD ["pytest", "tests/e2e"]
