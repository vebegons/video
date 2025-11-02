FROM python:3.11-slim

# تثبيت FFmpeg والأدوات المطلوبة
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# تعيين مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات
COPY requirements.txt .

# تثبيت المكتبات Python وتثبيت python-multipart بشكل صريح
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install python-multipart

# نسخ ملفات التطبيق
COPY . .

# إنشاء مجلد الرفع
RUN mkdir -p uploads static templates

# تعريض المنفذ
EXPOSE 8000

# تشغيل التطبيق
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
