FROM python:3.11-slim
RUN pip install --no-cache-dir fastapi uvicorn
WORKDIR /app
COPY app.py .
COPY index.html static/index.html
RUN mkdir -p /app/data
EXPOSE 8090
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
