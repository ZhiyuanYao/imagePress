# Quick Image Utilities (macOS)

Small desktop utility focused on convert, crop, resize, and compress workflows:
- Convert between common image formats (JPEG, PNG, TIFF) without leaving the app
- Crop by drag-selecting a rectangle
- Resize via the bottom-right guide and optional max-width export
- Compress to a target JPEG size (KB) while applying the current crop/resize
- Drag and drop image files to open

## Version 0.1

- Feature a compact Convert → Crop → Resize → Compress pipeline for local image tweaks.
- Refresh ImagePress branding with `static/imagePress.png` (macOS icon generated via `scripts/build_icon.py`).
- Keep README, spec, and assets aligned so the packaged macOS bundle mirrors the utility demo.

This is a lightweight local app using `tkinter + Pillow`, which is simpler than a full Pintura integration when you mainly need crop + compress.
The app icon is loaded from `static/imagePress.png` (`static/imagePress.svg` is optional fallback if `cairosvg` is available).
On macOS, Dock icon update uses Cocoa (`pyobjc-framework-Cocoa`).

## Run

```bash
cd /Users/zhiyuanyao/Nutstore/System/Python/Library/imagePress
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
5. Click `Resize` to enter resize mode and drag the bottom-right guide (`⌟`) to set target W x H
6. Click `Resize` again to apply the resize
7. After apply, that action button becomes `Undo` for one-step rollback
8. Use `Save` for direct export
9. In resize mode, you can directly click `Compress` to apply resize and export compressed output

## Build as macOS app (optional)

If you want a double-clickable `.app` bundle:

```bash
source .venv/bin/activate
pip install pyinstaller
pyinstaller --windowed --name QuickCropCompress photo_editor_app.py
```

Generated app:
- `dist/QuickCropCompress.app`
