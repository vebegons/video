from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
import os
import shutil
from pathlib import Path
from datetime import datetime
import json
import subprocess
from PIL import Image
import io
import re
import aiofiles
import logging

# إعدادات التسجيل (Logging)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# إعدادات المشروع
BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# إنشاء المجلدات إذا لم تكن موجودة
UPLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

# إعدادات الملفات
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "flv", "wmv", "webm"}

# إعداد تطبيق FastAPI
app = FastAPI(
    title="محقق الفيديو الأصلي",
    description="أداة متقدمة للبحث عن أصل الفيديوهات والصور",
    version="1.0.0"
)

# إعداد القوالب
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# إضافة StaticFiles لخدمة الملفات الثابتة (CSS/JS)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# إضافة CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# دالة حساب درجة الجودة (Quality Score) - التحليل الداخلي الحقيقي
# ============================================================================
def calculate_quality_score(video_info):
    """
    حساب درجة جودة الفيديو (0-100) بناءً على معايير متعددة
    
    المعايير المستخدمة:
    1. الدقة (Resolution): 40 نقطة
    2. معدل البت (Bitrate): 35 نقطة
    3. تاريخ الإنشاء (Creation Date): 15 نقطة
    4. حجم الملف (File Size): 10 نقاط
    """
    score = 0
    indicators = []
    
    # 1. معيار الدقة (40 نقطة)
    resolution_score = 0
    if video_info and "resolution" in video_info:
        resolution = video_info.get("resolution", "")
        height = 0
        
        # استخراج ارتفاع الفيديو من الدقة (مثل 1920x1080)
        try:
            height = int(resolution.split('x')[1])
        except:
            pass
        
        if height >= 2160:  # 4K
            resolution_score = 40
            indicators.append("✓ دقة عالية جداً (4K أو أعلى) - دليل قوي على الأصالة")
        elif height >= 1440:  # 2K
            resolution_score = 35
            indicators.append("✓ دقة عالية (2K) - دليل على جودة عالية")
        elif height >= 1080:  # Full HD
            resolution_score = 25
            indicators.append("✓ دقة متوسطة-عالية (Full HD)")
        elif height >= 720:  # HD
            resolution_score = 15
            indicators.append("⚠ دقة متوسطة (HD) - قد تكون نسخة مضغوطة")
        else:
            resolution_score = 5
            indicators.append("✗ دقة منخفضة - احتمالية عالية أنها نسخة معاد تشفيرها")
    
    score += resolution_score
    
    # 2. معيار معدل البت (35 نقطة)
    bitrate_score = 0
    if video_info and "bitrate" in video_info:
        bitrate_str = video_info.get("bitrate", "")
        
        # محاولة استخراج قيمة معدل البت بالـ Mbps
        bitrate_value = 0
        try:
            # البحث عن أرقام في معدل البت
            match = re.search(r'(\d+(?:\.\d+)?)', bitrate_str)
            if match:
                bitrate_value = float(match.group(1))
                
                # تحديد الوحدة (Mbps أو Kbps)
                if 'k' in bitrate_str.lower():
                    bitrate_value = bitrate_value / 1000  # تحويل من Kbps إلى Mbps
        except:
            pass
        
        if bitrate_value >= 50:
            bitrate_score = 35
            indicators.append(f"✓ معدل بت عالي جداً ({bitrate_value:.1f} Mbps) - دليل قوي على الأصالة")
        elif bitrate_value >= 20:
            bitrate_score = 25
            indicators.append(f"✓ معدل بت عالي ({bitrate_value:.1f} Mbps) - جودة احترافية")
        elif bitrate_value >= 10:
            bitrate_score = 15
            indicators.append(f"⚠ معدل بت متوسط ({bitrate_value:.1f} Mbps) - قد تكون نسخة توزيع")
        elif bitrate_value >= 5:
            bitrate_score = 8
            indicators.append(f"⚠ معدل بت منخفض ({bitrate_value:.1f} Mbps) - احتمالية عالية أنها نسخة مضغوطة")
        else:
            bitrate_score = 3
            indicators.append("✗ معدل بت منخفض جداً - احتمالية عالية أنها نسخة معاد تشفيرها")
    
    score += bitrate_score
    
    # 3. معيار تاريخ الإنشاء (15 نقطة)
    date_score = 0
    if video_info and "created_date" in video_info:
        try:
            created_date = datetime.fromisoformat(video_info.get("created_date", ""))
            days_old = (datetime.now() - created_date).days
            
            if days_old > 365:  # أكثر من سنة
                date_score = 15
                indicators.append(f"✓ تاريخ إنشاء قديم ({days_old} يوم) - دليل على الأصالة")
            elif days_old > 180:  # أكثر من 6 أشهر
                date_score = 10
                indicators.append(f"⚠ تاريخ إنشاء متوسط ({days_old} يوم)")
            elif days_old > 30:  # أكثر من شهر
                date_score = 5
                indicators.append(f"⚠ تاريخ إنشاء حديث نسبياً ({days_old} يوم)")
            else:
                date_score = 2
                indicators.append(f"✗ تاريخ إنشاء حديث جداً ({days_old} يوم) - قد تكون نسخة معاد تشفيرها")
        except:
            date_score = 0
    
    score += date_score
    
    # 4. معيار حجم الملف (10 نقاط)
    file_size_score = 0
    if video_info and "file_size" in video_info:
        file_size_mb = video_info.get("file_size", 0) / (1024 * 1024)
        
        if file_size_mb > 500:  # أكثر من 500 ميجا
            file_size_score = 10
            indicators.append(f"✓ حجم ملف كبير ({file_size_mb:.1f} MB) - دليل على جودة عالية")
        elif file_size_mb > 100:
            file_size_score = 7
            indicators.append(f"✓ حجم ملف متوسط-كبير ({file_size_mb:.1f} MB)")
        elif file_size_mb > 50:
            file_size_score = 4
            indicators.append(f"⚠ حجم ملف متوسط ({file_size_mb:.1f} MB)")
        else:
            file_size_score = 1
            indicators.append(f"⚠ حجم ملف صغير ({file_size_mb:.1f} MB) - قد تكون نسخة مضغوطة")
    
    score += file_size_score
    
    # تحديد مستوى الثقة (Confidence) بناءً على الدرجة
    if score >= 85:
        confidence = 0.95
        confidence_level = "عالية جداً"
    elif score >= 70:
        confidence = 0.80
        confidence_level = "عالية"
    elif score >= 50:
        confidence = 0.60
        confidence_level = "متوسطة"
    else:
        confidence = 0.40
        confidence_level = "منخفضة"
    
    return {
        "score": min(100, score),  # الحد الأقصى 100
        "confidence": confidence,
        "confidence_level": confidence_level,
        "indicators": indicators,
        "breakdown": {
            "resolution": resolution_score,
            "bitrate": bitrate_score,
            "creation_date": date_score,
            "file_size": file_size_score
        }
    }

