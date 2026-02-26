#!/usr/bin/env python3
import argparse
import io
import os
import sys


def _configure_frozen_macos_tk() -> None:
    if sys.platform != "darwin" or not bool(getattr(sys, "frozen", False)):
        return

    resource_path = os.environ.get("RESOURCEPATH")
    if not resource_path:
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        resource_path = os.path.abspath(os.path.join(exe_dir, "..", "Resources"))

    tcl_dir = os.path.join(resource_path, "tcl8.6")
    tk_dir = os.path.join(resource_path, "tk8.6")
    if os.path.isdir(tcl_dir):
        os.environ["TCL_LIBRARY"] = tcl_dir
    if os.path.isdir(tk_dir):
        os.environ["TK_LIBRARY"] = tk_dir


_configure_frozen_macos_tk()

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
    APP_NAME = "ImagePress"
    APP_VERSION = "0.1"
    APP_AUTHOR = "Zhiyuan Yao"
    APP_COPYRIGHT = "Copyright © 2026-2026 Zhiyuan Yao"
    PAD_X_RATIO = 0.06
    PAD_Y_RATIO = 0.06
    GUIDE_COLOR = "#F4F4F4"
    CANVAS_BG = "#9E9E9E"
    MIN_ZOOM = 0.25
    MAX_ZOOM = 8.0
    MAX_RESIZE_DIM = 16384

    def __init__(self, initial_path: str | None = None) -> None:
        super().__init__()
        self.packaged_macos = self._is_packaged_macos()
        if self.packaged_macos:
            self.withdraw()
        self.title(self.APP_NAME)
        self.geometry("1100x760")
        self.minsize(920, 660)

        self.source_path: str | None = None
        self.working_image: Image.Image | None = None
        self.display_image: Image.Image | None = None
        self.tk_image: ImageTk.PhotoImage | None = None

        self.scale = 1.0
        self.zoom_ratio = 1.0
        self.image_x = 0
        self.image_y = 0
        self.image_item_id: int | None = None

        self.zoom_percent_var = tk.StringVar(value="100%")
        self.zoom_entry: ttk.Entry | None = None

        self.crop_rect_id: int | None = None
        self.crop_start: tuple[int, int] | None = None
        self.crop_mode = False
        self.resize_mode = False
        self.active_corner: str | None = None
        self.active_drag_mode: str | None = None
        self.move_anchor: tuple[int, int] | None = None
        self.crop_corner_ids: list[int] = []
        self.crop_size_text_id: int | None = None
        self.crop_size_bg_id: int | None = None
        self.crop_overlay_ids: list[int] = []
        self.icon_image: tk.PhotoImage | None = None
        self.undo_image: Image.Image | None = None
        self.undo_action: str | None = None
        self.crop_info_font = tkfont.Font(family="Helvetica Neue", size=11, weight="bold")

        self.target_kb_var = tk.StringVar(value="300")
        self.max_width_var = tk.StringVar(value="1000")
        self.status_var = tk.StringVar(value="")
        self.bg_gray_var = tk.IntVar(value=158)
        self.bg_gray_value_var = tk.StringVar(value="158")

        self._setup_styles()
        self._build_ui()
        self._build_menu()
        self._set_app_icon()
        if HAS_DND:
            self.after(50, self._enable_drag_and_drop)
        if initial_path:
            self.after(80, lambda: self._open_initial_path(initial_path))
            self.after(130, self._bring_to_front)
        self.after(120, self._render_image)
        if self.packaged_macos:
            self.after(180, self._show_packaged_window_clean)

    @staticmethod
    def _is_packaged_macos() -> bool:
        return sys.platform == "darwin" and bool(getattr(sys, "frozen", False))

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

    def _show_packaged_window_clean(self) -> None:
        if not self.packaged_macos:
            return
        try:
            self.deiconify()
            self.update_idletasks()
            self._simulate_safe_canvas_click()
            self.update_idletasks()
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(200, lambda: self.attributes("-topmost", False))
        except tk.TclError:
            pass

    def _simulate_safe_canvas_click(self) -> None:
        if not hasattr(self, "canvas") or self.canvas is None:
            return
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        x = max(width - 4, 1)
        y = max(height - 4, 1)
        self.canvas.event_generate("<Motion>", x=x, y=y)
        self.canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        self.canvas.event_generate("<ButtonRelease-1>", x=x, y=y)

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
        style.configure("CanvasCard.TFrame", background="#f8fbff")
        style.configure("Field.TLabel", background="#f8fbff", foreground="#5a6b82")
        style.configure("Unit.TLabel", background="#f8fbff", foreground="#97a3b5")
        style.configure("Primary.TButton", foreground="#ffffff", background="#5f8fe8", padding=(4, 1))
        style.map(
            "Primary.TButton",
            background=[("active", "#4f81dd"), ("pressed", "#416fc9"), ("disabled", "#a7c0ef")],
            foreground=[("disabled", "#edf4ff")],
        )
        style.configure(
            "Neutral.TButton",
            padding=(4, 1),
            background="#eaf1fb",
            foreground="#3f5878",
            bordercolor="#d7e2f4",
        )
        style.map(
            "Neutral.TButton",
            background=[("active", "#dfe9f8"), ("pressed", "#d3e0f4")],
        )
        style.configure(
            "TEntry",
            fieldbackground="#ffffff",
            foreground="#111827",
            insertcolor="#111827",
            bordercolor="#5C6474",
            lightcolor="#5C6474",
            darkcolor="#5C6474",
            padding=(5, 2),
        )

    def _build_ui(self) -> None:
        main = ttk.Frame(self, style="App.TFrame", padding=(12, 10, 12, 12))
        main.pack(fill="both", expand=True)

        control_row = ttk.Frame(main, style="Bar.TFrame", padding=(10, 6))
        control_row.pack(fill="x", pady=(0, 8))

        self.open_button = ttk.Button(
            control_row,
            text="Open",
            width=5,
            style="Primary.TButton",
            command=self.open_image,
            takefocus=False,
        )
        self.open_button.pack(side="left", padx=(0, 8))
        self.crop_button = ttk.Button(
            control_row, text="Crop", width=5, style="Neutral.TButton", command=self.on_crop_or_undo, takefocus=False
        )
        self.crop_button.pack(side="left", padx=(0, 8))
        self.resize_button = ttk.Button(
            control_row, text="Resize", width=6, style="Neutral.TButton", command=self.on_resize_or_undo, takefocus=False
        )
        self.resize_button.pack(side="left", padx=(0, 8))
        ttk.Button(
            control_row, text="Save", width=5, style="Neutral.TButton", command=self.save_cropped, takefocus=False
        ).pack(
            side="left", padx=(0, 12)
        )

        ttk.Separator(control_row, orient="vertical").pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(control_row, text="size", style="Field.TLabel").pack(side="left")
        size_input = ttk.Frame(control_row, style="Bar.TFrame")
        size_input.pack(side="left", padx=(6, 12))
        ttk.Entry(size_input, width=5, textvariable=self.target_kb_var, justify="right").pack(side="left")
        ttk.Label(size_input, text="KB", style="Unit.TLabel").pack(side="left", padx=(6, 0))

        ttk.Label(control_row, text="width", style="Field.TLabel").pack(side="left")
        width_input = ttk.Frame(control_row, style="Bar.TFrame")
        width_input.pack(side="left", padx=(6, 10))
        ttk.Entry(width_input, width=5, textvariable=self.max_width_var, justify="right").pack(side="left")
        ttk.Label(width_input, text="px", style="Unit.TLabel").pack(side="left", padx=(6, 0))

        ttk.Button(
            control_row,
            text="Compress",
            width=8,
            style="Neutral.TButton",
            command=self.save_compressed,
            takefocus=False,
        ).pack(side="left", padx=(0, 10))
        ttk.Separator(control_row, orient="vertical").pack(side="left", fill="y", padx=(0, 10))

        bg_input = ttk.Frame(control_row, style="Bar.TFrame")
        bg_input.pack(side="left", padx=(0, 12))
        self.bg_scale = ttk.Scale(
            bg_input,
            from_=0,
            to=255,
            orient="horizontal",
            variable=self.bg_gray_var,
            command=self._on_bg_gray_changed,
            length=86,
        )
        self.bg_scale.pack(side="left")
        ttk.Label(bg_input, textvariable=self.bg_gray_value_var, style="Unit.TLabel", width=3).pack(side="left", padx=(6, 0))

        ttk.Separator(control_row, orient="vertical").pack(side="left", fill="y", padx=(0, 10))

        ttk.Button(
            control_row,
            text="−",
            width=2,
            style="Neutral.TButton",
            command=self.zoom_out,
            takefocus=False,
        ).pack(side="left", padx=(0, 6))

        self.zoom_entry = ttk.Entry(control_row, width=5, textvariable=self.zoom_percent_var, justify="center")
        self.zoom_entry.pack(side="left", padx=(0, 6))
        self.zoom_entry.bind("<Return>", self._apply_zoom_from_entry)
        self.zoom_entry.bind("<KP_Enter>", self._apply_zoom_from_entry)
        self.zoom_entry.bind("<FocusOut>", self._apply_zoom_from_entry)

        ttk.Button(
            control_row,
            text="+",
            width=2,
            style="Neutral.TButton",
            command=self.zoom_in,
            takefocus=False,
        ).pack(side="left")

        canvas_card = ttk.Frame(main, style="CanvasCard.TFrame", padding=(0, 0, 0, 0))
        canvas_card.pack(fill="both", expand=True)
        canvas_card.grid_rowconfigure(0, weight=1)
        canvas_card.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(canvas_card, background=self.CANVAS_BG, highlightthickness=0, borderwidth=0)
        self._apply_bg_gray(self.bg_gray_var.get())
        self.h_scroll = ttk.Scrollbar(canvas_card, orient="horizontal", command=self.canvas.xview)
        self.v_scroll = ttk.Scrollbar(canvas_card, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")

        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        self.bind("<Configure>", self._on_window_resize)
        self.bind("<Escape>", self._on_escape_key)

        self.bind_all("<KeyPress-o>", self._on_shortcut_open, add="+")
        self.bind_all("<KeyPress-O>", self._on_shortcut_open, add="+")
        self.bind_all("<KeyPress-c>", self._on_shortcut_crop, add="+")
        self.bind_all("<KeyPress-C>", self._on_shortcut_crop, add="+")
        self.bind_all("<KeyPress-r>", self._on_shortcut_resize, add="+")
        self.bind_all("<KeyPress-R>", self._on_shortcut_resize, add="+")
        self.bind_all("<KeyPress-s>", self._on_shortcut_save, add="+")
        self.bind_all("<KeyPress-S>", self._on_shortcut_save, add="+")
        self.bind_all("<KeyPress-u>", self._on_shortcut_undo, add="+")
        self.bind_all("<KeyPress-U>", self._on_shortcut_undo, add="+")
        self.bind_all("<KeyPress-k>", self._on_shortcut_compress, add="+")
        self.bind_all("<KeyPress-K>", self._on_shortcut_compress, add="+")
        self.bind_all("<Return>", self._on_shortcut_enter_save, add="+")
        self.bind_all("<KP_Enter>", self._on_shortcut_enter_save, add="+")

        self.bind_all("<KeyPress-equal>", self._on_shortcut_zoom_in, add="+")
        self.bind_all("<KeyPress-plus>", self._on_shortcut_zoom_in, add="+")
        self.bind_all("<KeyPress-minus>", self._on_shortcut_zoom_out, add="+")
        self.bind_all("<KeyPress-underscore>", self._on_shortcut_zoom_out, add="+")

        for seq in (
            "<Control-plus>",
            "<Control-equal>",
            "<Control-KP_Add>",
            "<Command-plus>",
            "<Command-equal>",
            "<Command-KP_Add>",
        ):
            self.bind_all(seq, self._on_shortcut_zoom_in, add="+")
        for seq in ("<Control-minus>", "<Control-KP_Subtract>", "<Command-minus>", "<Command-KP_Subtract>"):
            self.bind_all(seq, self._on_shortcut_zoom_out, add="+")

        self._set_action_highlight("open")

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        help_menu = tk.Menu(menu_bar, tearoff=0)
        help_menu.add_command(label="Basic Usage", command=self.show_basic_usage)
        help_menu.add_separator()
        help_menu.add_command(label=f"About {self.APP_NAME}", command=self.show_about)
        menu_bar.add_cascade(label="Help", menu=help_menu)
        self.configure(menu=menu_bar)

    def show_basic_usage(self) -> None:
        messagebox.showinfo(
            f"{self.APP_NAME} - Basic Usage",
            "3C Functions:\n"
            "Convert: Use Save (or Compress) and pick output format (JPG/PNG/etc.).\n"
            "Crop: Click Crop to enter crop mode, adjust selection, and apply or export.\n"
            "Resize: Click Resize to enter size mode, drag the bottom-right guide, then apply.\n"
            "Compress: Use Compress for max width resize and optional JPEG target size.\n\n"
            "Basic Flow:\n"
            "1. Open an image (or drag and drop).\n"
            "2. Click Crop and adjust the selection box.\n"
            "3. Press Enter in crop/resize mode to Save quickly.\n"
            "4. Use Save for direct format conversion/export.\n"
            "5. Use Compress for resize/compression export.\n\n"
            "Shortcuts:\n"
            "O: Open\n"
            "C: Crop/Undo\n"
            "R: Resize/Undo\n"
            "U: Undo\n"
            "S: Save\n"
            "K: Compress\n"
            "Enter: Save (crop/resize mode)\n"
            "+ / -: Zoom in/out",
        )

    def show_about(self) -> None:
        messagebox.showinfo(
            f"About {self.APP_NAME}",
            f"{self.APP_NAME} {self.APP_VERSION}\n\n"
            f"Author: {self.APP_AUTHOR}\n"
            f"{self.APP_COPYRIGHT}",
        )

    @staticmethod
    def _gray_to_hex(value: int) -> str:
        gray = max(0, min(255, int(value)))
        return f"#{gray:02x}{gray:02x}{gray:02x}"

    def _apply_bg_gray(self, value: int | str) -> None:
        try:
            gray = int(float(value))
        except (TypeError, ValueError):
            gray = int(self.bg_gray_var.get() or 158)
        gray = max(0, min(255, gray))

        if int(self.bg_gray_var.get()) != gray:
            self.bg_gray_var.set(gray)
        self.bg_gray_value_var.set(str(gray))

        color = self._gray_to_hex(gray)
        if hasattr(self, "canvas") and self.canvas is not None:
            self.canvas.configure(background=color)
            if (self.crop_mode or self.resize_mode) and self.crop_rect_id is not None:
                self._update_crop_overlay()

    def _on_bg_gray_changed(self, value: str) -> None:
        self._apply_bg_gray(value)

    def _set_action_highlight(self, target: str | None) -> None:
        if hasattr(self, "open_button"):
            self.open_button.configure(style="Primary.TButton" if target == "open" else "Neutral.TButton")
        if hasattr(self, "crop_button"):
            self.crop_button.configure(style="Primary.TButton" if target == "crop" else "Neutral.TButton")
        if hasattr(self, "resize_button"):
            self.resize_button.configure(style="Primary.TButton" if target == "resize" else "Neutral.TButton")

    def _has_loaded_image(self) -> bool:
        return self.working_image is not None

    def _on_window_resize(self, event: tk.Event) -> None:
        if event.widget == self:
            self.after(20, lambda: self._render_image(preserve_view=True))

    def _get_view_center(self) -> tuple[float, float]:
        view_w = max(self.canvas.winfo_width(), 1)
        view_h = max(self.canvas.winfo_height(), 1)
        return (self.canvas.canvasx(view_w / 2), self.canvas.canvasy(view_h / 2))

    def _restore_view_center(self, center_x: float, center_y: float) -> None:
        region = self.canvas.cget("scrollregion")
        if not region:
            return

        try:
            x1, y1, x2, y2 = [float(v) for v in str(region).split()]
        except Exception:
            return

        total_w = max(x2 - x1, 1.0)
        total_h = max(y2 - y1, 1.0)
        view_w = max(self.canvas.winfo_width(), 1)
        view_h = max(self.canvas.winfo_height(), 1)

        if total_w <= view_w:
            self.canvas.xview_moveto(0.0)
        else:
            target_left = max(x1, min(center_x - (view_w / 2), x2 - view_w))
            self.canvas.xview_moveto((target_left - x1) / total_w)

        if total_h <= view_h:
            self.canvas.yview_moveto(0.0)
        else:
            target_top = max(y1, min(center_y - (view_h / 2), y2 - view_h))
            self.canvas.yview_moveto((target_top - y1) / total_h)

    def _set_zoom_text(self) -> None:
        pct = int(round(self.zoom_ratio * 100))
        pct = max(int(self.MIN_ZOOM * 100), min(int(self.MAX_ZOOM * 100), pct))
        self.zoom_percent_var.set(f"{pct}%")

    def _fit_scale_for_dimensions(self, src_w: int, src_h: int) -> float:
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)
        pad_x = int(canvas_w * self.PAD_X_RATIO)
        pad_y = int(canvas_h * self.PAD_Y_RATIO)
        usable_w = max(canvas_w - (2 * pad_x), 1)
        usable_h = max(canvas_h - (2 * pad_y), 1)
        return min(usable_w / max(src_w, 1), usable_h / max(src_h, 1), 1.0)

    def _set_zoom_ratio(self, ratio: float, preserve_view: bool = True) -> None:
        clamped = max(self.MIN_ZOOM, min(self.MAX_ZOOM, ratio))
        if abs(clamped - self.zoom_ratio) < 0.0001:
            self._set_zoom_text()
            return

        center = self._get_view_center() if preserve_view else None
        self.zoom_ratio = clamped
        self._set_zoom_text()
        self._render_image(preserve_view=preserve_view, view_center=center)

    def zoom_in(self) -> None:
        self._set_zoom_ratio(self.zoom_ratio * 1.25)

    def zoom_out(self) -> None:
        self._set_zoom_ratio(self.zoom_ratio / 1.25)

    def _apply_zoom_from_entry(self, _event: tk.Event | None = None) -> str | None:
        raw = self.zoom_percent_var.get().strip().replace("%", "")
        try:
            pct = float(raw)
        except ValueError:
            self._set_zoom_text()
            return "break"

        self._set_zoom_ratio(pct / 100.0)
        return "break"

    def _entry_has_focus(self, allow_zoom_entry: bool = False) -> bool:
        widget = self.focus_get()
        if widget is None:
            return False

        if isinstance(widget, (tk.Entry, ttk.Entry, tk.Text)):
            if allow_zoom_entry and widget == self.zoom_entry:
                return False
            return True
        return False

    def _on_shortcut_open(self, _event: tk.Event) -> str | None:
        if self._entry_has_focus():
            return None
        self.open_image()
        return "break"

    def _on_shortcut_crop(self, _event: tk.Event) -> str | None:
        if self._entry_has_focus():
            return None
        self.on_crop_or_undo()
        return "break"

    def _on_shortcut_resize(self, _event: tk.Event) -> str | None:
        if self._entry_has_focus():
            return None
        self.on_resize_or_undo()
        return "break"

    def _on_shortcut_save(self, _event: tk.Event) -> str | None:
        if self._entry_has_focus():
            return None
        self.save_cropped()
        return "break"

    def _on_shortcut_undo(self, _event: tk.Event) -> str | None:
        if self._entry_has_focus():
            return None
        self.undo_last_edit()
        return "break"

    def _on_shortcut_compress(self, _event: tk.Event) -> str | None:
        if self._entry_has_focus():
            return None
        self.save_compressed()
        return "break"

    def _on_shortcut_enter_save(self, _event: tk.Event) -> str | None:
        if self._entry_has_focus():
            return None
        if not self.crop_mode and not self.resize_mode:
            return None
        self.save_cropped()
        return "break"

    def _on_shortcut_zoom_in(self, _event: tk.Event) -> str | None:
        if self._entry_has_focus(allow_zoom_entry=True):
            return None
        self.zoom_in()
        return "break"

    def _on_shortcut_zoom_out(self, _event: tk.Event) -> str | None:
        if self._entry_has_focus(allow_zoom_entry=True):
            return None
        self.zoom_out()
        return "break"

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
        self.undo_action = None
        self.zoom_ratio = 1.0
        self._set_zoom_text()
        self._update_mode_buttons()
        self._set_action_highlight(None)
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

    def _render_image(self, preserve_view: bool = False, view_center: tuple[float, float] | None = None) -> None:
        center = view_center
        if preserve_view and center is None:
            center = self._get_view_center()

        self.canvas.delete("all")
        self.image_item_id = None
        self.crop_rect_id = None
        self.crop_start = None
        self.crop_mode = False
        self.resize_mode = False
        self.active_corner = None
        self.active_drag_mode = None
        self.move_anchor = None
        self._clear_corner_guides()
        self.crop_size_text_id = None
        self.crop_size_bg_id = None
        self.crop_overlay_ids = []
        self._update_mode_buttons()
        self._set_action_highlight(None if self._has_loaded_image() else "open")

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
        draw_scale = max(fit_scale * self.zoom_ratio, 0.01)
        disp_w = max(int(src_w * draw_scale), 1)
        disp_h = max(int(src_h * draw_scale), 1)

        self.scale = draw_scale

        content_w = max(canvas_w, disp_w)
        content_h = max(canvas_h, disp_h)
        self.image_x = (content_w - disp_w) // 2
        self.image_y = (content_h - disp_h) // 2

        if (disp_w, disp_h) != self.working_image.size:
            self.display_image = self.working_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        else:
            self.display_image = self.working_image

        self.tk_image = ImageTk.PhotoImage(self.display_image)
        self.image_item_id = self.canvas.create_image(self.image_x, self.image_y, anchor="nw", image=self.tk_image)
        self.canvas.configure(scrollregion=(0, 0, content_w, content_h))

        if center is not None:
            self._restore_view_center(center[0], center[1])
        else:
            self._restore_view_center(content_w / 2, content_h / 2)

    def _on_mouse_down(self, event: tk.Event) -> None:
        if self.display_image is None:
            return

        if not self.crop_mode and not self.resize_mode:
            return

        cx = int(self.canvas.canvasx(event.x))
        cy = int(self.canvas.canvasy(event.y))

        if self.resize_mode:
            self.active_corner = self._hit_resize_handle(cx, cy)
            if self.active_corner is not None:
                self.active_drag_mode = "resize_corner"
                self.move_anchor = None
                return
            self.active_corner = None
            self.active_drag_mode = None
            self.move_anchor = None
            return

        x, y = self._clamp_to_image(cx, cy, require_inside=False)
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

        self.active_corner = None
        self.active_drag_mode = None
        self.move_anchor = None

    def _on_mouse_drag(self, event: tk.Event) -> None:
        if (not self.crop_mode and not self.resize_mode) or self.crop_rect_id is None or self.active_drag_mode is None:
            return

        cx = int(self.canvas.canvasx(event.x))
        cy = int(self.canvas.canvasy(event.y))

        if self.active_drag_mode == "corner" and self.active_corner is not None:
            x, y = self._clamp_to_image(cx, cy)
            if x is None or y is None:
                return
            constrain_square = bool(getattr(event, "state", 0) & 0x0001)
            self._drag_corner_handle(self.active_corner, x, y, constrain_square=constrain_square)
        elif self.active_drag_mode == "resize_corner":
            self._drag_resize_handle(cx, cy)
            self._update_resize_preview()
        elif self.active_drag_mode == "move":
            x, y = self._clamp_to_image(cx, cy)
            if x is None or y is None:
                return
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
        had_resize_preview = self.resize_mode
        self._clear_crop_selection()
        self.crop_mode = False
        self.resize_mode = False
        self.active_drag_mode = None
        self.move_anchor = None
        if had_resize_preview:
            self._render_image(preserve_view=True)
            return
        self._update_mode_buttons()
        self._set_action_highlight(None if self._has_loaded_image() else "open")

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

        arm = max(10, min(22, int(min(width, height) * 0.14)))
        fill_color = self.GUIDE_COLOR
        border_color = "#000000"
        stroke = 3

        def draw_corner_polygon(points: list[tuple[float, float]]) -> None:
            flattened: list[float] = []
            for px, py in points:
                flattened.extend([px, py])
            self.crop_corner_ids.append(
                self.canvas.create_polygon(
                    *flattened,
                    fill=fill_color,
                    outline=border_color,
                    width=1,
                )
            )

        if self.resize_mode:
            # Resize mode: only bottom-right guide.
            draw_corner_polygon(
                [
                    (right, bottom),
                    (right - arm, bottom),
                    (right - arm, bottom - stroke),
                    (right - stroke, bottom - stroke),
                    (right - stroke, bottom - arm),
                    (right, bottom - arm),
                ]
            )
        else:
            # Crop mode: all four guides.
            draw_corner_polygon(
                [
                    (left, top),
                    (left + arm, top),
                    (left + arm, top + stroke),
                    (left + stroke, top + stroke),
                    (left + stroke, top + arm),
                    (left, top + arm),
                ]
            )
            draw_corner_polygon(
                [
                    (right, top),
                    (right - arm, top),
                    (right - arm, top + stroke),
                    (right - stroke, top + stroke),
                    (right - stroke, top + arm),
                    (right, top + arm),
                ]
            )
            draw_corner_polygon(
                [
                    (left, bottom),
                    (left + arm, bottom),
                    (left + arm, bottom - stroke),
                    (left + stroke, bottom - stroke),
                    (left + stroke, bottom - arm),
                    (left, bottom - arm),
                ]
            )
            draw_corner_polygon(
                [
                    (right, bottom),
                    (right - arm, bottom),
                    (right - arm, bottom - stroke),
                    (right - stroke, bottom - stroke),
                    (right - stroke, bottom - arm),
                    (right, bottom - arm),
                ]
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

    def _hit_resize_handle(self, x: int, y: int) -> str | None:
        if self.crop_rect_id is None:
            return None

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        right = max(x1, x2)
        bottom = max(y1, y2)
        hit_radius = 20
        if ((x - right) * (x - right)) + ((y - bottom) * (y - bottom)) <= (hit_radius * hit_radius):
            return "se"
        return None

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

    def _drag_resize_handle(self, x: int, y: int) -> None:
        if self.crop_rect_id is None:
            return
        if self.display_image is None:
            return

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])

        img_left = self.image_x
        img_top = self.image_y
        min_size = 12
        max_display_w = max(int(self.MAX_RESIZE_DIM * self.scale), min_size)
        max_display_h = max(int(self.MAX_RESIZE_DIM * self.scale), min_size)

        left = img_left
        top = img_top
        right = max(left + min_size, min(x, left + max_display_w))
        bottom = max(top + min_size, min(y, top + max_display_h))

        self.canvas.coords(self.crop_rect_id, left, top, right, bottom)
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)
        content_w = max(canvas_w, int(right) + 20)
        content_h = max(canvas_h, int(bottom) + 20)
        self.canvas.configure(scrollregion=(0, 0, content_w, content_h))

    def _update_resize_preview(self) -> None:
        if not self.resize_mode or self.crop_rect_id is None:
            return
        if self.working_image is None or self.image_item_id is None:
            return

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])
        preview_w = max(int(round(right - left)), 1)
        preview_h = max(int(round(bottom - top)), 1)

        if self.display_image is None or self.display_image.size != (preview_w, preview_h):
            self.display_image = self.working_image.resize((preview_w, preview_h), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(self.display_image)
        self.canvas.itemconfigure(self.image_item_id, image=self.tk_image)
        self.canvas.coords(self.image_item_id, self.image_x, self.image_y)
        self.canvas.tag_lower(self.image_item_id)

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
        if self.resize_mode:
            # Resize mode scales the full image; avoid crop-like masking.
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

        if self.resize_mode:
            width_px = max(1, int(round((right - left) / self.scale)))
            height_px = max(1, int(round((bottom - top) / self.scale)))
        else:
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
            fill="#f8fafc",
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
            fill="#0f172a",
            outline="#0f172a",
            width=0,
        )
        self.canvas.tag_raise(self.crop_size_text_id, self.crop_size_bg_id)

    def _update_mode_buttons(self) -> None:
        crop_undo = self.undo_image is not None and self.undo_action == "crop" and not self.crop_mode and not self.resize_mode
        resize_undo = (
            self.undo_image is not None and self.undo_action == "resize" and not self.crop_mode and not self.resize_mode
        )
        self.crop_button.configure(text="Undo" if crop_undo else "Crop")
        self.resize_button.configure(text="Undo" if resize_undo else "Resize")

    def on_crop_or_undo(self) -> None:
        if self.undo_image is not None and self.undo_action == "crop" and not self.crop_mode and not self.resize_mode:
            self.undo_last_edit()
            return
        if not self.crop_mode:
            self._begin_crop_mode()
            return
        self.apply_crop()

    def on_resize_or_undo(self) -> None:
        if self.undo_image is not None and self.undo_action == "resize" and not self.crop_mode and not self.resize_mode:
            self.undo_last_edit()
            return
        if not self.resize_mode:
            self._begin_resize_mode()
            return
        self.apply_resize()

    def _begin_crop_mode(self) -> None:
        if self.working_image is None or self.display_image is None:
            return
        if self.resize_mode:
            self._render_image(preserve_view=True)
            if self.display_image is None:
                return

        self._clear_crop_selection()
        self.crop_mode = True
        self.resize_mode = False
        self.active_corner = None
        self.active_drag_mode = None
        self.move_anchor = None

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
        self._update_mode_buttons()
        self._set_action_highlight("crop")
        self._update_crop_overlay()
        self._draw_corner_guides()
        self._update_crop_size_indicator()

    def _begin_resize_mode(self) -> None:
        if self.working_image is None or self.display_image is None:
            return

        self._clear_crop_selection()
        self.crop_mode = False
        self.resize_mode = True
        self.active_corner = None
        self.active_drag_mode = None
        self.move_anchor = None

        img_left = self.image_x
        img_top = self.image_y
        img_right = self.image_x + self.display_image.size[0]
        img_bottom = self.image_y + self.display_image.size[1]

        self.crop_rect_id = self.canvas.create_rectangle(
            img_left,
            img_top,
            img_right,
            img_bottom,
            outline=self.GUIDE_COLOR,
            width=1,
        )
        self._update_mode_buttons()
        self._set_action_highlight("resize")
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
        crop_box = self._get_selected_crop_box()
        if crop_box is None:
            self.status_var.set("")
            return

        self.undo_image = self.working_image.copy()
        self.undo_action = "crop"
        self.working_image = self.working_image.crop(crop_box)
        self._update_mode_buttons()
        self._set_action_highlight("crop")
        self.status_var.set("")
        self._render_image()

    def apply_resize(self) -> None:
        if self.working_image is None:
            self.status_var.set("")
            return
        if self.crop_rect_id is None:
            self.status_var.set("")
            return

        resize_dims = self._get_selected_resize_dimensions()
        if resize_dims is None:
            self.status_var.set("")
            return

        new_width, new_height = resize_dims
        if new_width < 1 or new_height < 1:
            return

        old_draw_scale = max(self.scale, 0.01)
        self.undo_image = self.working_image.copy()
        self.undo_action = "resize"
        self.working_image = self.working_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        new_fit_scale = self._fit_scale_for_dimensions(new_width, new_height)
        if new_fit_scale > 0:
            self.zoom_ratio = max(self.MIN_ZOOM, min(self.MAX_ZOOM, old_draw_scale / new_fit_scale))
            self._set_zoom_text()
        self._update_mode_buttons()
        self._set_action_highlight("resize")
        self.status_var.set("")
        self._render_image()

    def undo_last_edit(self) -> None:
        if self.undo_image is None:
            return
        self.working_image = self.undo_image
        self.undo_image = None
        self.undo_action = None
        self.crop_mode = False
        self.resize_mode = False
        self._update_mode_buttons()
        self._set_action_highlight(None if self._has_loaded_image() else "open")
        self.status_var.set("")
        self._render_image()

    def save_cropped(self) -> None:
        if self.working_image is None:
            messagebox.showinfo("No image", "Open an image first.")
            return

        if self.crop_mode and self.crop_rect_id is not None:
            self.apply_crop()
            if self.working_image is None:
                return

        if self.resize_mode and self.crop_rect_id is not None:
            self.apply_resize()
            if self.working_image is None:
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

        if self.resize_mode and self.crop_rect_id is not None:
            self.apply_resize()
            if self.working_image is None:
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
            filetypes=[
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
            ],
        )
        if not output:
            return

        to_save = self.working_image.copy()
        if self.crop_mode and self.crop_rect_id is not None:
            draft_crop_box = self._get_selected_crop_box()
            if draft_crop_box is None:
                messagebox.showerror("Invalid selection", "Crop selection is too small.")
                return
            to_save = to_save.crop(draft_crop_box)

        if max_width is not None and to_save.width > max_width:
            ratio = max_width / to_save.width
            resized_h = max(int(to_save.height * ratio), 1)
            to_save = to_save.resize((max_width, resized_h), Image.Resampling.LANCZOS)

        ext = os.path.splitext(output)[1].lower()
        try:
            if ext in (".jpg", ".jpeg"):
                if to_save.mode != "RGB":
                    to_save = to_save.convert("RGB")
                self._write_jpeg(to_save, output, target_kb=target_kb)
            elif ext == ".png":
                if target_kb is not None:
                    messagebox.showinfo(
                        "PNG note",
                        "Target size (KB) is applied to JPEG only. PNG will be saved with optimize compression.",
                    )
                self._write_png(to_save, output)
            else:
                messagebox.showerror("Invalid format", "Choose either JPEG (.jpg/.jpeg) or PNG (.png).")
                return
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save image:\n{exc}")
            return

        self.status_var.set("")

    def _default_cropped_output_path(self) -> str:
        suffix = "_resized" if (self.resize_mode or self.undo_action == "resize") else "_cropped"
        if self.source_path is None:
            return f"output{suffix}.png"
        root, _ext = os.path.splitext(self.source_path)
        return f"{root}{suffix}.png"

    def _get_selected_crop_box(self) -> tuple[int, int, int, int] | None:
        if self.working_image is None or self.crop_rect_id is None:
            return None

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])

        if (right - left) < 5 or (bottom - top) < 5:
            return None

        src_x1 = int((left - self.image_x) / self.scale)
        src_y1 = int((top - self.image_y) / self.scale)
        src_x2 = int((right - self.image_x) / self.scale)
        src_y2 = int((bottom - self.image_y) / self.scale)

        src_w, src_h = self.working_image.size
        src_x1 = max(0, min(src_x1, src_w - 1))
        src_y1 = max(0, min(src_y1, src_h - 1))
        src_x2 = max(src_x1 + 1, min(src_x2, src_w))
        src_y2 = max(src_y1 + 1, min(src_y2, src_h))
        return (src_x1, src_y1, src_x2, src_y2)

    def _get_selected_resize_dimensions(self) -> tuple[int, int] | None:
        if self.crop_rect_id is None:
            return None

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])

        if (right - left) < 2 or (bottom - top) < 2:
            return None

        width_px = max(1, int(round((right - left) / self.scale)))
        height_px = max(1, int(round((bottom - top) / self.scale)))
        width_px = min(width_px, self.MAX_RESIZE_DIM)
        height_px = min(height_px, self.MAX_RESIZE_DIM)
        return (width_px, height_px)

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

    def _write_png(self, image: Image.Image, output_path: str) -> None:
        image.save(output_path, format="PNG", optimize=True, compress_level=9)

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
    parser = argparse.ArgumentParser(description=PhotoEditorApp.APP_NAME)
    parser.add_argument("image_path", nargs="?", help="Image file to open on launch")
    args = parser.parse_args()

    app = PhotoEditorApp(initial_path=args.image_path)
    app.mainloop()


if __name__ == "__main__":
    main()
