@echo off
REM ============================================================
REM  Satranc Antrenman Asistani - Windows .exe derleme scripti
REM  Cift tikla, bitince dist\SatrancAsistan klasoru hazir olur.
REM ============================================================
cd /d "%~dp0"

echo [1/4] Python kontrol...
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Python bulunamadi! https://www.python.org/downloads/ adresinden kur,
  echo kurulumda "Add python.exe to PATH" kutusunu isaretle.
  pause
  exit /b 1
)

echo [2/4] Sanal ortam + kutuphaneler...
if not exist venv (
  py -3 -m venv venv
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install PyQt6 numpy mss pyautogui keyboard pyinstaller
if errorlevel 1 ( echo Kutuphane kurulumu basarisiz! & pause & exit /b 1 )

echo [3/4] Stockfish indiriliyor (resmi GitHub yayini)...
if not exist stockfish md stockfish
if not exist stockfish\stockfish.exe (
  curl -L -o stockfish.zip https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-windows-x86-64-avx2.zip
  tar -xf stockfish.zip
  for /r %%f in (stockfish-*.exe) do if not exist stockfish\stockfish.exe copy "%%f" stockfish\stockfish.exe >nul 2>&1
  del stockfish.zip 2>nul
)
if not exist stockfish\stockfish.exe (
  curl -L -o stockfish.zip https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-windows-x86-64-universal.zip
  tar -xf stockfish.zip
  for /r %%f in (stockfish-*.exe) do if not exist stockfish\stockfish.exe copy "%%f" stockfish\stockfish.exe >nul 2>&1
  del stockfish.zip 2>nul
)
if not exist stockfish\stockfish.exe (
  echo UYARI: Stockfish indirilemedi. https://stockfishchess.org/download/
  echo adresinden elle indirip stockfish klasorune koy.
)

echo [4/4] .exe derleniyor (1-3 dakika surebilir)...
pyinstaller --noconsole --onedir --name SatrancAsistan ^
  --collect-submodules PyQt6 main.py
if errorlevel 1 ( echo Derleme basarisiz! & pause & exit /b 1 )

if exist stockfish (
  xcopy /e /i /y stockfish dist\SatrancAsistan\stockfish >nul
)
echo.
echo BITTI!  Program: dist\SatrancAsistan\SatrancAsistan.exe
echo (Tum dist klasorunu birlikte tasi; stockfish klasoru yaninda kalmali)
pause