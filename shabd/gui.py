"""Shabd desktop app (Tkinter).

Threading rule (spec "Must never freeze the UI"): ALL transcription happens on
a worker thread; the worker communicates only via a queue.Queue that the UI
thread drains with root.after(). Tk widgets are touched by the UI thread only.
"""

import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, cues, engine as engine_mod, hardware


def _lang_display(code, label):
    return "%s — %s" % (code, label)


class App:
    def __init__(self, root):
        self.root = root
        root.title("Shabd — Offline Subtitle Studio  v" + __version__)
        root.geometry("900x680")
        root.minsize(760, 560)

        self.engine = engine_mod.Engine()
        self.msg_q = queue.Queue()
        self.worker = None
        self.cancel_event = threading.Event()
        self.last_out_dir = None

        self._build_widgets()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(100, self._poll_queue)

    # ------------------------------------------------------------- layout --

    def _build_widgets(self):
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=10, pady=8)

        # --- files ---
        files_box = ttk.LabelFrame(main, text=" 1. Files to subtitle ")
        files_box.pack(fill="x", **pad)
        inner = ttk.Frame(files_box)
        inner.pack(fill="x", padx=6, pady=6)
        self.files_list = tk.Listbox(inner, height=4, selectmode="extended")
        self.files_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(inner, command=self.files_list.yview)
        scroll.pack(side="left", fill="y")
        self.files_list.config(yscrollcommand=scroll.set)
        btns = ttk.Frame(inner)
        btns.pack(side="left", fill="y", padx=(6, 0))
        self.btn_add = ttk.Button(btns, text="Add files…", command=self._add_files)
        self.btn_add.pack(fill="x")
        self.btn_remove = ttk.Button(btns, text="Remove", command=self._remove_selected)
        self.btn_remove.pack(fill="x", pady=(4, 0))
        self.btn_clear = ttk.Button(btns, text="Clear", command=lambda: self.files_list.delete(0, "end"))
        self.btn_clear.pack(fill="x", pady=(4, 0))

        # --- options ---
        opts = ttk.LabelFrame(main, text=" 2. Options ")
        opts.pack(fill="x", **pad)
        grid = ttk.Frame(opts)
        grid.pack(fill="x", padx=6, pady=6)

        recommended = hardware.recommend_tier()
        self.tier_values = []
        for tier, (_model, label) in engine_mod.MODEL_TIERS.items():
            suffix = "  ← recommended for this PC" if tier == recommended else ""
            self.tier_values.append("%s: %s%s" % (tier, label, suffix))
        ttk.Label(grid, text="Accuracy:").grid(row=0, column=0, sticky="w")
        self.tier_var = tk.StringVar(
            value=next(v for v in self.tier_values if v.startswith(recommended)))
        self.tier_combo = ttk.Combobox(grid, textvariable=self.tier_var,
                                       values=self.tier_values, state="readonly", width=52)
        self.tier_combo.grid(row=0, column=1, columnspan=3, sticky="w", padx=6)

        ttk.Label(grid, text="Language:").grid(row=1, column=0, sticky="w")
        lang_values = [_lang_display(c, l) for c, l in engine_mod.COMMON_LANGUAGES]
        self.lang_var = tk.StringVar(value=lang_values[0])
        self.lang_combo = ttk.Combobox(grid, textvariable=self.lang_var,
                                       values=lang_values, width=24)
        self.lang_combo.grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(grid, text="(pick, or type any ISO code)").grid(row=1, column=2, sticky="w")

        ttk.Label(grid, text="Mode:").grid(row=2, column=0, sticky="w")
        self.task_var = tk.StringVar(value="transcribe")
        ttk.Radiobutton(grid, text="Subtitles in the spoken language",
                        variable=self.task_var, value="transcribe").grid(row=2, column=1, sticky="w", padx=6)
        ttk.Radiobutton(grid, text="Translate to English",
                        variable=self.task_var, value="translate").grid(row=2, column=2, sticky="w")

        ttk.Label(grid, text="Save as:").grid(row=3, column=0, sticky="w")
        fmt_frame = ttk.Frame(grid)
        fmt_frame.grid(row=3, column=1, columnspan=2, sticky="w", padx=6)
        self.fmt_srt = tk.BooleanVar(value=True)
        self.fmt_vtt = tk.BooleanVar(value=False)
        self.fmt_txt = tk.BooleanVar(value=False)
        ttk.Checkbutton(fmt_frame, text=".srt subtitles", variable=self.fmt_srt).pack(side="left")
        ttk.Checkbutton(fmt_frame, text=".vtt (web)", variable=self.fmt_vtt).pack(side="left", padx=8)
        ttk.Checkbutton(fmt_frame, text=".txt transcript", variable=self.fmt_txt).pack(side="left")
        self.overwrite_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(fmt_frame, text="Overwrite existing",
                        variable=self.overwrite_var).pack(side="left", padx=16)

        ttk.Label(grid, text="Save into:").grid(row=4, column=0, sticky="w")
        self.outdir_var = tk.StringVar(value="")
        ttk.Entry(grid, textvariable=self.outdir_var, width=48).grid(row=4, column=1, columnspan=2, sticky="w", padx=6)
        ttk.Button(grid, text="Browse…", command=self._pick_outdir).grid(row=4, column=3, sticky="w")
        ttk.Label(grid, text="(empty = next to each video)").grid(row=4, column=4, sticky="w")

        ttk.Label(grid, text="Custom vocabulary:").grid(row=5, column=0, sticky="w")
        self.vocab_var = tk.StringVar(value="")
        ttk.Entry(grid, textvariable=self.vocab_var, width=48).grid(row=5, column=1, columnspan=2, sticky="w", padx=6)
        ttk.Label(grid, text="names/terms, comma-separated").grid(row=5, column=3, columnspan=2, sticky="w")

        ttk.Label(grid, text=hardware.describe(), foreground="#666").grid(
            row=6, column=0, columnspan=5, sticky="w", pady=(6, 0))

        # --- run ---
        run_box = ttk.LabelFrame(main, text=" 3. Run ")
        run_box.pack(fill="both", expand=True, **pad)
        controls = ttk.Frame(run_box)
        controls.pack(fill="x", padx=6, pady=6)
        self.btn_start = ttk.Button(controls, text="▶  Start", command=self._start)
        self.btn_start.pack(side="left")
        self.btn_cancel = ttk.Button(controls, text="Cancel", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=6)
        self.btn_open = ttk.Button(controls, text="Open output folder", command=self._open_outdir, state="disabled")
        self.btn_open.pack(side="left", padx=6)

        self.progress = ttk.Progressbar(run_box, maximum=100)
        self.progress.pack(fill="x", padx=8)
        self.status_var = tk.StringVar(value="Add files and press Start.")
        ttk.Label(run_box, textvariable=self.status_var).pack(anchor="w", padx=8, pady=(2, 4))

        self.preview = tk.Text(run_box, height=10, state="disabled", wrap="word")
        self.preview.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ------------------------------------------------------------ actions --

    def _add_files(self):
        exts = " ".join("*" + e for e in engine_mod.MEDIA_EXTENSIONS)
        paths = filedialog.askopenfilenames(
            title="Choose video or audio files",
            filetypes=[("Video/Audio", exts), ("All files", "*.*")])
        existing = set(self.files_list.get(0, "end"))
        for p in paths:
            if p not in existing:
                self.files_list.insert("end", p)

    def _remove_selected(self):
        for i in reversed(self.files_list.curselection()):
            self.files_list.delete(i)

    def _pick_outdir(self):
        d = filedialog.askdirectory(title="Folder to save subtitles into")
        if d:
            self.outdir_var.set(d)

    def collect_options(self):
        """Read the widgets into a plain dict (kept separate for testing)."""
        tier = self.tier_var.get().split(":", 1)[0].strip()
        lang = self.lang_var.get().split("—", 1)[0].strip() or "auto"
        formats = [f for f, v in
                   (("srt", self.fmt_srt), ("vtt", self.fmt_vtt), ("txt", self.fmt_txt))
                   if v.get()]
        return {
            "tier": tier,
            "language": lang,
            "task": self.task_var.get(),
            "formats": formats,
            "output_dir": self.outdir_var.get().strip() or None,
            "overwrite": self.overwrite_var.get(),
            "vocab": self.vocab_var.get().strip() or None,
        }

    def _start(self):
        files = list(self.files_list.get(0, "end"))
        if not files:
            messagebox.showinfo("Shabd", "Add at least one video or audio file first.")
            return
        opts = self.collect_options()
        if not opts["formats"]:
            messagebox.showinfo("Shabd", "Tick at least one output format (.srt, .vtt or .txt).")
            return
        if opts["overwrite"]:
            if not messagebox.askyesno(
                    "Shabd", "Existing subtitle files with matching names will "
                             "be REPLACED. Continue?"):
                return
        self.cancel_event.clear()
        self._set_running(True)
        self._log_clear()
        self._log("Starting %d file(s) — model tier: %s\n" % (len(files), opts["tier"]))
        self.worker = threading.Thread(
            target=self._run_jobs, args=(files, opts), daemon=True)
        self.worker.start()

    def _cancel(self):
        self.cancel_event.set()
        self.status_var.set("Cancelling after the current segment…")

    def _open_outdir(self):
        if self.last_out_dir and os.path.isdir(self.last_out_dir):
            os.startfile(self.last_out_dir)

    def _on_close(self):
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno("Shabd", "A transcription is running. Stop it and quit?"):
                return
            self.cancel_event.set()
            self.status_var.set("Stopping safely — finishing the current segment…")
            self._shutdown_poll(tries=100)  # up to ~10 s for a clean stop
            return
        self.root.destroy()

    def _shutdown_poll(self, tries):
        """Wait for the worker to stop before destroying the window, so a
        file write is never cut off mid-flight."""
        if self.worker is not None and self.worker.is_alive() and tries > 0:
            self.root.after(100, lambda: self._shutdown_poll(tries - 1))
        else:
            self.root.destroy()

    # ------------------------------------------------------ worker thread --

    def _run_jobs(self, files, opts):
        q = self.msg_q
        done, failed = 0, 0
        try:
            for idx, path in enumerate(files):
                if self.cancel_event.is_set():
                    break
                q.put(("file_start", idx + 1, len(files), path))
                try:
                    result = self.engine.transcribe_file(
                        path,
                        tier_or_model=opts["tier"],
                        language=opts["language"],
                        task=opts["task"],
                        vocab=opts["vocab"],
                        on_progress=lambda f: q.put(("progress", f)),
                        on_segment=lambda t, s, e: q.put(("segment", t, s)),
                        on_status=lambda m: q.put(("status", m)),
                        cancel_event=self.cancel_event,
                    )
                    written = engine_mod.write_outputs(
                        result, path, opts["formats"],
                        output_dir=opts["output_dir"],
                        overwrite=opts["overwrite"],
                    )
                    done += 1
                    q.put(("file_done", path, written, result["language"]))
                except engine_mod.CancelledError:
                    q.put(("log", "Cancelled: " + os.path.basename(path)))
                    break
                except FileExistsError as e:
                    failed += 1
                    q.put(("log", "SKIPPED (already exists): %s — tick 'Overwrite existing' to replace." % e))
                except FileNotFoundError:
                    failed += 1
                    q.put(("log", "ERROR: file not found (moved or renamed?): %s" % path))
                except Exception as e:
                    failed += 1
                    q.put(("log", "ERROR on %s: %s" % (os.path.basename(path), e)))
                    q.put(("log", traceback.format_exc(limit=3)))
        finally:
            q.put(("all_done", done, failed))

    # --------------------------------------------------------- UI updates --

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_q.get_nowait()
                self._handle(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle(self, msg):
        kind = msg[0]
        if kind == "file_start":
            _, i, n, path = msg
            self.progress["value"] = 0
            self.status_var.set("File %d of %d: %s" % (i, n, os.path.basename(path)))
            self._log("\n— %s —\n" % os.path.basename(path))
        elif kind == "progress":
            self.progress["value"] = msg[1] * 100
        elif kind == "status":
            self.status_var.set(msg[1])
        elif kind == "segment":
            _, text, start = msg
            self._log("[%s] %s\n" % (cues.format_timestamp(start, ".")[:8], text))
        elif kind == "file_done":
            _, path, written, lang = msg
            self.last_out_dir = os.path.dirname(written[0]) if written else None
            self._log("Saved (%s): %s\n" % (lang, ", ".join(os.path.basename(w) for w in written)))
        elif kind == "log":
            self._log(msg[1] + "\n")
        elif kind == "all_done":
            _, done, failed = msg
            self._set_running(False)
            self.progress["value"] = 0 if failed else 100
            summary = "Finished: %d done, %d failed/skipped." % (done, failed)
            if self.cancel_event.is_set():
                summary = "Stopped. %d file(s) completed." % done
            self.status_var.set(summary + "  Files are saved next to your videos unless you chose a folder.")
            if self.last_out_dir:
                self.btn_open.config(state="normal")

    def _set_running(self, running):
        state = "disabled" if running else "normal"
        for w in (self.btn_start, self.btn_add, self.btn_remove, self.btn_clear):
            w.config(state=state)
        self.tier_combo.config(state="disabled" if running else "readonly")
        self.btn_cancel.config(state="normal" if running else "disabled")

    def _log(self, text):
        self.preview.config(state="normal")
        self.preview.insert("end", text)
        self.preview.see("end")
        self.preview.config(state="disabled")

    def _log_clear(self):
        self.preview.config(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.config(state="disabled")


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
