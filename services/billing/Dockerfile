FROM python:3.11-slim
WORKDIR /app
COPY services/billing/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY services/billing/app ./app
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8010"] 