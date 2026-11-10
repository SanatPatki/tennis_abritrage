FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    httpx "websockets>=12" cryptography "pydantic>=2" pandas \
    "psycopg[binary]" "apscheduler>=3.10,<4" rapidfuzz unidecode pyyaml python-dotenv

COPY src/ /app/src/
COPY config.yaml /app/config.yaml

ENV MODE=paper
CMD ["python", "-m", "src.main"]
