FROM python:3.9-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/data /app/images

ENV DATA_DIR=/app/data

EXPOSE 5000

CMD ["python", "app.py"]