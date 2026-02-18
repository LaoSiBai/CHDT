@echo off
chcp 65001 >nul 2>&1
title 彩色电台 - 环境一键安装
echo ============================================================
echo   彩色电台 - 环境一键安装脚本
echo   适用于 Windows 10/11 服务器
echo ============================================================
echo.

:: ─────────── 0. 检查并安装 Git ───────────
echo [1/5] 正在检查 Git...
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo   [!] 未检测到 Git，正在尝试通过 winget 安装...
    winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements >nul 2>&1
    if %errorlevel% neq 0 (
        echo   [!] winget 安装 Git 失败，正在从国内镜像下载安装包...
        echo   [!] 正在下载 Git 安装程序（约 60MB）...
        powershell -Command "Invoke-WebRequest -Uri 'https://registry.npmmirror.com/-/binary/git-for-windows/v2.45.2.windows.1/Git-2.45.2-64-bit.exe' -OutFile '%TEMP%\git_setup.exe'"
        if exist "%TEMP%\git_setup.exe" (
            echo   [+] 下载完成，正在静默安装 Git...
            "%TEMP%\git_setup.exe" /VERYSILENT /NORESTART /SP-
            del "%TEMP%\git_setup.exe"
            :: 刷新环境变量
            set "PATH=%PATH%;C:\Program Files\Git\cmd"
            echo   [OK] Git 安装完成。
        ) else (
            echo   [X] Git 下载失败，请手动安装 Git。
        )
    ) else (
        echo   [OK] Git 通过 winget 安装成功。
        set "PATH=%PATH%;C:\Program Files\Git\cmd"
    )
) else (
    echo   [OK] Git 已安装。
)
echo.

:: ─────────── 1. 检查并安装 Python ───────────
echo [2/5] 正在检查 Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   [!] 未检测到 Python，正在尝试通过 winget 安装...
    winget install --id Python.Python.3.11 -e --source winget --accept-package-agreements --accept-source-agreements >nul 2>&1
    if %errorlevel% neq 0 (
        echo   [!] winget 安装失败，正在从 Python 官网下载安装包...
        echo   [!] 正在下载 Python 安装程序（约 25MB）...
        powershell -Command "Invoke-WebRequest -Uri 'https://registry.npmmirror.com/-/binary/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%TEMP%\python_setup.exe'"
        if exist "%TEMP%\python_setup.exe" (
            echo   [+] 下载完成，正在静默安装 Python...
            "%TEMP%\python_setup.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
            del "%TEMP%\python_setup.exe"
            echo   [OK] Python 安装完成。
            echo   [!!] 重要：请关闭此窗口，重新打开后再运行本脚本一次！
            pause
            exit
        ) else (
            echo   [X] Python 下载失败，请手动安装 Python 3.8+。
            pause
            exit
        )
    ) else (
        echo   [OK] Python 通过 winget 安装成功。
        echo   [!!] 重要：请关闭此窗口，重新打开后再运行本脚本一次！
        pause
        exit
    )
) else (
    python --version
    echo   [OK] Python 已安装。
)
echo.

:: ─────────── 2. 升级 pip ───────────
echo [3/5] 正在升级 pip...
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
echo   [OK] pip 已是最新版本。
echo.

:: ─────────── 3. 安装 Python 依赖包 ───────────
echo [4/5] 正在安装 Python 依赖包（使用清华镜像源）...
echo   -> yt-dlp
python -m pip install yt-dlp -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
echo   -> librosa
python -m pip install librosa -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
echo   -> soundfile
python -m pip install soundfile -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
echo   -> imageio-ffmpeg (内含 FFmpeg)
python -m pip install imageio-ffmpeg -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
echo   -> pandas
python -m pip install pandas -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
echo   -> openpyxl
python -m pip install openpyxl -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
echo   -> numpy
python -m pip install numpy -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
echo   [OK] 所有依赖安装完成。
echo.

:: ─────────── 4. 创建必要文件夹 ───────────
echo [5/5] 正在检查文件夹结构...
if not exist "BLUE"  mkdir BLUE  & echo   [+] 已创建 BLUE
if not exist "GREEN" mkdir GREEN & echo   [+] 已创建 GREEN
if not exist "RED"   mkdir RED   & echo   [+] 已创建 RED
echo   [OK] 文件夹结构就绪。
echo.

:: ─────────── 完成 ───────────
echo ============================================================
echo   环境配置全部完成！
echo.
echo   接下来请运行：
echo     python bpm_classifier.py
echo ============================================================
pause
