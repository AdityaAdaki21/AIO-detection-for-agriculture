FROM python:3.9-slim

WORKDIR /app

COPY . .

RUN mkdir -p static/uploads static/audio && \
    chmod -R 777 static && \
    pip install --no-cache-dir -r requirements.txt

CMD ["gunicorn", "--bind", "0.0.0.0:7860", "app:app"]