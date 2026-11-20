# Build the Shorts app on Windows

The Windows .exe is built on a Windows PC from this same folder.
The steps below were written for Rayhan's Windows PC, which has
an NVIDIA GPU.

## 1. Install the tools

1. Python 3.12 from python.org. During install, tick **Add python
   to PATH**.
2. Git from git-scm.com (needed for nothing in the build itself,
   but useful). Not strictly required.
3. FFmpeg: download the essentials build from
   https://www.gyan.dev/ffmpeg/builds/ (`ffmpeg-release-essentials.zip`),
   unzip it, and add its `bin` folder to PATH. Verify in a new
   terminal: `ffmpeg -version` and `ffprobe -version`.

## 2. Get the project

Copy the `shorts-app` folder to the PC (USB, cloud drive, or git),
then open a terminal inside it.

## 3. Create the environment

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

This downloads PySide6, faster-whisper, MediaPipe, OpenCV,
onnxruntime, yt-dlp, streamlink and chat-downloader. It takes a
few minutes on first install.

## 4. Build the exe

```powershell
pyinstaller shorts-app.spec
```

The build takes several minutes. The result is
`dist\shorts-app.exe` — a single file, no Python needed to run it.

## 5. Run it

Double-click `dist\shorts-app.exe`. First launch is slow (the
one-file bundle unpacks itself). The window has a URL bar: paste
a YouTube or Twitch URL, press Detect, and go.

Notes:

- The exe needs internet for probing, downloading and live chat.
- Whisper models download on first use into the user cache
  (`%USERPROFILE%\.cache\huggingface`); tiny is ~75 MB.
- On a PC with an NVIDIA GPU, faster-whisper and the YOLOv8
  detector use CUDA automatically. On a CPU-only PC they fall
  back to CPU, slower but working.
- If Windows Defender flags the fresh exe, allow it: it is built
  from this source on this machine.
- To rebuild after changing the code, run step 4 again.