# ============================================================================
# دالة لاستخراج معلومات الفيديو باستخدام ffprobe
# ============================================================================
def get_video_info(video_path):
    """استخراج معلومات الفيديو من الملف"""
    try:
        cmd = [
            'ffprobe', '-v', 'error', '-show_format', '-show_streams',
            '-print_section', 'format=json', '-print_section', 'stream=json',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            # محاولة استخراج المعلومات الأساسية
            info = {
                "filename": os.path.basename(video_path),
                "file_size": os.path.getsize(video_path),
                "created_date": datetime.fromtimestamp(os.path.getctime(video_path)).isoformat(),
                "modified_date": datetime.fromtimestamp(os.path.getmtime(video_path)).isoformat(),
            }
            
            # محاولة استخراج معلومات الفيديو من ffprobe
            try:
                output = result.stdout
                if 'duration' in output:
                    # محاولة استخراج المدة
                    duration_match = re.search(r'"duration"\s*:\s*"([^"]+)"', output)
                    if duration_match:
                        info["duration"] = duration_match.group(1)
                    
                    # محاولة استخراج الدقة
                    width_match = re.search(r'"width"\s*:\s*(\d+)', output)
                    height_match = re.search(r'"height"\s*:\s*(\d+)', output)
                    if width_match and height_match:
                        width = int(width_match.group(1))
                        height = int(height_match.group(1))
                        info["resolution"] = f"{width}x{height}"
                        
                        # تحديد جودة الفيديو
                        if height >= 2160:
                            info["quality"] = "4K UHD"
                        elif height >= 1440:
                            info["quality"] = "2K"
                        elif height >= 1080:
                            info["quality"] = "Full HD"
                        elif height >= 720:
                            info["quality"] = "HD"
                        else:
                            info["quality"] = "SD"
                    
                    # محاولة استخراج معدل البت
                    bitrate_match = re.search(r'"bit_rate"\s*:\s*"([^"]+)"', output)
                    if bitrate_match:
                        bitrate_str = bitrate_match.group(1)
                        info["bitrate"] = bitrate_str
                        
                        # تحويل معدل البت إلى Mbps للحساب
                        try:
                            bitrate_value = float(bitrate_str)
                            if bitrate_value > 1000:  # إذا كان بالـ bps
                                bitrate_value = bitrate_value / 1000000  # تحويل إلى Mbps
                            elif bitrate_value > 1:  # إذا كان بالـ Kbps
                                bitrate_value = bitrate_value / 1000  # تحويل إلى Mbps
                            info["bitrate"] = f"{bitrate_value:.1f} Mbps"
                        except:
                            pass
            except Exception as e:
                logger.error(f"Error parsing ffprobe output: {e}")
                pass
            
            return info
    except Exception as e:
        logger.error(f"Error in get_video_info: {e}")
    
    return None

# ============================================================================
# دالة لاستخراج لقطات شاشة من الفيديو
# ============================================================================
def extract_frames(video_path, num_frames=6):
    """استخراج عدة لقطات شاشة من الفيديو"""
    frames = []
    try:
        # الحصول على معلومات الفيديو أولاً
        info = get_video_info(video_path)
        if not info or 'duration' not in info:
            logger.error("Could not get video duration for frame extraction.")
            return []

        # تحويل المدة إلى ثواني
        try:
            duration_parts = info['duration'].split(':')
            if len(duration_parts) == 3:
                duration_seconds = int(duration_parts[0]) * 3600 + int(duration_parts[1]) * 60 + float(duration_parts[2])
            else:
                duration_seconds = float(info['duration'])
        except:
            duration_seconds = 60 # قيمة افتراضية

        # حساب الفواصل الزمنية
        interval = duration_seconds / (num_frames + 1)
        
        for i in range(1, num_frames + 1):
            timestamp = i * interval
            frame_filename = f"{Path(video_path).stem}_frame_{i}.jpg"
            frame_path = STATIC_DIR / frame_filename
            
            # استخدام FFmpeg لاستخراج الإطار
            cmd = [
                'ffmpeg', '-ss', str(timestamp), '-i', video_path, '-vframes', '1',
                '-q:v', '2', '-y', str(frame_path)
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            
            frames.append(f"/static/{frame_filename}")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed during frame extraction: {e.stderr.decode()}")
    except Exception as e:
        logger.error(f"Error during frame extraction: {e}")
        
    return frames

# ============================================================================
# المسارات (Routes)
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """عرض الصفحة الرئيسية"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """رفع ومعالجة الفيديو"""
    try:
        # 1. التحقق من نوع الملف
        file_extension = file.filename.split(".")[-1].lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            logger.error(f"Invalid file extension: {file_extension}")
            raise HTTPException(status_code=400, detail="صيغة الملف غير مدعومة. يرجى رفع ملف فيديو.")

        # 2. حفظ الملف المؤقت
        temp_file_path = UPLOAD_DIR / file.filename
        
        # استخدام aiofiles للكتابة غير المتزامنة
        file_size = 0
        async with aiofiles.open(temp_file_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024):  # قراءة 1MB في كل مرة
                file_size += len(content)
                if file_size > MAX_FILE_SIZE:
                    # حذف الملف الزائد
                    os.remove(temp_file_path)
                    logger.error(f"File size exceeded limit: {file_size} bytes")
                    raise HTTPException(status_code=400, detail="حجم الملف يتجاوز الحد المسموح به (100 ميجابايت).")
                await out_file.write(content)
        
        # 3. بدء التحليل
        analysis_result = await analyze_video(temp_file_path)

        return analysis_result

    except HTTPException as e:
        # إعادة توجيه أخطاء HTTP القياسية (مثل 400)
        raise e
    except Exception as e:
        # طباعة الخطأ الفعلي في السجلات
        logger.error(f"Internal Server Error during upload: {e}", exc_info=True)
        # إرجاع خطأ 500 مع رسالة عامة للمستخدم
        raise HTTPException(status_code=500, detail=f"خطأ داخلي في الخادم أثناء المعالجة: {e}")

async def analyze_video(file_path):
    """دالة مساعدة لتنفيذ التحليل"""
    try:
        # 1. استخراج معلومات الفيديو
        video_info = get_video_info(str(file_path))
        
        if not video_info:
            raise Exception("فشل في استخراج معلومات الفيديو (قد يكون الملف تالفاً أو غير مدعوم).")

        # 2. حساب درجة الجودة
        quality_analysis = calculate_quality_score(video_info)
        
        # 3. استخراج لقطات شاشة
        frames = extract_frames(str(file_path), num_frames=6)
        
        # 4. تجميع النتيجة
        result = {
            "success": True,
            "message": "تم رفع الفيديو وتحليله بنجاح",
            "video_info": video_info,
            "quality_analysis": quality_analysis,
            "frames": frames,
            "filename": Path(file_path).name
        }
        
        # 5. حذف الملف المؤقت بعد التحليل
        os.remove(file_path)
        
        return result
    except Exception as e:
        # حذف الملف في حالة فشل التحليل
        if os.path.exists(file_path):
            os.remove(file_path)
        raise e

@app.get("/api/analyze")
async def analyze_metadata(filename: str):
    """تحليل البيانات الوصفية للفيديو"""
    try:
        file_path = UPLOAD_DIR / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="الملف غير موجود")
        
        # استخدام دالة analyze_video الجديدة
        analysis_result = await analyze_video(file_path)
        
        return analysis_result
    except HTTPException as e:
        logger.error(f"Error in /api/analyze: {e}", exc_info=True)
        raise e
    except Exception as e:
        logger.error(f"Error in /api/analyze: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/uploads/{filename}")
async def get_file(filename: str):
    """تحميل ملف من مجلد الرفع"""
    file_path = UPLOAD_DIR / filename
    if file_path.exists():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="الملف غير موجود")

@app.get("/health")
async def health_check():
    """فحص صحة التطبيق"""
    return {
        "status": "healthy",
        "service": "محقق الفيديو الأصلي",
        "version": "1.0.0"
    }

# نقطة البداية
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
