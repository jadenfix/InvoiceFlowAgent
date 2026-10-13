FROM python:3.11-slim
WORKDIR /app
COPY services/pipeline/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/pipeline /app/services/pipeline
ENV PYTHONPATH=/app
CMD ["uvicorn", "services.pipeline.runtime:app", "--host", "0.0.0.0", "--port", "8000"]
