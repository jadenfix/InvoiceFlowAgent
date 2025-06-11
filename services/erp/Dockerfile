FROM python:3.11-slim

WORKDIR /app

COPY services/erp/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY services/erp/app ./app

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"] 