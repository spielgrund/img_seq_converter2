#!/usr/bin/env python3
"""
Image Sequence → MP4 / GIF Converter (Tkinter)
----------------------------------------------
- No drag & drop — use Add Files / Add Folder.
- Uses bundled ffmpeg.exe when built with PyInstaller (--add-binary).
- Otherwise, prefers local ffmpeg.exe next to the script, then falls back to system ffmpeg.
- MP4: codec + CRF, GIF: palettegen/paletteuse + optional scale width.

Build Windows onefile EXE (example):
    pip install pyinstaller
    pyinstaller --onefile --noconsole --add-binary "ffmpeg.exe;." img_seq_converter2.py

Put ffmpeg.exe in the same folder as this script if you want to run without installing ffmpeg system-wide.
"""

import os
import sys
import shutil
import tempfile
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp'}


def is_image_file(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def resolve_ffmpeg_executable() -> str:
    """
    Determine which ffmpeg executable to call:
      1) If running from PyInstaller bundle, use ffmpeg.exe from sys._MEIPASS.
      2) Else if ffmpeg.exe exists next to this script, use that.
      3) Else fallback to 'ffmpeg' (system PATH).
    """
    # 1) PyInstaller bundle
    if getattr(sys, "frozen", False):
        # ffmpeg.exe should be added with --add-binary "ffmpeg.exe;."
        bundled = os.path.join(sys._MEIPASS, "ffmpeg.exe")
        if os.path.exists(bundled):
            return bundled
    # 2) local ffmpeg.exe next to script
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()
    local = os.path.join(script_dir, "ffmpeg.exe")
    if os.path.exists(local):
        return local
    # 3) fallback to system ffmpeg (cross-platform)
    return "ffmpeg"


class ImageSeqConverter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Image Sequence → MP4 / GIF")
        self.geometry("780x520")

        self.images = []
        self.ffmpeg_path = resolve_ffmpeg_executable()
        # UI
        self._build_ui()
        self.ffmpeg_proc = None

    def _build_ui(self):
        # File list frame
        frame_files = ttk.LabelFrame(self, text="Image Sequence")
        frame_files.pack(fill="both", expand=True, padx=10, pady=6)

        self.listbox = tk.Listbox(frame_files, selectmode=tk.EXTENDED)
        self.listbox.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)

        sb = ttk.Scrollbar(frame_files, orient="vertical", command=self.listbox.yview)
        self.listbox.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 6), pady=6)

        # List control buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=6)
        ttk.Button(btn_frame, text="Add Files", command=self.add_files).grid(row=0, column=0, padx=4)
        ttk.Button(btn_frame, text="Add Folder", command=self.add_folder).grid(row=0, column=1, padx=4)
        ttk.Button(btn_frame, text="Remove", command=self.remove_selected).grid(row=0, column=2, padx=4)
        ttk.Button(btn_frame, text="Clear", command=self.clear_list).grid(row=0, column=3, padx=4)
        ttk.Button(btn_frame, text="Up", command=lambda: self.move_item(-1)).grid(row=0, column=4, padx=4)
        ttk.Button(btn_frame, text="Down", command=lambda: self.move_item(1)).grid(row=0, column=5, padx=4)

        # Options frame
        frame_opts = ttk.LabelFrame(self, text="Options")
        frame_opts.pack(fill="x", padx=10, pady=6)

        ttk.Label(frame_opts, text="FPS:").grid(row=0, column=0, padx=6, pady=6, sticky="e")
        self.fps_var = tk.IntVar(value=25)
        ttk.Spinbox(frame_opts, from_=1, to=240, textvariable=self.fps_var, width=6).grid(row=0, column=1, pady=6, sticky="w")

        ttk.Label(frame_opts, text="Format:").grid(row=0, column=2, padx=6, pady=6, sticky="e")
        self.format_var = tk.StringVar(value="MP4")
        format_combo = ttk.Combobox(frame_opts, textvariable=self.format_var, values=["MP4", "GIF"], width=8, state="readonly")
        format_combo.grid(row=0, column=3, pady=6, sticky="w")
        format_combo.bind("<<ComboboxSelected>>", self.update_format_options)

        # MP4 options
        self.mp4_opts = ttk.Frame(frame_opts)
        ttk.Label(self.mp4_opts, text="Codec:").grid(row=0, column=0, padx=6, pady=6, sticky="e")
        self.codec_var = tk.StringVar(value="libx264")
        ttk.Combobox(self.mp4_opts, textvariable=self.codec_var, values=["libx264", "libx265", "mpeg4"], width=12).grid(row=0, column=1, pady=6, sticky="w")
        ttk.Label(self.mp4_opts, text="CRF:").grid(row=0, column=2, padx=6, pady=6, sticky="e")
        self.crf_var = tk.IntVar(value=18)
        ttk.Spinbox(self.mp4_opts, from_=0, to=51, textvariable=self.crf_var, width=6).grid(row=0, column=3, pady=6, sticky="w")

        # GIF options
        self.gif_opts = ttk.Frame(frame_opts)
        ttk.Label(self.gif_opts, text="Scale Width (optional px):").grid(row=0, column=0, padx=6, pady=6, sticky="e")
        self.scale_var = tk.StringVar(value="")
        ttk.Entry(self.gif_opts, textvariable=self.scale_var, width=10).grid(row=0, column=1, pady=6, sticky="w")

        # Output file
        ttk.Label(frame_opts, text="Output File:").grid(row=1, column=0, padx=6, pady=6, sticky="e")
        self.output_var = tk.StringVar(value="output.mp4")
        ttk.Entry(frame_opts, textvariable=self.output_var, width=48).grid(row=1, column=1, columnspan=3, pady=6, sticky="w")
        ttk.Button(frame_opts, text="Browse", command=self.choose_output).grid(row=1, column=4, pady=6, padx=6)

        # Initial format options setup
        self.update_format_options()

        # Control + Log
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.pack(fill="x", padx=10, pady=6)
        self.start_btn = ttk.Button(ctrl_frame, text="Start", command=self.start_conversion)
        self.start_btn.pack(side="left", padx=(0, 6))
        self.cancel_btn = ttk.Button(ctrl_frame, text="Cancel", command=self.cancel_conversion, state="disabled")
        self.cancel_btn.pack(side="left")

        # ffmpeg path display (small)
        path_frame = ttk.Frame(ctrl_frame)
        path_frame.pack(side="right")
        ttk.Label(path_frame, text="ffmpeg:").pack(side="left")
        self.ffmpeg_label = ttk.Label(path_frame, text=self.ffmpeg_path)
        self.ffmpeg_label.pack(side="left", padx=(4, 0))

        # Log
        self.log_text = tk.Text(self, height=12, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # UI helpers
    def update_format_options(self, event=None):
        self.mp4_opts.grid_forget()
        self.gif_opts.grid_forget()
        fmt = self.format_var.get()
        if fmt == "MP4":
            self.mp4_opts.grid(row=0, column=5, columnspan=4, sticky="w", padx=(6, 0))
            # update output default extension only if user has not changed from previous default
            if not self.output_var.get() or self.output_var.get().endswith(".gif"):
                self.output_var.set("output.mp4")
        else:
            self.gif_opts.grid(row=0, column=5, columnspan=4, sticky="w", padx=(6, 0))
            if not self.output_var.get() or self.output_var.get().endswith(".mp4"):
                self.output_var.set("output.gif")

    # File list management
    def add_image(self, path):
        if path not in self.images and is_image_file(path):
            self.images.append(path)
            self.listbox.insert("end", path)

    def add_files(self):
        files = filedialog.askopenfilenames(title="Select images", filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp")])
        for f in files:
            self.add_image(f)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select folder containing images")
        if folder:
            for f in sorted(os.listdir(folder)):
                fp = os.path.join(folder, f)
                if is_image_file(fp):
                    self.add_image(fp)

    def remove_selected(self):
        sel = list(self.listbox.curselection())
        sel.reverse()
        for idx in sel:
            try:
                self.images.pop(idx)
            except IndexError:
                pass
            self.listbox.delete(idx)

    def clear_list(self):
        self.images.clear()
        self.listbox.delete(0, "end")

    def move_item(self, delta):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        # operate on first-selected item only for simplicity when reordering multiple selections
        # preserve order by moving each selected item
        new_sel = []
        for idx in sel:
            new_idx = idx + delta
            if 0 <= new_idx < len(self.images):
                self.images[idx], self.images[new_idx] = self.images[new_idx], self.images[idx]
                new_sel.append(new_idx)
            else:
                new_sel.append(idx)
        self.refresh_listbox()
        # select moved items
        self.listbox.selection_clear(0, "end")
        for i in new_sel:
            self.listbox.selection_set(i)

    def refresh_listbox(self):
        self.listbox.delete(0, "end")
        for f in self.images:
            self.listbox.insert("end", f)

    # Output selection
    def choose_output(self):
        ext = ".mp4" if self.format_var.get() == "MP4" else ".gif"
        f = filedialog.asksaveasfilename(defaultextension=ext, filetypes=[(ext.upper(), f"*{ext}")])
        if f:
            self.output_var.set(f)

    # Conversion control
    def start_conversion(self):
        if not self.images:
            messagebox.showwarning("No files", "Please add images before starting.")
            return
        out = self.output_var.get().strip()
        if not out:
            messagebox.showwarning("No output", "Please choose an output filename.")
            return

        # disable start, enable cancel
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.log_text.delete("1.0", "end")
        # run after short delay to allow UI update
        self.after(100, self.run_ffmpeg)

    def run_ffmpeg(self):
        tmpdir = tempfile.mkdtemp(prefix="imgseq_")
        try:
            # copy images into temp dir, renaming sequentially
            ext = Path(self.images[0]).suffix
            for i, src in enumerate(self.images, start=1):
                dst = os.path.join(tmpdir, f"img{i:04d}{ext}")
                shutil.copy2(src, dst)

            pattern = os.path.join(tmpdir, f"img%04d{ext}")
            fmt = self.format_var.get().upper()

            if fmt == "MP4":
                cmd = [
                    self.ffmpeg_path, "-y",
                    "-framerate", str(self.fps_var.get()),
                    "-i", pattern,
                    "-c:v", self.codec_var.get(),
                    "-crf", str(self.crf_var.get()),
                    "-pix_fmt", "yuv420p",
                    self.output_var.get()
                ]
            else:  # GIF
                # build -vf string: optional scale, then palettegen/paletteuse
                vf_parts = []
                scale = self.scale_var.get().strip()
                if scale:
                    # validate numeric width (or expression); we don't enforce too strictly here
                    vf_parts.append(f"scale={scale}:-1:flags=lanczos")
                vf_parts.append("split [a][b]; [a] palettegen=stats_mode=full [p]; [b][p] paletteuse=dither=floyd_steinberg")
                vf_str = ",".join(vf_parts)

                cmd = [
                    self.ffmpeg_path, "-y",
                    "-framerate", str(self.fps_var.get()),
                    "-i", pattern,
                    "-vf", vf_str,
                    self.output_var.get()
                ]

            self.log("Running: " + " ".join(cmd) + "\n")
            # start process
            # Use text mode so we can iterate over stderr lines
            self.ffmpeg_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

            # Read both stdout and stderr asynchronously line-by-line in a simple loop.
            # ffmpeg generally writes progress to stderr.
            # We will read stderr lines as they arrive.
            for line in self.ffmpeg_proc.stderr:
                if line:
                    self.log(line)
                    self.update_idletasks()
                    # allow cancellation check
                    if self.ffmpeg_proc.poll() is not None:
                        break

            rc = self.ffmpeg_proc.wait()
            if rc == 0:
                self.log("\nFinished successfully.\n")
                messagebox.showinfo("Done", f"Exported: {self.output_var.get()}")
            else:
                self.log(f"\nffmpeg exited with code {rc}\n")
                messagebox.showerror("Error", "ffmpeg failed. See log for details.")
        except FileNotFoundError:
            messagebox.showerror("ffmpeg not found", f"ffmpeg executable not found.\nExpected: {self.ffmpeg_path}\nInstall ffmpeg or place ffmpeg.exe next to the script / include it when building the EXE.")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.log(f"\nException: {e}\n")
        finally:
            # cleanup temp dir
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass
            self.start_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")
            self.ffmpeg_proc = None

    def cancel_conversion(self):
        if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            try:
                self.ffmpeg_proc.terminate()
            except Exception:
                pass
            self.log("\nffmpeg terminated by user.\n")
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")

    def log(self, text: str):
        self.log_text.insert("end", text)
        self.log_text.see("end")


if __name__ == "__main__":
    app = ImageSeqConverter()
    app.mainloop()
