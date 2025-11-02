from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
from pathlib import Path
from datetime import datetime
import json
import subprocess
from PIL import Image
import io
import re

# إعدادات المشروع
BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# إنشاء المجلدات إذا لم تكن موجودة
UPLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

# إنشاء تطبيق FastAPI
app = FastAPI(
    title="محقق الفيديو الأصلي",
    description="أداة متقدمة للبحث عن أصل الفيديوهات والصور",
    version="1.0.0"
)

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
            except:
                pass
            
            return info
    except Exception as e:
        print(f"خطأ في استخراج معلومات الفيديو: {str(e)}")
    
    return None

# ============================================================================
# دالة لاستخراج لقطات شاشة من الفيديو
# ============================================================================
def extract_frames(video_path, num_frames=6):
    """استخراج عدة لقطات شاشة من الفيديو"""
    frames = []
    try:
        # الحصول على معلومات الفيديو أولاً
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1:noprint_sections=1', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            return frames
        
        try:
            duration = float(result.stdout.strip())
        except:
            duration = 10  # قيمة افتراضية
        
        # حساب المواضع الزمنية لاستخراج الصور
        timestamps = [int(duration * (i + 1) / (num_frames + 1)) for i in range(num_frames)]
        
        # استخراج الصور
        for idx, timestamp in enumerate(timestamps):
            output_path = UPLOAD_DIR / f"frame_{idx}.jpg"
            
            cmd = [
                'ffmpeg', '-ss', str(timestamp), '-i', video_path,
                '-vframes', '1', '-vf', 'scale=320:180',
                '-y', str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            
            if result.returncode == 0 and output_path.exists():
                frames.append({
                    "id": idx,
                    "timestamp": timestamp,
                    "path": f"/uploads/frame_{idx}.jpg"
                })
        
        return frames
    except Exception as e:
        print(f"خطأ في استخراج الصور: {str(e)}")
        return frames

# ============================================================================
# المسارات (Routes)
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """الصفحة الرئيسية"""
    html_path = TEMPLATES_DIR / "index.html"
    if html_path.exists():
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "<h1>محقق الفيديو الأصلي</h1>"

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """رفع ملف فيديو ومعالجته"""
    try:
        # التحقق من نوع الملف
        allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm'}
        file_ext = Path(file.filename).suffix.lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم")
        
        # حفظ الملف
        file_path = UPLOAD_DIR / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # استخراج معلومات الفيديو
        video_info = get_video_info(str(file_path))
        
        # حساب درجة الجودة
        quality_analysis = calculate_quality_score(video_info)
        
        # استخراج لقطات شاشة
        frames = extract_frames(str(file_path), num_frames=6)
        
        return {
            "success": True,
            "message": "تم رفع الفيديو بنجاح",
            "video_info": video_info,
            "quality_analysis": quality_analysis,
            "frames": frames,
            "filename": file.filename
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في معالجة الملف: {str(e)}")

@app.get("/api/analyze")
async def analyze_metadata(filename: str):
    """تحليل البيانات الوصفية للفيديو"""
    try:
        file_path = UPLOAD_DIR / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="الملف غير موجود")
        
        video_info = get_video_info(str(file_path))
        quality_analysis = calculate_quality_score(video_info)
        
        analysis = {
            "success": True,
            "filename": filename,
            "metadata": video_info,
            "quality_analysis": quality_analysis,
            "analysis": {
                "is_original": quality_analysis["score"] >= 70,
                "confidence": quality_analysis["confidence"],
                "confidence_level": quality_analysis["confidence_level"],
                "indicators": quality_analysis["indicators"],
                "score": quality_analysis["score"]
            }
        }
        
        return analysis
    except HTTPException as e:
        raise e
    except Exception as e:
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
