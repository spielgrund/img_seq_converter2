#!/usr/bin/env python3
"""
Image Sequence → MP4 / GIF Converter (Tkinter, no drag-and-drop)
---------------------------------------------------------------
- Add images/folders via buttons.
- Choose output format (MP4 or GIF) and format-specific options.
- MP4: codec + CRF.
- GIF: optional scale width (palettegen for quality).

Requirements:
    Install ffmpeg and ensure it's in PATH.

Windows executable:
    pip install pyinstaller
    pyinstaller --onefile --noconsole image_seq_converter.py
"""

import os
import shutil
import tempfile
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp'}

def is_image_file(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS

class ImageSeqConverter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Image Sequence → MP4 / GIF")
        self.geometry("750x500")

        self.images = []

        # File list frame
        frame_files = ttk.LabelFrame(self, text="Image Sequence")
        frame_files.pack(fill="both", expand=True, padx=10, pady=5)

        self.listbox = tk.Listbox(frame_files, selectmode=tk.EXTENDED)
        self.listbox.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(frame_files, orient="vertical", command=self.listbox.yview)
        self.listbox.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        # List control buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=2)
        ttk.Button(btn_frame, text="Add Files", command=self.add_files).grid(row=0, column=0, padx=2)
        ttk.Button(btn_frame, text="Add Folder", command=self.add_folder).grid(row=0, column=1, padx=2)
        ttk.Button(btn_frame, text="Remove", command=self.remove_selected).grid(row=0, column=2, padx=2)
        ttk.Button(btn_frame, text="Clear", command=self.clear_list).grid(row=0, column=3, padx=2)
        ttk.Button(btn_frame, text="Up", command=lambda: self.move_item(-1)).grid(row=0, column=4, padx=2)
        ttk.Button(btn_frame, text="Down", command=lambda: self.move_item(1)).grid(row=0, column=5, padx=2)

        # Options frame
        frame_opts = ttk.LabelFrame(self, text="Options")
        frame_opts.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_opts, text="FPS:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.fps_var = tk.IntVar(value=25)
        ttk.Spinbox(frame_opts, from_=1, to=240, textvariable=self.fps_var, width=5).grid(row=0, column=1, pady=5, sticky="w")

        ttk.Label(frame_opts, text="Format:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        self.format_var = tk.StringVar(value="MP4")
        format_combo = ttk.Combobox(frame_opts, textvariable=self.format_var, values=["MP4", "GIF"], width=6, state="readonly")
        format_combo.grid(row=0, column=3, pady=5, sticky="w")
        format_combo.bind("<<ComboboxSelected>>", self.update_format_options)

        # MP4 options
        self.mp4_opts = ttk.Frame(frame_opts)
        ttk.Label(self.mp4_opts, text="Codec:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.codec_var = tk.StringVar(value="libx264")
        ttk.Combobox(self.mp4_opts, textvariable=self.codec_var, values=["libx264", "libx265", "mpeg4"], width=10).grid(row=0, column=1, pady=5, sticky="w")
        ttk.Label(self.mp4_opts, text="CRF:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        self.crf_var = tk.IntVar(value=18)
        ttk.Spinbox(self.mp4_opts, from_=0, to=51, textvariable=self.crf_var, width=5).grid(row=0, column=3, pady=5, sticky="w")

        # GIF options
        self.gif_opts = ttk.Frame(frame_opts)
        ttk.Label(self.gif_opts, text="Scale Width (optional):").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.scale_var = tk.StringVar(value="")
        ttk.Entry(self.gif_opts, textvariable=self.scale_var, width=8).grid(row=0, column=1, pady=5, sticky="w")

        # Output file
        ttk.Label(frame_opts, text="Output File:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.output_var = tk.StringVar(value="output.mp4")
        ttk.Entry(frame_opts, textvariable=self.output_var, width=40).grid(row=2, column=1, columnspan=3, pady=5, sticky="w")
        ttk.Button(frame_opts, text="Browse", command=self.choose_output).grid(row=2, column=4, pady=5)

        self.update_format_options()

        # Control + Log
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.pack(fill="x", padx=10, pady=5)
        self.start_btn = ttk.Button(ctrl_frame, text="Start", command=self.start_conversion)
        self.start_btn.pack(side="left", padx=5)
        self.cancel_btn = ttk.Button(ctrl_frame, text="Cancel", command=self.cancel_conversion, state="disabled")
        self.cancel_btn.pack(side="left")

        self.log_text = tk.Text(self, height=10, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)

        self.ffmpeg_proc = None

    # --- UI logic ---
    def update_format_options(self, event=None):
        self.mp4_opts.grid_forget()
        self.gif_opts.grid_forget()
        fmt = self.format_var.get()
        if fmt == "MP4":
            self.mp4_opts.grid(row=1, column=0, columnspan=5, sticky="w")
            self.output_var.set("output.mp4")
        else:
            self.gif_opts.grid(row=1, column=0, columnspan=5, sticky="w")
            self.output_var.set("output.gif")

    # --- File list ---
    def add_image(self, path):
        if path not in self.images:
            self.images.append(path)
            self.listbox.insert("end", path)

    def add_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp")])
        for f in files:
            if is_image_file(f):
                self.add_image(f)

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            for f in sorted(os.listdir(folder)):
                fp = os.path.join(folder, f)
                if is_image_file(fp):
                    self.add_image(fp)

    def remove_selected(self):
        sel = list(self.listbox.curselection())
        sel.reverse()
        for idx in sel:
            self.images.pop(idx)
            self.listbox.delete(idx)

    def clear_list(self):
        self.images.clear()
        self.listbox.delete(0, "end")

    def move_item(self, delta):
        sel = self.listbox.curselection()
        if not sel:
            return
        for idx in sel:
            new_idx = idx + delta
            if 0 <= new_idx < len(self.images):
                self.images[idx], self.images[new_idx] = self.images[new_idx], self.images[idx]
        self.refresh_listbox()
        self.listbox.select_set(*(i + delta for i in sel))

    def refresh_listbox(self):
        self.listbox.delete(0, "end")
        for f in self.images:
            self.listbox.insert("end", f)

    # --- Output + ffmpeg ---
    def choose_output(self):
        ext = ".mp4" if self.format_var.get() == "MP4" else ".gif"
        f = filedialog.asksaveasfilename(defaultextension=ext, filetypes=[(ext.upper(), f"*{ext}")])
        if f:
            self.output_var.set(f)

    def start_conversion(self):
        if not self.images:
            messagebox.showwarning("No files", "Please add images first.")
            return
        out = self.output_var.get().strip()
        if not out:
            messagebox.showwarning("No output", "Please choose an output file.")
            return

        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.log_text.delete("1.0", "end")

        self.after(100, self.run_ffmpeg)

    def run_ffmpeg(self):
        tmpdir = tempfile.mkdtemp(prefix="imgseq_")
        try:
            ext = Path(self.images[0]).suffix
            for i, src in enumerate(self.images, start=1):
                dst = os.path.join(tmpdir, f"img{i:04d}{ext}")
                shutil.copy2(src, dst)

            pattern = os.path.join(tmpdir, f"img%04d{ext}")
            fmt = self.format_var.get()

            if fmt == "MP4":
                cmd = [
                    "ffmpeg", "-y",
                    "-framerate", str(self.fps_var.get()),
                    "-i", pattern,
                    "-c:v", self.codec_var.get(),
                    "-crf", str(self.crf_var.get()),
                    "-pix_fmt", "yuv420p",
                    self.output_var.get()
                ]
            else:  # GIF
                vf = []
                if self.scale_var.get().strip():
                    vf.append(f"scale={self.scale_var.get().strip()}:-1:flags=lanczos")
                vf.append("split [a][b]; [a] palettegen=stats_mode=full [p]; [b][p] paletteuse=dither=floyd_steinberg")
                vf_str = ",".join(vf)
                cmd = [
                    "ffmpeg", "-y",
                    "-framerate", str(self.fps_var.get()),
                    "-i", pattern,
                    "-vf", vf_str,
                    self.output_var.get()
                ]

            self.log_text.insert("end", "Running: " + " ".join(cmd) + "\n")
            self.ffmpeg_proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

            for line in self.ffmpeg_proc.stderr:
                self.log_text.insert("end", line)
                self.log_text.see("end")
                self.update()

            rc = self.ffmpeg_proc.wait()
            if rc == 0:
                self.log_text.insert("end", "\nFinished successfully.\n")
                messagebox.showinfo("Done", f"Exported: {self.output_var.get()}")
            else:
                self.log_text.insert("end", f"\nffmpeg exited with code {rc}\n")
                messagebox.showerror("Error", "ffmpeg failed. See log.")
        except FileNotFoundError:
            messagebox.showerror("ffmpeg not found", "Please install ffmpeg and ensure it is in PATH.")
        except Exception as e:
            messagebox.showerror("Error", str(e))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            self.start_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")

    def cancel_conversion(self):
        if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            self.ffmpeg_proc.terminate()
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")

if __name__ == "__main__":
    app = ImageSeqConverter()
    app.mainloop()
