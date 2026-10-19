@echo off
REM Windows launcher: reels [reel numbers] [--preview] [--source "G:\My Drive\Vlog"]
where ffmpeg >nul 2>nul || (
  echo ffmpeg is not installed. Run this once, then open a new window:
  echo     winget install Gyan.FFmpeg
  exit /b 1
)
python -c "import PIL" 2>nul || python -m pip install --quiet pillow
python "%~dp0reels\make_reels.py" %*
