FROM mcr.microsoft.com/playwright/python:v1.43.0-jammy

WORKDIR /app

COPY 서버/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY 서버/ .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
