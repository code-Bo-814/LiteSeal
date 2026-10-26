@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [!] Virtual environment not found. Please create it first.
    exit /b 1
)

echo [1/2] Building EXE with PyInstaller...
".venv\Scripts\pyinstaller.exe" packaging\liteseal.spec --noconfirm
if errorlevel 1 exit /b 1

echo [2/2] Building Setup with Inno Setup...
where iscc >nul 2>nul
if errorlevel 1 (
    echo [!] Inno Setup iscc not found. 
    exit /b 0
)
iscc packaging\setup.iss
echo Build Success: packaging\dist\LiteSeal-Setup-0.1.0.exe