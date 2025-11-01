## Dockerfile المُعدَّل لحل مشكلة "Could not import module app.main"

# 1. المرحلة الأولى: اختيار الصورة الأساسية
FROM python:3.11-slim

# 2. تثبيت أدوات معالجة الفيديو: FFmpeg والأدوات المطلوبة
# استخدام `--no-install-recommends` لتقليل حجم الصورة
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# 3. تعيين مجلد العمل
# سيتم نسخ جميع الملفات إليه (المسار: /app)
WORKDIR /app

# 4. نسخ ملف المتطلبات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. نسخ ملفات التطبيق
# سيتم نسخ مجلد 'app' و 'Dockerfile' و 'requirements.txt' وباقي الملفات إلى /app
COPY . .

# 6. إنشاء مجلدات العمل (التي يحتاجها main.py)
RUN mkdir -p uploads static templates

# 7. تعريض المنفذ (Port)
ENV PORT 8000
EXPOSE 8000

# 8. تشغيل التطبيق (الأمر الحاسم)
# تم التعديل إلى 'app.app.main:app' ليعكس المسار الصحيح داخل Docker:
# /app (مجلد العمل) / app (المجلد المنسوخ) / main.py
CMD ["uvicorn", "app.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
