#!/usr/bin/env python3
import io
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, urlparse

from PIL import Image, ImageDraw, ImageTk, UnidentifiedImageError

try:
    import cairosvg
except Exception:
    cairosvg = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    TK_ROOT = TkinterDnD.Tk
    HAS_DND = True
except ImportError:
    DND_FILES = None
    TK_ROOT = tk.Tk
    HAS_DND = False


class PhotoEditorApp(TK_ROOT):
    PAD_X_RATIO = 0.08
    PAD_Y_RATIO = 0.08

    def __init__(self) -> None:
        super().__init__()
        self.title("Quick Crop + Compress")
        self.geometry("1100x760")
        self.minsize(920, 660)

        self.source_path: str | None = None
        self.working_image: Image.Image | None = None
        self.display_image: Image.Image | None = None
        self.tk_image: ImageTk.PhotoImage | None = None

        self.scale = 1.0
        self.image_x = 0
        self.image_y = 0

        self.crop_rect_id: int | None = None
        self.crop_start: tuple[int, int] | None = None
        self.crop_size_text_id: int | None = None
        self.crop_size_bg_id: int | None = None
        self.crop_overlay_id: int | None = None
        self.crop_overlay_tk: ImageTk.PhotoImage | None = None
        self.icon_image: tk.PhotoImage | None = None
        self.undo_image: Image.Image | None = None
        self.crop_info_font = tkfont.Font(family="Helvetica Neue", size=11, weight="bold")

        self.target_kb_var = tk.StringVar(value="300")
        self.max_width_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")

        self._setup_styles()
        self._build_ui()
        self._set_app_icon()
        if HAS_DND:
            self.after(50, self._enable_drag_and_drop)
        self.after(120, self._render_image)

    def _set_app_icon(self) -> None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        png_main_path = os.path.join(base_dir, "static", "imagine.png")
        png_fallback_path = os.path.join(base_dir, "static", "imagine_icon.png")
        svg_path = os.path.join(base_dir, "static", "imagine.svg")
        png_candidates = [png_main_path, png_fallback_path]

        for png_path in png_candidates:
            if not os.path.isfile(png_path):
                continue
            try:
                icon_pil = Image.open(png_path).convert("RGBA")
                self.icon_image = ImageTk.PhotoImage(icon_pil)
                self.iconphoto(True, self.icon_image)
                self._set_macos_dock_icon(icon_pil)
                return
            except Exception:
                continue

        if cairosvg is not None and os.path.isfile(svg_path):
            try:
                png_bytes = cairosvg.svg2png(
                    url=svg_path,
                    output_width=256,
                    output_height=256,
                )
                icon_pil = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
                self.icon_image = ImageTk.PhotoImage(icon_pil)
                self.iconphoto(True, self.icon_image)
                self._set_macos_dock_icon(icon_pil)
                return
            except Exception:
                pass

    def _set_macos_dock_icon(self, icon_pil: Image.Image) -> None:
        if sys.platform != "darwin":
            return
        try:
            from AppKit import NSApplication, NSImage
            from Foundation import NSData
        except ImportError:
            return

        png_buffer = io.BytesIO()
        icon_pil.save(png_buffer, format="PNG")
        png_data = png_buffer.getvalue()

        ns_data = NSData.dataWithBytes_length_(png_data, len(png_data))
        ns_image = NSImage.alloc().initWithData_(ns_data)
        if ns_image is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(ns_image)

    def _setup_styles(self) -> None:
        self.configure(bg="#eef3f8")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background="#eef3f8")
        style.configure("Bar.TFrame", background="#f8fbff")
        style.configure("Field.TLabel", background="#f8fbff", foreground="#5a6b82")
        style.configure("Unit.TLabel", background="#f8fbff", foreground="#97a3b5")
        style.configure("Primary.TButton", foreground="#ffffff", background="#5f8fe8", padding=(11, 4))
        style.map(
            "Primary.TButton",
            background=[("active", "#4f81dd"), ("pressed", "#416fc9"), ("disabled", "#a7c0ef")],
            foreground=[("disabled", "#edf4ff")],
        )
        style.configure(
            "Neutral.TButton",
            padding=(10, 4),
            background="#eaf1fb",
            foreground="#3f5878",
            bordercolor="#d7e2f4",
        )
        style.map(
            "Neutral.TButton",
            background=[("active", "#dfe9f8"), ("pressed", "#d3e0f4")],
        )
        style.configure("TEntry", fieldbackground="#ffffff")

    def _build_ui(self) -> None:
        main = ttk.Frame(self, style="App.TFrame", padding=(14, 12, 14, 12))
        main.pack(fill="both", expand=True)

        control_row = ttk.Frame(main, style="Bar.TFrame", padding=(12, 10))
        control_row.pack(fill="x", pady=(0, 10))

        ttk.Button(control_row, text="Open", style="Primary.TButton", command=self.open_image, takefocus=False).pack(
            side="left", padx=(0, 8)
        )
        self.crop_button = ttk.Button(
            control_row, text="Crop", style="Neutral.TButton", command=self.on_crop_or_undo, takefocus=False
        )
        self.crop_button.pack(side="left", padx=(0, 8))
        ttk.Button(control_row, text="Save", style="Neutral.TButton", command=self.save_cropped, takefocus=False).pack(
            side="left", padx=(0, 16)
        )

        ttk.Separator(control_row, orient="vertical").pack(side="left", fill="y", padx=(0, 16))

        ttk.Label(control_row, text="max size", style="Field.TLabel").pack(side="left")
        size_input = ttk.Frame(control_row, style="Bar.TFrame")
        size_input.pack(side="left", padx=(6, 14))
        ttk.Entry(size_input, width=7, textvariable=self.target_kb_var, justify="right").pack(side="left")
        ttk.Label(size_input, text="KB", style="Unit.TLabel").pack(side="left", padx=(6, 0))

        ttk.Label(control_row, text="max width", style="Field.TLabel").pack(side="left")
        width_input = ttk.Frame(control_row, style="Bar.TFrame")
        width_input.pack(side="left", padx=(6, 12))
        ttk.Entry(width_input, width=7, textvariable=self.max_width_var, justify="right").pack(side="left")
        ttk.Label(width_input, text="px", style="Unit.TLabel").pack(side="left", padx=(6, 0))

        ttk.Button(
            control_row,
            text="Compress",
            style="Neutral.TButton",
            command=self.save_compressed,
            takefocus=False,
        ).pack(side="left")

        canvas_card = ttk.Frame(main, style="Bar.TFrame", padding=(12, 12))
        canvas_card.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_card, background="#b9bec7", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        self.bind("<Configure>", self._on_window_resize)
        self.bind("<Escape>", self._on_escape_key)

    def _on_window_resize(self, event: tk.Event) -> None:
        if event.widget == self:
            self.after(30, self._render_image)

    def open_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose image",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._load_image(path)

    def _load_image(self, path: str) -> bool:
        if not os.path.isfile(path):
            messagebox.showerror("Open failed", f"Not a file:\n{path}")
            return False

        try:
            loaded = Image.open(path)
            loaded.load()
        except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:
            messagebox.showerror("Open failed", f"Cannot open image:\n{exc}")
            return False

        self.source_path = path
        self.working_image = loaded.copy()
        self.undo_image = None
        self._set_crop_button_mode(is_undo=False)
        self.status_var.set("")
        self._render_image()
        return True

    def _enable_drag_and_drop(self) -> None:
        for widget in self._walk_widgets(self):
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)
            except (AttributeError, tk.TclError):
                continue

    def _on_drop(self, event: tk.Event) -> None:
        dropped_path = self._extract_dropped_path(getattr(event, "data", ""))
        if not dropped_path:
            self.status_var.set("")
            return
        self._load_image(dropped_path)

    def _walk_widgets(self, root: tk.Misc) -> list[tk.Misc]:
        widgets = [root]
        for child in root.winfo_children():
            widgets.extend(self._walk_widgets(child))
        return widgets

    def _extract_dropped_path(self, raw_data: str) -> str | None:
        if not raw_data:
            return None

        try:
            candidates = self.tk.splitlist(raw_data)
        except tk.TclError:
            candidates = [raw_data]

        for item in candidates:
            path = self._normalize_drop_item(item)
            if path and os.path.isfile(path):
                return path
        return None

    def _normalize_drop_item(self, item: str) -> str | None:
        token = item.strip()
        if token.startswith("{") and token.endswith("}"):
            token = token[1:-1]
        if not token:
            return None

        if token.startswith("file://"):
            parsed = urlparse(token)
            token = unquote(parsed.path or "")
            if parsed.netloc and parsed.netloc != "localhost":
                token = f"/{parsed.netloc}{token}"

        token = os.path.expanduser(token)
        return os.path.abspath(token)

    def _render_image(self) -> None:
        self.canvas.delete("all")
        self.crop_rect_id = None
        self.crop_start = None
        self.crop_size_text_id = None
        self.crop_size_bg_id = None
        self.crop_overlay_id = None
        self.crop_overlay_tk = None

        if self.working_image is None:
            return

        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)
        src_w, src_h = self.working_image.size

        pad_x = int(canvas_w * self.PAD_X_RATIO)
        pad_y = int(canvas_h * self.PAD_Y_RATIO)
        usable_w = max(canvas_w - (2 * pad_x), 1)
        usable_h = max(canvas_h - (2 * pad_y), 1)

        fit_scale = min(usable_w / src_w, usable_h / src_h, 1.0)
        disp_w = max(int(src_w * fit_scale), 1)
        disp_h = max(int(src_h * fit_scale), 1)

        self.scale = fit_scale
        self.image_x = (canvas_w - disp_w) // 2
        self.image_y = (canvas_h - disp_h) // 2

        if (disp_w, disp_h) != self.working_image.size:
            self.display_image = self.working_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        else:
            self.display_image = self.working_image

        self.tk_image = ImageTk.PhotoImage(self.display_image)
        self.canvas.create_image(self.image_x, self.image_y, anchor="nw", image=self.tk_image)

    def _on_mouse_down(self, event: tk.Event) -> None:
        if self.display_image is None:
            return

        x, y = self._clamp_to_image(event.x, event.y, require_inside=False)
        if x is None or y is None:
            return

        self._clear_crop_selection()

        self.crop_start = (x, y)
        self.crop_rect_id = self.canvas.create_rectangle(
            x, y, x, y, outline="#4f80d8", width=2, dash=(4, 2)
        )

    def _on_mouse_drag(self, event: tk.Event) -> None:
        if self.crop_rect_id is None or self.crop_start is None:
            return

        x, y = self._clamp_to_image(event.x, event.y)
        if x is None or y is None:
            return

        sx, sy = self.crop_start
        self.canvas.coords(self.crop_rect_id, sx, sy, x, y)
        self._update_crop_overlay()
        self._update_crop_size_indicator()

    def _on_mouse_up(self, _event: tk.Event) -> None:
        return

    def _on_escape_key(self, _event: tk.Event) -> None:
        self._clear_crop_selection()

    def _clear_crop_selection(self) -> None:
        self._clear_crop_overlay()
        self._clear_crop_size_indicator()
        if self.crop_rect_id is not None:
            self.canvas.delete(self.crop_rect_id)
            self.crop_rect_id = None
        self.crop_start = None

    def _clear_crop_overlay(self) -> None:
        if self.crop_overlay_id is not None:
            self.canvas.delete(self.crop_overlay_id)
            self.crop_overlay_id = None
        self.crop_overlay_tk = None

    def _update_crop_overlay(self) -> None:
        if self.crop_rect_id is None:
            self._clear_crop_overlay()
            return
        if self.display_image is None:
            self._clear_crop_overlay()
            return

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])

        if (right - left) < 2 or (bottom - top) < 2:
            self._clear_crop_overlay()
            return

        img_left = self.image_x
        img_top = self.image_y
        img_right = self.image_x + self.display_image.size[0]
        img_bottom = self.image_y + self.display_image.size[1]
        overlay_width = self.display_image.size[0]
        overlay_height = self.display_image.size[1]

        cut_left = max(0, min(int(left - img_left), overlay_width))
        cut_top = max(0, min(int(top - img_top), overlay_height))
        cut_right = max(0, min(int(right - img_left), overlay_width))
        cut_bottom = max(0, min(int(bottom - img_top), overlay_height))

        overlay = Image.new("RGBA", (overlay_width, overlay_height), (127, 147, 175, 177))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle((cut_left, cut_top, cut_right, cut_bottom), fill=(0, 0, 0, 0))

        self.crop_overlay_tk = ImageTk.PhotoImage(overlay)
        if self.crop_overlay_id is None:
            self.crop_overlay_id = self.canvas.create_image(
                img_left, img_top, anchor="nw", image=self.crop_overlay_tk
            )
        else:
            self.canvas.itemconfigure(self.crop_overlay_id, image=self.crop_overlay_tk)

        self.canvas.tag_raise(self.crop_overlay_id)
        self.canvas.tag_raise(self.crop_rect_id)

    def _clear_crop_size_indicator(self) -> None:
        if self.crop_size_bg_id is not None:
            self.canvas.delete(self.crop_size_bg_id)
            self.crop_size_bg_id = None
        if self.crop_size_text_id is not None:
            self.canvas.delete(self.crop_size_text_id)
            self.crop_size_text_id = None

    def _update_crop_size_indicator(self) -> None:
        if self.crop_rect_id is None:
            return
        if self.working_image is None:
            return

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])
        if (right - left) < 2 or (bottom - top) < 2:
            self._clear_crop_size_indicator()
            return

        src_w, src_h = self.working_image.size
        src_x1 = int((left - self.image_x) / self.scale)
        src_y1 = int((top - self.image_y) / self.scale)
        src_x2 = int((right - self.image_x) / self.scale)
        src_y2 = int((bottom - self.image_y) / self.scale)

        src_x1 = max(0, min(src_x1, src_w - 1))
        src_y1 = max(0, min(src_y1, src_h - 1))
        src_x2 = max(src_x1 + 1, min(src_x2, src_w))
        src_y2 = max(src_y1 + 1, min(src_y2, src_h))

        width_px = src_x2 - src_x1
        height_px = src_y2 - src_y1
        text = f"{width_px} x {height_px}"

        # Prefer below-right placement of the selection box.
        label_x = int(right) + 8
        label_y = int(bottom) + 8
        text_w = self.crop_info_font.measure(text)
        text_h = self.crop_info_font.metrics("linespace")
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)
        padding_x = 7
        padding_y = 4

        if label_x + text_w + (padding_x * 2) > canvas_w:
            label_x = max(int(left) - text_w - (padding_x * 2) - 8, 2)
        if label_y + text_h + (padding_y * 2) > canvas_h:
            label_y = max(int(top) - text_h - (padding_y * 2) - 8, 2)

        self._clear_crop_size_indicator()
        self.crop_size_text_id = self.canvas.create_text(
            label_x + padding_x,
            label_y + padding_y,
            anchor="nw",
            text=text,
            fill="#f8fbff",
            font=self.crop_info_font,
        )
        text_bbox = self.canvas.bbox(self.crop_size_text_id)
        if text_bbox is None:
            return

        self.crop_size_bg_id = self.canvas.create_rectangle(
            text_bbox[0] - 3,
            text_bbox[1] - 2,
            text_bbox[2] + 3,
            text_bbox[3] + 2,
            fill="#6d98e8",
            outline="#5a84d4",
            width=1,
        )
        self.canvas.tag_raise(self.crop_size_text_id, self.crop_size_bg_id)

    def _set_crop_button_mode(self, is_undo: bool) -> None:
        self.crop_button.configure(text="Undo" if is_undo else "Crop")

    def on_crop_or_undo(self) -> None:
        if self.undo_image is not None:
            self.undo_last_crop()
            return
        self.apply_crop()

    def _clamp_to_image(
        self, x: int, y: int, require_inside: bool = False
    ) -> tuple[int | None, int | None]:
        if self.display_image is None:
            return (None, None)

        img_w, img_h = self.display_image.size
        left, top = self.image_x, self.image_y
        right, bottom = left + img_w, top + img_h

        if require_inside and (x < left or x > right or y < top or y > bottom):
            return (None, None)

        return (max(min(x, right), left), max(min(y, bottom), top))

    def apply_crop(self) -> None:
        if self.working_image is None:
            self.status_var.set("")
            return
        if self.crop_rect_id is None:
            self.status_var.set("")
            return

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])

        if (right - left) < 5 or (bottom - top) < 5:
            self.status_var.set("")
            return

        self.undo_image = self.working_image.copy()
        src_x1 = int((left - self.image_x) / self.scale)
        src_y1 = int((top - self.image_y) / self.scale)
        src_x2 = int((right - self.image_x) / self.scale)
        src_y2 = int((bottom - self.image_y) / self.scale)

        src_w, src_h = self.working_image.size
        src_x1 = max(0, min(src_x1, src_w - 1))
        src_y1 = max(0, min(src_y1, src_h - 1))
        src_x2 = max(src_x1 + 1, min(src_x2, src_w))
        src_y2 = max(src_y1 + 1, min(src_y2, src_h))

        self.working_image = self.working_image.crop((src_x1, src_y1, src_x2, src_y2))
        self._set_crop_button_mode(is_undo=True)
        self.status_var.set("")
        self._render_image()

    def undo_last_crop(self) -> None:
        if self.undo_image is None:
            return
        self.working_image = self.undo_image
        self.undo_image = None
        self._set_crop_button_mode(is_undo=False)
        self.status_var.set("")
        self._render_image()

    def save_cropped(self) -> None:
        if self.working_image is None:
            messagebox.showinfo("No image", "Open an image first.")
            return

        output = filedialog.asksaveasfilename(
            title="Save",
            initialfile=os.path.basename(self._default_cropped_output_path()),
            defaultextension=".png",
            filetypes=[
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
                ("WebP", "*.webp"),
                ("TIFF", "*.tif *.tiff"),
                ("BMP", "*.bmp"),
            ],
        )
        if not output:
            return

        try:
            self._save_image_by_extension(self.working_image, output)
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save image:\n{exc}")
            return

        self.status_var.set("")

    def save_compressed(self) -> None:
        if self.working_image is None:
            messagebox.showinfo("No image", "Open an image first.")
            return

        target_kb_text = self.target_kb_var.get().strip()
        max_width_text = self.max_width_var.get().strip()

        target_kb: int | None = None
        if target_kb_text:
            try:
                target_kb = int(target_kb_text)
                if target_kb <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid target", "Target size must be a positive integer in KB.")
                return

        max_width: int | None = None
        if max_width_text:
            try:
                max_width = int(max_width_text)
                if max_width <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid width", "Max width must be a positive integer.")
                return

        output = filedialog.asksaveasfilename(
            title="Save",
            initialfile=os.path.basename(self._default_compressed_output_path()),
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg *.jpeg")],
        )
        if not output:
            return

        to_save = self.working_image.copy()
        if max_width is not None and to_save.width > max_width:
            ratio = max_width / to_save.width
            resized_h = max(int(to_save.height * ratio), 1)
            to_save = to_save.resize((max_width, resized_h), Image.Resampling.LANCZOS)

        if to_save.mode != "RGB":
            to_save = to_save.convert("RGB")

        try:
            self._write_jpeg(to_save, output, target_kb=target_kb)
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save JPEG:\n{exc}")
            return

        self.status_var.set("")

    def _default_cropped_output_path(self) -> str:
        if self.source_path is None:
            return "output_cropped.png"
        root, _ext = os.path.splitext(self.source_path)
        return f"{root}_cropped.png"

    def _default_compressed_output_path(self) -> str:
        if self.source_path is None:
            return "output_compressed.jpg"
        root, _ext = os.path.splitext(self.source_path)
        return f"{root}_compressed.jpg"

    def _save_image_by_extension(self, image: Image.Image, output_path: str) -> None:
        ext = os.path.splitext(output_path)[1].lower()

        if ext in (".jpg", ".jpeg"):
            if image.mode != "RGB":
                image = image.convert("RGB")
            image.save(output_path, format="JPEG", quality=95, optimize=True)
            return

        if ext == ".png":
            image.save(output_path, format="PNG", optimize=True)
            return

        if ext == ".webp":
            image.save(output_path, format="WEBP", quality=95)
            return

        if ext in (".tif", ".tiff"):
            image.save(output_path, format="TIFF")
            return

        if ext == ".bmp":
            image.save(output_path, format="BMP")
            return

        image.save(output_path)

    def _write_jpeg(self, image: Image.Image, output_path: str, target_kb: int | None) -> None:
        if target_kb is None:
            image.save(output_path, format="JPEG", quality=90, optimize=True, progressive=True)
            return

        target_bytes = target_kb * 1024
        low_quality = 20
        high_quality = 95
        best_blob: bytes | None = None

        while low_quality <= high_quality:
            quality = (low_quality + high_quality) // 2
            blob = self._encode_jpeg(image, quality)
            if len(blob) <= target_bytes:
                best_blob = blob
                low_quality = quality + 1
            else:
                high_quality = quality - 1

        if best_blob is None:
            best_blob = self._encode_jpeg(image, 20)

        with open(output_path, "wb") as f:
            f.write(best_blob)

    def _encode_jpeg(self, image: Image.Image, quality: int) -> bytes:
        data = io.BytesIO()
        try:
            image.save(
                data,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
            )
        except OSError:
            data = io.BytesIO()
            image.save(data, format="JPEG", quality=quality)
        return data.getvalue()


def main() -> None:
    app = PhotoEditorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
