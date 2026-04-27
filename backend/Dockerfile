FROM python:3.11-slim
WORKDIR /app

# System deps for OCR (tesseract + russian language pack) + PDF→image (poppler)
# + libgl/libglib for opencv if used elsewhere by markitdown
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    ghostscript \
    qpdf \
    unpaper \
    pngquant \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD sh -c "python init_db.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"
