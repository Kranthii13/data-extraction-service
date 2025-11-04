# Dockerfile

# 1. Use an official Python slim image as the base
FROM python:3.10-slim

# 2. Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 3. Install system dependencies for OCR and PDF processing
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    poppler-utils \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 3.1. Verify Tesseract installation
RUN tesseract --version

# 4. Set the working directory inside the container
WORKDIR /app

# 5. Copy and install requirements
# This is done first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy your application source code
# We copy the 'src' folder into the container's /app/src
COPY ./src ./src

# 7. Expose the port the app will run on
EXPOSE 8000

# 8. Define the command to run your application
CMD ["python", "src/app_main.py"]