@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [!] 未找到虚拟环境,请先按 README.md 创建并安装依赖
    exit /b 1
)

echo [1/2] PyInstaller 打包...
".venv\Scripts\pyinstaller.exe" packaging\liteseal.spec --noconfirm
if errorlevel 1 exit /b 1

echo [2/2] Inno Setup 制作安装包...
where iscc >nul 2>nul
if errorlevel 1 (
    echo [!] 未找到 Inno Setup ^(iscc^),已生成 dist\LiteSeal 文件夹,
    echo     安装 https://jrsoftware.org/isinfo.php 后重跑本脚本,或直接分发 dist 文件夹
    exit /b 0
)
iscc packaging\setup.iss
echo 完成:packaging\dist\LiteSeal-Setup-0.1.0.exe
