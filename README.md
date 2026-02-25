# Quick Crop + Compress (macOS)

Small desktop image editor focused on:
- Crop by drag-selecting a rectangle
- Save cropped result directly (without size-target compression)
- Compress to a target JPEG size (KB)
- Optional max-width resize during export
- Drag and drop image files to open

This is a lightweight local app using `tkinter + Pillow`, which is simpler than a full Pintura integration when you mainly need crop + compress.
The app icon is loaded from `static/imagine.png` (`static/imagine.svg` is optional fallback if `cairosvg` is available).
On macOS, Dock icon update uses Cocoa (`pyobjc-framework-Cocoa`).

## Run

```bash
cd /Users/zhiyuanyao/Nutstore/System/Python/Library/imagine
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python photo_editor_app.py
```

Open an image directly from command line:

```bash
python photo_editor_app.py /path/to/image.jpg
```

If drag-and-drop does not work, check that DnD support is installed in the same Python environment:

```bash
source .venv/bin/activate
pip install tkinterdnd2
python -c "import tkinterdnd2; print('DnD OK')"
```

## Usage

1. Click `Open`
   - or drag an image file into the app window
2. Click `Crop` to enter crop mode
3. Drag the corner handles (`⌜ ⌝ ⌞ ⌟`) to adjust the crop region
   - press `Esc` to clear the current crop selection/mode
4. Click `Crop` again to apply the crop
5. After crop, `Crop` becomes `Undo` for one-step rollback
6. Use `Save` for direct export
7. Use `Compress` if you want size-target compression (`max size`) and optional resize width (`max width`)

## Build as macOS app (optional)

If you want a double-clickable `.app` bundle:

```bash
source .venv/bin/activate
pip install pyinstaller
pyinstaller --windowed --name QuickCropCompress photo_editor_app.py
```

Generated app:
- `dist/QuickCropCompress.app`
