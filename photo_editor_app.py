#!/usr/bin/env python3
import argparse
import io
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, urlparse

from PIL import Image, ImageTk, UnidentifiedImageError

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
    GUIDE_COLOR = "#78b0ff"

    def __init__(self, initial_path: str | None = None) -> None:
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
        self.crop_mode = False
        self.active_corner: str | None = None
        self.active_drag_mode: str | None = None
        self.move_anchor: tuple[int, int] | None = None
        self.crop_corner_ids: list[int] = []
        self.crop_size_text_id: int | None = None
        self.crop_size_bg_id: int | None = None
        self.crop_overlay_ids: list[int] = []
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
        if initial_path:
            self.after(80, lambda: self._open_initial_path(initial_path))
            self.after(130, self._bring_to_front)
        self.after(120, self._render_image)

    def _open_initial_path(self, path: str) -> None:
        normalized = os.path.abspath(os.path.expanduser(path))
        if not os.path.isfile(normalized):
            messagebox.showerror("Open failed", f"Not a file:\n{normalized}")
            return
        self._load_image(normalized)

    def _bring_to_front(self) -> None:
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(250, lambda: self.attributes("-topmost", False))
        except tk.TclError:
            pass

        if sys.platform == "darwin":
            try:
                from AppKit import NSApplication

                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            except Exception:
                pass

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
        self.crop_mode = False
        self.active_corner = None
        self.active_drag_mode = None
        self.move_anchor = None
        self._clear_corner_guides()
        self.crop_size_text_id = None
        self.crop_size_bg_id = None
        self.crop_overlay_ids = []

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

        if not self.crop_mode:
            return

        x, y = self._clamp_to_image(event.x, event.y, require_inside=False)
        if x is None or y is None:
            return

        self.active_corner = self._hit_corner_handle(x, y)
        if self.active_corner is not None:
            self.active_drag_mode = "corner"
            self.move_anchor = None
            return

        if self._point_in_crop_rect(x, y):
            self.active_drag_mode = "move"
            self.move_anchor = (x, y)
            return

        self.active_drag_mode = None
        self.move_anchor = None

    def _on_mouse_drag(self, event: tk.Event) -> None:
        if not self.crop_mode or self.crop_rect_id is None or self.active_drag_mode is None:
            return

        x, y = self._clamp_to_image(event.x, event.y)
        if x is None or y is None:
            return

        if self.active_drag_mode == "corner" and self.active_corner is not None:
            constrain_square = bool(getattr(event, "state", 0) & 0x0001)
            self._drag_corner_handle(self.active_corner, x, y, constrain_square=constrain_square)
        elif self.active_drag_mode == "move":
            self._drag_crop_region(x, y)
        else:
            return

        self._update_crop_overlay()
        self._draw_corner_guides()
        self._update_crop_size_indicator()

    def _on_mouse_up(self, _event: tk.Event) -> None:
        self.active_corner = None
        self.active_drag_mode = None
        self.move_anchor = None

    def _on_escape_key(self, _event: tk.Event) -> None:
        self._clear_crop_selection()
        self.crop_mode = False
        self.active_drag_mode = None
        self.move_anchor = None
        if self.undo_image is None:
            self._set_crop_button_mode(is_undo=False)

    def _clear_crop_selection(self) -> None:
        self.active_corner = None
        self.active_drag_mode = None
        self.move_anchor = None
        self._clear_corner_guides()
        self._clear_crop_overlay()
        self._clear_crop_size_indicator()
        if self.crop_rect_id is not None:
            self.canvas.delete(self.crop_rect_id)
            self.crop_rect_id = None
        self.crop_start = None

    def _clear_corner_guides(self) -> None:
        if not self.crop_corner_ids:
            return
        for guide_id in self.crop_corner_ids:
            self.canvas.delete(guide_id)
        self.crop_corner_ids = []

    def _draw_corner_guides(self) -> None:
        self._clear_corner_guides()
        if self.crop_rect_id is None:
            return

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])
        width = right - left
        height = bottom - top
        if width < 2 or height < 2:
            return

        seg = max(14, min(30, int(min(width, height) * 0.18)))
        color = self.GUIDE_COLOR
        thickness = 3

        # Top-left: ⌜
        self.crop_corner_ids.append(
            self.canvas.create_line(left, top, left + seg, top, fill=color, width=thickness, capstyle="round")
        )
        self.crop_corner_ids.append(
            self.canvas.create_line(left, top, left, top + seg, fill=color, width=thickness, capstyle="round")
        )
        # Top-right: ⌝
        self.crop_corner_ids.append(
            self.canvas.create_line(right - seg, top, right, top, fill=color, width=thickness, capstyle="round")
        )
        self.crop_corner_ids.append(
            self.canvas.create_line(right, top, right, top + seg, fill=color, width=thickness, capstyle="round")
        )
        # Bottom-left: ⌞
        self.crop_corner_ids.append(
            self.canvas.create_line(left, bottom, left + seg, bottom, fill=color, width=thickness, capstyle="round")
        )
        self.crop_corner_ids.append(
            self.canvas.create_line(left, bottom - seg, left, bottom, fill=color, width=thickness, capstyle="round")
        )
        # Bottom-right: ⌟
        self.crop_corner_ids.append(
            self.canvas.create_line(right - seg, bottom, right, bottom, fill=color, width=thickness, capstyle="round")
        )
        self.crop_corner_ids.append(
            self.canvas.create_line(right, bottom - seg, right, bottom, fill=color, width=thickness, capstyle="round")
        )

        for guide_id in self.crop_corner_ids:
            self.canvas.tag_raise(guide_id)

    def _hit_corner_handle(self, x: int, y: int) -> str | None:
        if self.crop_rect_id is None:
            return None

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])
        corners = {
            "nw": (left, top),
            "ne": (right, top),
            "sw": (left, bottom),
            "se": (right, bottom),
        }

        hit_radius = 18
        hit_radius_sq = hit_radius * hit_radius
        nearest: tuple[str, float] | None = None
        for key, (cx, cy) in corners.items():
            dist_sq = ((x - cx) * (x - cx)) + ((y - cy) * (y - cy))
            if dist_sq <= hit_radius_sq and (nearest is None or dist_sq < nearest[1]):
                nearest = (key, dist_sq)

        return nearest[0] if nearest is not None else None

    def _point_in_crop_rect(self, x: int, y: int) -> bool:
        if self.crop_rect_id is None:
            return False
        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])
        return left <= x <= right and top <= y <= bottom

    def _drag_corner_handle(self, corner: str, x: int, y: int, constrain_square: bool = False) -> None:
        if self.crop_rect_id is None:
            return
        if self.display_image is None:
            return

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])

        img_left = self.image_x
        img_top = self.image_y
        img_right = self.image_x + self.display_image.size[0]
        img_bottom = self.image_y + self.display_image.size[1]
        min_size = 12

        if corner == "nw":
            fixed_x, fixed_y = right, bottom
            trial_x, trial_y = x, y
            max_size = min(fixed_x - img_left, fixed_y - img_top)
        elif corner == "ne":
            fixed_x, fixed_y = left, bottom
            trial_x, trial_y = x, y
            max_size = min(img_right - fixed_x, fixed_y - img_top)
        elif corner == "sw":
            fixed_x, fixed_y = right, top
            trial_x, trial_y = x, y
            max_size = min(fixed_x - img_left, img_bottom - fixed_y)
        else:  # "se"
            fixed_x, fixed_y = left, top
            trial_x, trial_y = x, y
            max_size = min(img_right - fixed_x, img_bottom - fixed_y)

        if constrain_square:
            side = max(abs(trial_x - fixed_x), abs(trial_y - fixed_y))
            max_size = max(1, int(max_size))
            side = max(min_size if max_size >= min_size else max_size, min(side, max_size))

            if corner == "nw":
                left = fixed_x - side
                top = fixed_y - side
                right = fixed_x
                bottom = fixed_y
            elif corner == "ne":
                left = fixed_x
                top = fixed_y - side
                right = fixed_x + side
                bottom = fixed_y
            elif corner == "sw":
                left = fixed_x - side
                top = fixed_y
                right = fixed_x
                bottom = fixed_y + side
            else:
                left = fixed_x
                top = fixed_y
                right = fixed_x + side
                bottom = fixed_y + side
        else:
            if corner == "nw":
                left, top = trial_x, trial_y
            elif corner == "ne":
                right, top = trial_x, trial_y
            elif corner == "sw":
                left, bottom = trial_x, trial_y
            else:
                right, bottom = trial_x, trial_y

            if right - left < min_size:
                if corner in ("nw", "sw"):
                    left = right - min_size
                else:
                    right = left + min_size
            if bottom - top < min_size:
                if corner in ("nw", "ne"):
                    top = bottom - min_size
                else:
                    bottom = top + min_size

            left = max(img_left, min(left, img_right - 1))
            right = max(left + 1, min(right, img_right))
            top = max(img_top, min(top, img_bottom - 1))
            bottom = max(top + 1, min(bottom, img_bottom))

        self.canvas.coords(self.crop_rect_id, left, top, right, bottom)

    def _drag_crop_region(self, x: int, y: int) -> None:
        if self.crop_rect_id is None or self.move_anchor is None:
            return
        if self.display_image is None:
            return

        anchor_x, anchor_y = self.move_anchor
        dx = x - anchor_x
        dy = y - anchor_y
        if dx == 0 and dy == 0:
            return

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])
        width = right - left
        height = bottom - top

        new_left = left + dx
        new_right = right + dx
        new_top = top + dy
        new_bottom = bottom + dy

        img_left = self.image_x
        img_top = self.image_y
        img_right = self.image_x + self.display_image.size[0]
        img_bottom = self.image_y + self.display_image.size[1]

        if new_left < img_left:
            new_left = img_left
            new_right = new_left + width
        if new_right > img_right:
            new_right = img_right
            new_left = new_right - width
        if new_top < img_top:
            new_top = img_top
            new_bottom = new_top + height
        if new_bottom > img_bottom:
            new_bottom = img_bottom
            new_top = new_bottom - height

        self.canvas.coords(self.crop_rect_id, new_left, new_top, new_right, new_bottom)
        self.move_anchor = (x, y)

    def _clear_crop_overlay(self) -> None:
        if not self.crop_overlay_ids:
            return
        for overlay_id in self.crop_overlay_ids:
            self.canvas.delete(overlay_id)
        self.crop_overlay_ids = []

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

        if len(self.crop_overlay_ids) != 4:
            self._clear_crop_overlay()
            mask_color = self.canvas.cget("background")
            for _ in range(4):
                self.crop_overlay_ids.append(
                    self.canvas.create_rectangle(
                        0,
                        0,
                        0,
                        0,
                        fill=mask_color,
                        outline="",
                    )
                )

        img_left = self.image_x
        img_top = self.image_y
        img_right = self.image_x + self.display_image.size[0]
        img_bottom = self.image_y + self.display_image.size[1]
        self.canvas.coords(self.crop_overlay_ids[0], img_left, img_top, img_right, top)
        self.canvas.coords(self.crop_overlay_ids[1], img_left, bottom, img_right, img_bottom)
        self.canvas.coords(self.crop_overlay_ids[2], img_left, top, left, bottom)
        self.canvas.coords(self.crop_overlay_ids[3], right, top, img_right, bottom)

        for overlay_id in self.crop_overlay_ids:
            self.canvas.tag_raise(overlay_id)
        self.canvas.tag_raise(self.crop_rect_id)
        for guide_id in self.crop_corner_ids:
            self.canvas.tag_raise(guide_id)

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
        if self.undo_image is not None and not self.crop_mode:
            self.undo_last_crop()
            return
        if not self.crop_mode:
            self._begin_crop_mode()
            return
        self.apply_crop()

    def _begin_crop_mode(self) -> None:
        if self.working_image is None or self.display_image is None:
            return

        self._clear_crop_selection()
        self.crop_mode = True
        self.active_corner = None

        img_left = self.image_x
        img_top = self.image_y
        img_right = self.image_x + self.display_image.size[0]
        img_bottom = self.image_y + self.display_image.size[1]

        left = img_left
        top = img_top
        right = img_right
        bottom = img_bottom

        self.crop_rect_id = self.canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            outline=self.GUIDE_COLOR,
            width=1,
        )
        self._update_crop_overlay()
        self._draw_corner_guides()
        self._update_crop_size_indicator()

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
    parser = argparse.ArgumentParser(description="Quick Crop + Compress")
    parser.add_argument("image_path", nargs="?", help="Image file to open on launch")
    args = parser.parse_args()

    app = PhotoEditorApp(initial_path=args.image_path)
    app.mainloop()


if __name__ == "__main__":
    main()
