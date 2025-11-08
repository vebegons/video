Document.addEventListener('DOMContentLoaded', () => {
    const uploadArea = document.getElementById('uploadArea');
    const videoInput = document.getElementById('videoInput');
    const uploadForm = document.getElementById('uploadForm');
    const loadingSection = document.getElementById('loadingSection');
    const resultsSection = document.getElementById('resultsSection');
    const metadataTableBody = document.getElementById('metadataTableBody');
    const scoreCircle = document.getElementById('scoreCircle');
    const scoreText = document.getElementById('scoreText');
    const confidenceLevel = document.getElementById('confidenceLevel');
    const indicatorsList = document.getElementById('indicatorsList');
    const framesGrid = document.getElementById('framesGrid');
    const tabs = document.querySelectorAll('.nav-btn');
    const contents = document.querySelectorAll('.main-content');

    // Tab switching logic
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));

            tab.classList.add('active');
            const target = document.getElementById(tab.dataset.target);
            if (target) {
                target.classList.add('active');
            }
        });
    });

    // Initial state
    document.getElementById('uploadTab').classList.add('active');
    document.getElementById('uploadSection').classList.add('active');

    // Drag and Drop functionality
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        uploadArea.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, unhighlight, false);
    });

    function highlight() {
        uploadArea.classList.add('dragover');
    }

    function unhighlight() {
        uploadArea.classList.remove('dragover');
    }

    uploadArea.addEventListener('click', () => {
        videoInput.click();
    });

    videoInput.addEventListener('change', () => {
        if (videoInput.files.length > 0) {
            handleFiles(videoInput.files);
        }
    });

    uploadArea.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    });

    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            if (file.type.startsWith('video/')) {
                // Display file name and prepare for upload
                document.getElementById('fileNameDisplay').textContent = `الملف المحدد: ${file.name}`;
                document.getElementById('uploadButton').style.display = 'inline-block';
                // Set file to form data for manual submission
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(file);
                videoInput.files = dataTransfer.files;
            } else {
                showError('الرجاء تحديد ملف فيديو صالح.');
            }
        }
    }

    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        if (videoInput.files.length === 0) {
            showError('الرجاء تحديد ملف فيديو للتحميل.');
            return;
        }

        // Hide upload section, show loading
        document.getElementById('uploadSection').classList.remove('active');
        resultsSection.classList.remove('active');
        loadingSection.classList.add('active');
        document.getElementById('uploadButton').style.display = 'none';
        document.getElementById('fileNameDisplay').textContent = 'الرجاء سحب وإفلات ملف فيديو أو النقر هنا للتحميل';

        const formData = new FormData();
        const fileToUpload = videoInput.files[0];
        // 🌟 التعديل المطلوب: إضافة الملف بشكل صريح إلى FormData
        formData.append('file', fileToUpload, fileToUpload.name); 
        
        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            loadingSection.classList.remove('active');

            if (response.ok) {
                const result = await response.json();
                displayResults(result);
                showSuccess('تم تحليل الفيديو بنجاح!');
            } else {
                const error = await response.json();
                showError(`خطأ في التحليل: ${error.detail || 'حدث خطأ غير متوقع.'}`);
                document.getElementById('uploadSection').classList.add('active');
            }
        } catch (error) {
            loadingSection.classList.remove('active');
            showError(`خطأ في الاتصال بالخادم: ${error.message}`);
            document.getElementById('uploadSection').classList.add('active');
        }
    });

    function displayResults(data) {
        // Switch to results tab
        tabs.forEach(t => t.classList.remove('active'));
        document.getElementById('resultsTab').classList.add('active');
        contents.forEach(c => c.classList.remove('active'));
        resultsSection.classList.add('active');

        // 1. Metadata Table
        metadataTableBody.innerHTML = '';
        const metadata = data.video_info;
        for (const key in metadata) {
            const row = metadataTableBody.insertRow();
            const labelCell = row.insertCell();
            const valueCell = row.insertCell();
            labelCell.textContent = getMetadataLabel(key);
            valueCell.textContent = metadata[key];
        }

        // 2. Quality Score
        const scoreData = data.quality_analysis;
        const score = scoreData.score;
        const confidence = scoreData.confidence_level;
        const card = document.getElementById('qualityScoreCard');

        scoreCircle.textContent = `${score}%`;
        scoreText.textContent = `درجة الجودة: ${score}%`;
        confidenceLevel.textContent = `مستوى الثقة: ${confidence}`;

        card.classList.remove('high', 'medium', 'low');
        scoreCircle.classList.remove('high', 'medium', 'low');

        if (score >= 70) {
            card.classList.add('high');
            scoreCircle.classList.add('high');
        } else if (score >= 50) {
            card.classList.add('medium');
            scoreCircle.classList.add('medium');
        } else {
            card.classList.add('low');
            scoreCircle.classList.add('low');
        }

        // 3. Indicators List
        indicatorsList.innerHTML = '';
        scoreData.indicators.forEach(indicator => {
            const li = document.createElement('li');
            li.textContent = indicator;
            if (indicator.startsWith('✓')) {
                li.classList.add('success');
            } else if (indicator.startsWith('⚠')) {
                li.classList.add('warning');
            } else if (indicator.startsWith('✗')) {
                li.classList.add('danger');
            }
            indicatorsList.appendChild(li);
        });

        // 4. Frames Grid
        renderFrames(data.frames);
    }

    function getMetadataLabel(key) {
        const labels = {
            "filename": "اسم الملف",
            "file_size": "حجم الملف (بايت)",
            "created_date": "تاريخ الإنشاء",
            "modified_date": "تاريخ التعديل",
            "duration": "المدة",
            "resolution": "الدقة",
            "quality": "الجودة",
            "bitrate": "معدل البت",
            "codec_name": "ترميز الفيديو",
            "codec_long_name": "الترميز الكامل",
            "profile": "الملف الشخصي للترميز",
            "avg_frame_rate": "متوسط معدل الإطارات",
            "tags": "العلامات (Tags)"
        };
        return labels[key] || key;
    }

    function renderFrames(frames) {
        framesGrid.innerHTML = '';
        let html = '';
        frames.forEach((frame, index) => {
            html += `
                <div class="frame-card">
                    <img src="${frame.path}" alt="لقطة شاشة ${index + 1}" class="frame-image">
                    <div class="frame-actions">
                        <a href="#" onclick="searchFrame('${frame.path}', 'google'); return false;" class="search-btn search-btn-google">بحث جوجل</a>
                        <a href="#" onclick="searchFrame('${frame.path}', 'yandex'); return false;" class="search-btn search-btn-yandex">بحث ياندكس</a>
                        <a href="#" onclick="searchFrame('${frame.path}', 'tineye'); return false;" class="search-btn search-btn-tineye">بحث TinEye</a>
                        <a href="#" onclick="searchFrame('${frame.path}', 'archive'); return false;" class="search-btn search-btn-archive">أرشيف الإنترنت</a>
                    </div>
                </div>
            `;
        });

        framesGrid.innerHTML = html;
    }

    window.searchFrame = function(framePath, engine) {
        // Note: The framePath is already a public URL (e.g., /static/frames/...)
        // We use window.location.origin to construct the full URL for external search engines
        let searchUrl = '';
        const fullUrl = window.location.origin + framePath;

        switch(engine) {
            case 'google':
                // Google Lens/Images often requires a publicly accessible URL
                searchUrl = `https://lens.google.com/uploadbyurl?url=${encodeURIComponent(fullUrl)}`;
                break;
            case 'yandex':
                // Yandex Images also supports searching by URL
                searchUrl = `https://yandex.com/images/search?url=${encodeURIComponent(fullUrl)}`;
                break;
            case 'tineye':
                // TinEye supports searching by URL
                searchUrl = `https://tineye.com/search?url=${encodeURIComponent(fullUrl)}`;
                break;
            case 'archive':
                // This is a placeholder, as Archive.org doesn't have a direct reverse image search.
                // We'll link to a general search or the frame itself for now.
                searchUrl = fullUrl; 
                break;
        }

        if (searchUrl) {
            window.open(searchUrl, '_blank');
        }
    }

    function showError(message) {
        const errorDiv = document.getElementById('errorMessage');
        errorDiv.textContent = message;
        errorDiv.classList.add('active');
        setTimeout(() => errorDiv.classList.remove('active'), 5000);
    }

    function showSuccess(message) {
        const successDiv = document.getElementById('successMessage');
        successDiv.textContent = message;
        successDiv.classList.add('active');
        setTimeout(() => successDiv.classList.remove('active'), 5000);
    }
});
