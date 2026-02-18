# 彩色电台 - 环境安装脚本 (Win11 PowerShell)
# ==========================================

# 1. 检查 Python
Write-Host "🔍 正在检查 Python..." -ForegroundColor Cyan
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ 错误: 未找到 Python。请先安装 Python 3.8+ 并勾选 'Add to PATH'。" -ForegroundColor Red
    exit
}
python --version

# 2. 升级 pip
Write-Host "`n🆙 正在升级 pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

# 3. 安装依赖包
Write-Host "`n📦 正在安装 Python 依赖 (yt-dlp, librosa, pandas 等)..." -ForegroundColor Cyan
# 使用清华源以确保国内服务器下载速度
$packages = "yt-dlp", "librosa", "soundfile", "imageio-ffmpeg", "pandas", "openpyxl", "numpy"
foreach ($pkg in $packages) {
    Write-Host "  -> 正在安装 $pkg..."
    python -m pip install $pkg -i https://pypi.tuna.tsinghua.edu.cn/simple
}

# 4. 创建必要文件夹
Write-Host "`n📁 正在检查文件夹结构..." -ForegroundColor Cyan
$dirs = "BLUE", "GREEN", "RED", "表格"
foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "  ✅ 已创建文件夹: $dir"
    } else {
        Write-Host "  ✔ 文件夹已存在: $dir"
    }
}

# 5. 完成
Write-Host "`n✨ 环境配置完成！" -ForegroundColor Green
Write-Host "-------------------------------------------------------"
Write-Host "您可以现在运行脚本了:"
Write-Host "python bpm_classifier.py" -ForegroundColor Yellow
Write-Host "-------------------------------------------------------"
pause
