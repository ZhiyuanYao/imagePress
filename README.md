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

If drag-and-drop does not work, check that DnD support is installed in the same Python environment:

```bash
source .venv/bin/activate
pip install tkinterdnd2
python -c "import tkinterdnd2; print('DnD OK')"
```

## Usage

1. Click `Open`
   - or drag an image file into the app window
2. Drag on the image to draw a crop box
   - drawing a new rectangle replaces the previous selection
   - press `Esc` to clear current crop selection
3. Click `Crop` to commit the crop
4. After crop, `Crop` becomes `Undo` for one-step crop rollback
5. Use `Save` for direct export
6. Use `Compress` if you want size-target compression (`KB`) and optional resize width (`W`)

## Build as macOS app (optional)

If you want a double-clickable `.app` bundle:

```bash
source .venv/bin/activate
pip install pyinstaller
pyinstaller --windowed --name QuickCropCompress photo_editor_app.py
```

Generated app:
- `dist/QuickCropCompress.app`
