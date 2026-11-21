"""
Driver Finder - Modern Windows GUI
Simple, easy-to-understand interface for scanning PC hardware, checking manufacturer driver updates,
and automatically downloading and installing drivers with live progress and zero window popups.
"""

import os
import sys
import json
import time
import shutil
import threading
import webbrowser
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import driver_scanner
import driver_installer
import create_shortcut
import paths
import updater
from version import APP_VERSION, APP_REVISION, APP_BUILD_INFO

def enable_dpi_awareness():
    """Without this, Windows bitmap-stretches the window above 100% scaling."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def system_dpi():
    try:
        import ctypes
        dpi = ctypes.windll.user32.GetDpiForSystem()
        if dpi and dpi >= 48:
            return dpi
    except Exception:
        pass
    try:
        import ctypes
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        if dpi and dpi >= 48:
            return dpi
    except Exception:
        pass
    return 96


def apply_tk_scaling(root):
    try:
        root.tk.call("tk", "scaling", system_dpi() / 72.0)
    except Exception:
        pass


class InstallationDialog(tk.Toplevel):
    """
    Dedicated dialog for downloading and installing drivers with live real-time progress bars,
    activity streaming, silent UAC execution, and reboot management.
    """
    def __init__(self, parent, devices_to_update, on_completed_callback):
        super().__init__(parent)
        self.parent = parent
        self.devices = devices_to_update
        self.on_completed = on_completed_callback
        self.title("Driver Installation Manager")
        self.geometry("680x540")
        self.minsize(620, 480)
        self.transient(parent)
        self.grab_set()

        self.download_base = paths.downloads_dir()

        self.reboot_required = False
        self.is_running = True
        self.countdown_active = False
        self.countdown_seconds = 10
        self.last_log_pos = 0

        self.configure(bg="#F8FAFC")
        self.build_ui()
        self.start_pipeline()

    def build_ui(self):
        # 1. Header
        header = tk.Frame(self, bg="#0F172A", padx=24, pady=16)
        header.pack(fill=tk.X, side=tk.TOP)

        title = tk.Label(
            header,
            text="🚀 Installing Driver Updates",
            font=("Segoe UI", 15, "bold"),
            fg="#F8FAFC",
            bg="#0F172A"
        )
        title.pack(anchor=tk.W)

        self.lbl_subtitle = tk.Label(
            header,
            text=f"Preparing to update {len(self.devices)} device(s)...",
            font=("Segoe UI", 9),
            fg="#94A3B8",
            bg="#0F172A"
        )
        self.lbl_subtitle.pack(anchor=tk.W, pady=(3, 0))

        # 2. Main Content
        content = tk.Frame(self, bg="#F8FAFC", padx=24, pady=16)
        content.pack(fill=tk.BOTH, expand=True)

        # Progress Status Card
        card = tk.Frame(content, bg="#FFFFFF", padx=18, pady=14, bd=1, relief=tk.SOLID)
        card.pack(fill=tk.X)

        self.lbl_step_phase = tk.Label(
            card,
            text="Phase 1: Downloading Driver Packages",
            font=("Segoe UI", 9, "bold"),
            fg="#2563EB",
            bg="#FFFFFF",
            anchor=tk.W
        )
        self.lbl_step_phase.pack(fill=tk.X)

        self.lbl_step = tk.Label(
            card,
            text="Initializing...",
            font=("Segoe UI Semibold", 11),
            fg="#0F172A",
            bg="#FFFFFF",
            anchor=tk.W
        )
        self.lbl_step.pack(fill=tk.X, pady=(2, 6))

        # Item Progress Bar
        self.progress_item = ttk.Progressbar(card, mode="determinate", length=400)
        self.progress_item.pack(fill=tk.X, pady=(2, 2))

        self.lbl_item_details = tk.Label(
            card,
            text="Waiting to start...",
            font=("Segoe UI", 8),
            fg="#64748B",
            bg="#FFFFFF",
            anchor=tk.W
        )
        self.lbl_item_details.pack(fill=tk.X)

        # Overall Progress Bar
        self.lbl_overall = tk.Label(
            card,
            text=f"Overall Progress: 0 of {len(self.devices)} completed",
            font=("Segoe UI Semibold", 9),
            fg="#334155",
            bg="#FFFFFF",
            anchor=tk.W
        )
        self.lbl_overall.pack(fill=tk.X, pady=(12, 4))

        self.progress_overall = ttk.Progressbar(card, mode="determinate", maximum=100)
        self.progress_overall.pack(fill=tk.X)

        # Activity Log Area
        log_frame = tk.Frame(content, bg="#F8FAFC", pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            log_frame,
            text="Live Activity & Installation Log:",
            font=("Segoe UI Semibold", 9),
            fg="#334155",
            bg="#F8FAFC"
        ).pack(anchor=tk.W, pady=(0, 4))

        self.log_text = tk.Text(
            log_frame,
            font=("Consolas", 8),
            bg="#FFFFFF",
            fg="#1E293B",
            height=7,
            bd=1,
            relief=tk.SOLID
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Bottom Alert Frame (Hidden initially)
        self.alert_frame = tk.Frame(self, bg="#FEF3C7", padx=20, pady=12, bd=1, relief=tk.SOLID)

        self.lbl_alert = tk.Label(
            self.alert_frame,
            text="⚠️ RESTART REQUIRED: New drivers have been installed and require a computer restart to complete.",
            font=("Segoe UI Semibold", 10),
            fg="#92400E",
            bg="#FEF3C7",
            wraplength=580,
            justify=tk.LEFT
        )
        self.lbl_alert.pack(fill=tk.X, pady=(0, 8))

        alert_btns = tk.Frame(self.alert_frame, bg="#FEF3C7")
        alert_btns.pack(fill=tk.X)

        self.btn_restart_now = tk.Button(
            alert_btns,
            text="🔄 Restart Computer Now",
            font=("Segoe UI", 10, "bold"),
            bg="#DC2626",
            fg="#FFFFFF",
            activebackground="#B91C1C",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self.on_click_restart_now
        )
        self.btn_restart_now.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_restart_later = tk.Button(
            alert_btns,
            text="⏱️ Restart Later",
            font=("Segoe UI", 9),
            bg="#FFFFFF",
            fg="#334155",
            activebackground="#F1F5F9",
            relief=tk.SOLID,
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.on_click_restart_later
        )
        self.btn_restart_later.pack(side=tk.LEFT)

        self.btn_cancel_restart = tk.Button(
            alert_btns,
            text="Abort Restart",
            font=("Segoe UI", 9),
            bg="#FEE2E2",
            fg="#991B1B",
            relief=tk.FLAT,
            padx=10,
            pady=5,
            cursor="hand2",
            command=self.on_click_cancel_restart
        )

        # Dialog Footer
        self.footer = tk.Frame(self, bg="#F1F5F9", padx=24, pady=10)
        self.footer.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_close = tk.Button(
            self.footer,
            text="Close",
            font=("Segoe UI", 9),
            bg="#E2E8F0",
            fg="#334155",
            relief=tk.FLAT,
            padx=18,
            pady=5,
            state=tk.DISABLED,
            command=self.destroy
        )
        self.btn_close.pack(side=tk.RIGHT)

    def log(self, text):
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    DOWNLOAD_WORKERS = 3
    STATUS_WAIT_TIMEOUT = 180

    def start_pipeline(self):
        self._build_jobs()
        self._ticker_running = True
        self._tick_progress()
        threading.Thread(target=self.run_download_and_extract, daemon=True).start()

    def _build_jobs(self):
        """One job per device. The job index is part of the folder name so two
        devices with similar names can never share a cab or extract folder."""
        self._jobs = []
        self._jobs_lock = threading.Lock()
        for idx, dev in enumerate(self.devices):
            name = dev.get("description", "Device")
            dev_slug = "".join(c if c.isalnum() else "_" for c in name)[:40]
            self._jobs.append({
                "index": idx,
                "device": dev,
                "name": name,
                "slug": f"{idx:02d}_{dev_slug}",
                "extract_dir": "",
                "done": False,
                "ok": False,
                "downloaded": 0,
                "total_bytes": 0,
            })

    def _finish_job(self, job, ok):
        with self._jobs_lock:
            job["done"] = True
            job["ok"] = ok

    def _post_log(self, text):
        self.after(0, self.log, text)

    def _tick_progress(self):
        """Single UI update per tick, driven by aggregate job state."""
        if not self._ticker_running:
            return

        total = len(self._jobs)
        with self._jobs_lock:
            done = sum(1 for j in self._jobs if j["done"])
            active = [j for j in self._jobs if not j["done"]]
            current = active[0] if active else None
            downloaded = sum(j["downloaded"] for j in self._jobs)
            total_bytes = sum(j["total_bytes"] for j in self._jobs)
            item_pct = 0
            if current and current["total_bytes"]:
                item_pct = int(current["downloaded"] * 100 / current["total_bytes"])
            current_name = current["name"] if current else ""

        if total:
            self.progress_item.config(mode="determinate", value=item_pct)
            self.lbl_step.config(
                text=f"Downloading ({min(done + 1, total)}/{total}): {current_name or 'finishing up'}"
            )
            self.lbl_item_details.config(
                text=f"{downloaded / 1048576:.1f} MB / {total_bytes / 1048576:.1f} MB"
            )
            self.progress_overall.config(value=int(done * 50 / total))
            self.lbl_overall.config(
                text=f"Overall Download Progress: {done} of {total} packages ready"
            )

        self.after(150, self._tick_progress)

    def _fetch_and_extract_job(self, job):
        dev = job["device"]
        name = job["name"]
        target_cab = os.path.join(self.download_base, job["slug"] + ".cab")
        target_extract = os.path.join(self.download_base, "extract_" + job["slug"])
        job["extract_dir"] = target_extract

        shutil.rmtree(target_extract, ignore_errors=True)
        try:
            if os.path.exists(target_cab):
                os.remove(target_cab)
        except Exception:
            pass

        self._post_log(f"\n--- Downloading: {name} ---")

        dl_url = dev.get("download_url") or ""
        if not dl_url.startswith("http"):
            driver_scanner.check_device_update(dev)
            dl_url = dev.get("download_url") or ""

        if not dl_url.startswith("http"):
            self._post_log(f"  No direct download URL available for {name}.")
            self._finish_job(job, False)
            return job

        def progress_hook(downloaded, total_size, pct):
            with self._jobs_lock:
                job["downloaded"] = downloaded
                job["total_bytes"] = total_size

        try:
            ok = driver_installer.download_driver_file(dl_url, target_cab, progress_hook)
            if not ok:
                self._post_log("  Download failed.")
                self._finish_job(job, False)
                return job
        except Exception as exc:
            self._post_log(f"  Download error: {exc}")
            self._finish_job(job, False)
            return job

        try:
            driver_installer.extract_cab(target_cab, target_extract)
        except Exception as exc:
            self._post_log(f"  Extraction error: {exc}")
            self._finish_job(job, False)
            return job

        size_mb = os.path.getsize(target_cab) / 1048576 if os.path.exists(target_cab) else 0
        self._post_log(f"  Downloaded {size_mb:.1f} MB and extracted: {name}")
        self._finish_job(job, True)
        return job

    def run_download_and_extract(self):
        total = len(self._jobs)
        self._post_log(
            f"[{datetime.now().strftime('%H:%M:%S')}] Phase 1: Downloading & extracting "
            f"{total} driver package(s) ({self.DOWNLOAD_WORKERS} at a time)..."
        )

        with ThreadPoolExecutor(max_workers=self.DOWNLOAD_WORKERS) as pool:
            futures = [pool.submit(self._fetch_and_extract_job, job) for job in self._jobs]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    self._post_log(f"  Unexpected worker error: {exc}")

        self._ticker_running = False

        install_plan = {"devices": []}
        for job in self._jobs:
            if job["ok"]:
                install_plan["devices"].append({
                    "name": job["name"],
                    "extract_dir": job["extract_dir"],
                })

        self._post_log(f"Phase 1 complete: {len(install_plan['devices'])} of {total} package(s) ready.")

        plan_file = os.path.join(self.download_base, "install_plan.json")
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(install_plan, f, indent=2)

        self.after(0, lambda: self.start_elevated_installation(install_plan["devices"]))

    # --- Phase 2: Live Elevated Installation ---

    def _elevated_helper_running(self):
        """True when a second copy of our own exe is alive (the UAC-approved worker)."""
        try:
            image = os.path.basename(sys.executable)
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq " + image, "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=0x08000000,
            )
            return result.stdout.lower().count(image.lower()) > 1
        except Exception:
            return False

    def start_elevated_installation(self, ready_devices):
        if not ready_devices:
            self.log("\n❌ No driver packages available to install.")
            self.on_pipeline_completed()
            return

        total = len(ready_devices)
        self.lbl_step_phase.config(text="Phase 2 of 2: Installing Drivers into Windows", fg="#059669")
        self.lbl_step.config(text="Requesting Administrator authorization (UAC)...")
        self.lbl_item_details.config(text="Please click 'Yes' on the Windows permission prompt...")
        self.progress_item.config(mode="indeterminate")
        self.progress_item.start(10)

        self.log("\n=======================================================")
        self.log("Phase 2: Requesting Windows Administrator Elevation (UAC)...")
        self.log("Please click 'Yes' on the Windows prompt to authorize the installation.")
        self.log("=======================================================\n")

        # Launch the elevated background worker silently
        ok = driver_installer.launch_elevated_worker(self.download_base)
        if not ok:
            self.log("❌ Elevation cancelled or failed to launch.")
            self.on_pipeline_completed()
            return

        # Start polling loop for install_status.json
        self._status_wait_started = time.time()
        self.poll_worker_status(total)

    def poll_worker_status(self, total):
        status_file = os.path.join(self.download_base, "install_status.json")
        log_file = os.path.join(self.download_base, "install_log.txt")

        # The helper writes its status immediately. If nothing arrives and no
        # elevated copy of us is running, say so instead of spinning forever.
        if not os.path.exists(status_file):
            waited = time.time() - getattr(self, "_status_wait_started", time.time())
            if waited > self.STATUS_WAIT_TIMEOUT:
                if self._elevated_helper_running():
                    self._status_wait_started = time.time()
                else:
                    self.progress_item.stop()
                    self.log("\n❌ The elevated installer never started. Nothing was installed.")
                    self.lbl_step.config(text="❌ Installation did not start")
                    self.lbl_item_details.config(
                        text="The UAC-approved helper never reported back."
                    )
                    messagebox.showerror(
                        "Driver installation did not start",
                        "Windows reported the permission prompt as approved, but the installer "
                        "helper never reported back.\n\n"
                        "Nothing was installed and no drivers were changed.\n\n"
                        "Close this dialog and try again."
                    )
                    self.on_pipeline_completed()
                    return

        # Stream new lines from install_log.txt
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(self.last_log_pos)
                    new_text = f.read()
                    self.last_log_pos = f.tell()
                    if new_text:
                        for line in new_text.splitlines():
                            if line.strip():
                                self.log(f"  [Installer] {line}")
            except Exception:
                pass

        if os.path.exists(status_file):
            try:
                with open(status_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                state = data.get("state", "running")
                current_idx = data.get("current_index", 0)
                current_name = data.get("current_device", "")
                reboot_needed = data.get("reboot_required", False)

                if reboot_needed:
                    self.reboot_required = True

                # Progress: Phase 2 is from 50% to 100%
                install_pct = data.get("percent", 0)
                overall_value = 50 + int(install_pct * 0.5)
                self.progress_overall.config(value=overall_value)

                if state == "installing":
                    self.lbl_step.config(text=f"⚙️ Installing ({current_idx}/{total}): {current_name}")
                    self.lbl_item_details.config(text="Adding driver package to Windows DriverStore...")
                    self.lbl_overall.config(text=f"Overall Progress: Installing {current_idx} of {total} ({overall_value}%)")
                elif state == "finished":
                    self.progress_item.stop()
                    self.progress_item.config(mode="determinate", value=100)
                    self.progress_overall.config(value=100)
                    self.lbl_step.config(text="✅ All driver packages installed successfully!")
                    self.lbl_item_details.config(text="Finished installation.")
                    self.lbl_overall.config(text=f"Overall Progress: 100% Completed")
                    self.on_pipeline_completed()
                    return
                elif state == "error":
                    self.log(f"❌ Error during installation: {data.get('error')}")
                    self.on_pipeline_completed()
                    return

            except Exception:
                pass

        # Continue polling every 250ms
        self.after(250, lambda: self.poll_worker_status(total))

    def on_pipeline_completed(self):
        self.progress_item.stop()
        self.btn_close.config(state=tk.NORMAL)

        if self.on_completed:
            self.on_completed(self.reboot_required)

        if self.reboot_required:
            self.alert_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=24, pady=(0, 10))
            self.lbl_subtitle.config(
                text="Driver installation finished! A computer restart is REQUIRED to finalize updates.",
                fg="#F59E0B"
            )
        else:
            self.lbl_subtitle.config(
                text="Installation completed successfully! All drivers are up to date.",
                fg="#10B981"
            )

    # --- Restart Handlers ---

    def on_click_restart_now(self):
        self.countdown_seconds = 10
        self.countdown_active = True
        self.btn_restart_now.config(state=tk.DISABLED)
        self.btn_cancel_restart.pack(side=tk.LEFT, padx=6)
        
        driver_installer.restart_computer(self.countdown_seconds)
        self.tick_countdown()

    def tick_countdown(self):
        if not self.countdown_active:
            return
        if self.countdown_seconds > 0:
            self.lbl_alert.config(
                text=f"🔄 Computer is restarting in {self.countdown_seconds} seconds! Please save your open documents. Click 'Abort Restart' to cancel.",
                fg="#B91C1C"
            )
            self.countdown_seconds -= 1
            self.after(1000, self.tick_countdown)
        else:
            self.lbl_alert.config(text="🔄 Restarting system now...")

    def on_click_cancel_restart(self):
        self.countdown_active = False
        driver_installer.cancel_restart()
        self.btn_cancel_restart.pack_forget()
        self.btn_restart_now.config(state=tk.NORMAL)
        self.lbl_alert.config(
            text="⚠️ Restart cancelled. Please remember to restart your computer when convenient to finalize the driver installation.",
            fg="#92400E"
        )

    def on_click_restart_later(self):
        self.destroy()


class DriverFinderApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Driver Finder {APP_BUILD_INFO} - Hardware & Manufacturer Driver Scanner")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1100, max(880, screen_width - 60))
        height = min(740, max(540, screen_height - 120))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(980, width), min(600, height))

        self.project_dir = paths.resource_dir()
        icon_path = sys.executable if paths.is_frozen() else os.path.join(self.project_dir, "app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        self.system_info = {}
        self.all_devices = []
        self.displayed_devices = []
        self.selected_device = None
        self.reboot_pending = False
        self.update_release = None
        self._update_check_running = False
        self.current_category = "⭐ Key Hardware"
        self.filter_updates_only = tk.BooleanVar(value=False)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.apply_filters())

        self.bg_color = "#F8FAFC"
        self.header_bg = "#0F172A"
        self.card_bg = "#FFFFFF"
        self.text_primary = "#0F172A"
        self.text_secondary = "#475569"
        self.accent_blue = "#2563EB"
        self.accent_green = "#059669"
        self.accent_amber = "#D97706"
        self.border_color = "#E2E8F0"

        self.root.configure(bg=self.bg_color)
        self.setup_styles()
        self.build_ui()

        self.trigger_scan(initial=True)
        self.root.after(2500, lambda: self.check_app_updates(manual=False))

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Treeview",
            background="#FFFFFF",
            foreground="#1E293B",
            rowheight=32,
            fieldbackground="#FFFFFF",
            font=("Segoe UI", 10),
            borderwidth=0
        )
        style.configure(
            "Treeview.Heading",
            background="#F1F5F9",
            foreground="#334155",
            font=("Segoe UI Semibold", 10),
            padding=(8, 6),
            borderwidth=0
        )
        style.map(
            "Treeview",
            background=[("selected", "#E0E7FF")],
            foreground=[("selected", "#1E1B4B")]
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#E2E8F0")]
        )

        style.configure("Vertical.TScrollbar", troughcolor="#F1F5F9", borderwidth=0, arrowsize=14)

    def build_ui(self):
        # 1. TOP HEADER BANNER
        header = tk.Frame(self.root, bg=self.header_bg, padx=24, pady=16)
        header.pack(fill=tk.X, side=tk.TOP)

        header_top = tk.Frame(header, bg=self.header_bg)
        header_top.pack(fill=tk.X)

        title_box = tk.Frame(header_top, bg=self.header_bg)
        title_box.pack(side=tk.LEFT)

        title_label = tk.Label(
            title_box,
            text="Driver Finder",
            font=("Segoe UI", 20, "bold"),
            fg="#F8FAFC",
            bg=self.header_bg
        )
        title_label.pack(side=tk.LEFT)

        rev_badge = tk.Label(
            title_box,
            text=f"🏷️ Rev {APP_REVISION}",
            font=("Segoe UI", 9, "bold"),
            fg="#38BDF8",
            bg="#1E293B",
            padx=8,
            pady=2,
            bd=1,
            relief=tk.SOLID
        )
        rev_badge.pack(side=tk.LEFT, padx=(12, 0), pady=(4, 0))

        ver_badge = tk.Label(
            title_box,
            text=f"v{APP_VERSION}",
            font=("Segoe UI", 9),
            fg="#94A3B8",
            bg=self.header_bg
        )
        ver_badge.pack(side=tk.LEFT, padx=(6, 0), pady=(4, 0))

        subtitle = tk.Label(
            header_top,
            text="Hardware Scanner & Official Manufacturer Driver Checker",
            font=("Segoe UI", 11),
            fg="#94A3B8",
            bg=self.header_bg
        )
        subtitle.pack(side=tk.LEFT, padx=(16, 0), pady=(4, 0))

        # Top Right Quick Utility Buttons
        btn_box = tk.Frame(header_top, bg=self.header_bg)
        btn_box.pack(side=tk.RIGHT)

        self.btn_oem = tk.Button(
            btn_box,
            text="🌐 Manufacturer Support",
            font=("Segoe UI", 9, "bold"),
            bg="#0284C7",
            fg="#FFFFFF",
            activebackground="#0369A1",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.open_oem_portal
        )
        self.btn_oem.pack(side=tk.LEFT, padx=4)

        btn_devmgmt = tk.Button(
            btn_box,
            text="🛠️ Device Manager",
            font=("Segoe UI", 9),
            bg="#334155",
            fg="#F8FAFC",
            activebackground="#475569",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.open_device_manager
        )
        btn_devmgmt.pack(side=tk.LEFT, padx=4)

        btn_desktop = tk.Button(
            btn_box,
            text="📌 Desktop Shortcut",
            font=("Segoe UI", 9),
            bg="#334155",
            fg="#F8FAFC",
            activebackground="#475569",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.make_desktop_shortcut
        )
        btn_desktop.pack(side=tk.LEFT, padx=4)

        self.btn_check_app_update = tk.Button(
            btn_box,
            text="⬆️ Update App",
            font=("Segoe UI", 9),
            bg="#334155",
            fg="#F8FAFC",
            activebackground="#475569",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            command=lambda: self.check_app_updates(manual=True)
        )
        self.btn_check_app_update.pack(side=tk.LEFT, padx=4)

        # Header Info Strip (PC details)
        self.pc_info_label = tk.Label(
            header,
            text="Detecting system hardware...",
            font=("Segoe UI", 10),
            fg="#38BDF8",
            bg=self.header_bg
        )
        self.pc_info_label.pack(fill=tk.X, pady=(8, 0))

        # 1.5 PERSISTENT REBOOT BANNER
        self.reboot_banner = tk.Frame(self.root, bg="#FEE2E2", padx=24, pady=8, bd=1, relief=tk.SOLID)

        lbl_reboot_msg = tk.Label(
            self.reboot_banner,
            text="⚠️ RESTART REQUIRED: Driver updates were installed. Please restart your computer to finish the installation.",
            font=("Segoe UI Semibold", 10),
            fg="#991B1B",
            bg="#FEE2E2"
        )
        lbl_reboot_msg.pack(side=tk.LEFT)

        btn_banner_restart = tk.Button(
            self.reboot_banner,
            text="🔄 Restart Computer Now",
            font=("Segoe UI", 9, "bold"),
            bg="#DC2626",
            fg="#FFFFFF",
            activebackground="#B91C1C",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=12,
            pady=3,
            cursor="hand2",
            command=self.trigger_restart_now
        )
        btn_banner_restart.pack(side=tk.RIGHT, padx=4)

        # 1.6 APP UPDATE BANNER (packed only when a newer release exists)
        self.update_banner = tk.Frame(self.root, bg="#E0F2FE", padx=24, pady=8, bd=1, relief=tk.SOLID)

        self.lbl_update_msg = tk.Label(
            self.update_banner,
            text="",
            font=("Segoe UI Semibold", 10),
            fg="#075985",
            bg="#E0F2FE"
        )
        self.lbl_update_msg.pack(side=tk.LEFT)

        self.btn_update_install = tk.Button(
            self.update_banner,
            text="⬆️ Install Update",
            font=("Segoe UI", 9, "bold"),
            bg="#0284C7",
            fg="#FFFFFF",
            activebackground="#0369A1",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=12,
            pady=3,
            cursor="hand2",
            command=self.on_click_install_update
        )
        self.btn_update_install.pack(side=tk.RIGHT, padx=4)

        btn_update_notes = tk.Button(
            self.update_banner,
            text="📝 Release Notes",
            font=("Segoe UI", 9),
            bg="#FFFFFF",
            fg="#075985",
            activebackground="#F1F5F9",
            relief=tk.SOLID,
            bd=1,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.on_click_update_notes
        )
        btn_update_notes.pack(side=tk.RIGHT, padx=4)

        btn_update_later = tk.Button(
            self.update_banner,
            text="Later",
            font=("Segoe UI", 9),
            bg="#FFFFFF",
            fg="#475569",
            activebackground="#F1F5F9",
            relief=tk.SOLID,
            bd=1,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.on_click_dismiss_update
        )
        btn_update_later.pack(side=tk.RIGHT, padx=4)

        # 2. STATS & ACTION CONTROLS STRIP
        action_strip = tk.Frame(self.root, bg="#FFFFFF", padx=24, pady=12, highlightthickness=1, highlightbackground="#E2E8F0")
        action_strip.pack(fill=tk.X, side=tk.TOP)

        left_actions = tk.Frame(action_strip, bg="#FFFFFF")
        left_actions.pack(side=tk.LEFT)

        self.btn_update_all = tk.Button(
            left_actions,
            text="🚀  Update All Drivers",
            font=("Segoe UI", 11, "bold"),
            bg="#059669",
            fg="#FFFFFF",
            activebackground="#047857",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self.action_update_all_drivers
        )
        self.btn_update_all.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_scan = tk.Button(
            left_actions,
            text="🔍  Scan Computer",
            font=("Segoe UI", 10, "bold"),
            bg="#2563EB",
            fg="#FFFFFF",
            activebackground="#1D4ED8",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=14,
            pady=6,
            cursor="hand2",
            command=lambda: self.trigger_scan(initial=False)
        )
        self.btn_scan.pack(side=tk.LEFT, padx=4)

        self.btn_check_all = tk.Button(
            left_actions,
            text="⚡  Check Updates",
            font=("Segoe UI", 10),
            bg="#F1F5F9",
            fg="#334155",
            activebackground="#E2E8F0",
            relief=tk.FLAT,
            padx=12,
            pady=7,
            cursor="hand2",
            command=self.trigger_check_updates
        )
        self.btn_check_all.pack(side=tk.LEFT, padx=4)

        self.btn_export = tk.Button(
            left_actions,
            text="💾  Export Report",
            font=("Segoe UI", 10),
            bg="#F1F5F9",
            fg="#334155",
            activebackground="#E2E8F0",
            relief=tk.FLAT,
            padx=12,
            pady=7,
            cursor="hand2",
            command=self.export_report
        )
        self.btn_export.pack(side=tk.LEFT, padx=4)

        kpi_box = tk.Frame(action_strip, bg="#FFFFFF")
        kpi_box.pack(side=tk.RIGHT)

        self.kpi_total = self.create_kpi_badge(kpi_box, "Total Devices", "0", "#334155", "#F1F5F9")
        self.kpi_primary = self.create_kpi_badge(kpi_box, "Key Devices", "0", "#0284C7", "#E0F2FE")
        self.kpi_updates = self.create_kpi_badge(kpi_box, "Updates Available", "0", "#D97706", "#FEF3C7")
        self.kpi_uptodate = self.create_kpi_badge(kpi_box, "Up to Date", "0", "#16A34A", "#DCFCE7")

        # 3. CATEGORY TABS & FILTER BAR
        filter_bar = tk.Frame(self.root, bg=self.bg_color, padx=24, pady=10)
        filter_bar.pack(fill=tk.X, side=tk.TOP)

        self.cat_frame = tk.Frame(filter_bar, bg=self.bg_color)
        self.cat_frame.pack(side=tk.LEFT)

        self.category_buttons = {}
        categories = [
            "⭐ Key Hardware",
            "🖥️ Display",
            "🌐 Network",
            "🔊 Audio",
            "🔵 Bluetooth",
            "💾 Storage",
            "📋 All Devices"
        ]

        for cat in categories:
            btn = tk.Button(
                self.cat_frame,
                text=cat,
                font=("Segoe UI", 9, "bold" if cat == self.current_category else "normal"),
                bg="#2563EB" if cat == self.current_category else "#FFFFFF",
                fg="#FFFFFF" if cat == self.current_category else "#475569",
                activebackground="#1D4ED8" if cat == self.current_category else "#F1F5F9",
                activeforeground="#FFFFFF" if cat == self.current_category else "#1E293B",
                relief=tk.FLAT,
                padx=10,
                pady=4,
                cursor="hand2",
                command=lambda c=cat: self.select_category(c)
            )
            btn.pack(side=tk.LEFT, padx=3)
            self.category_buttons[cat] = btn

        search_frame = tk.Frame(filter_bar, bg=self.bg_color)
        search_frame.pack(side=tk.RIGHT)

        chk_updates = tk.Checkbutton(
            search_frame,
            text="Show Updates Only",
            variable=self.filter_updates_only,
            font=("Segoe UI", 9),
            bg=self.bg_color,
            fg="#1E293B",
            activebackground=self.bg_color,
            command=self.apply_filters
        )
        chk_updates.pack(side=tk.LEFT, padx=(0, 10))

        search_lbl = tk.Label(search_frame, text="🔍", font=("Segoe UI", 10), bg=self.bg_color, fg="#64748B")
        search_lbl.pack(side=tk.LEFT)

        search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            font=("Segoe UI", 9),
            bg="#FFFFFF",
            fg="#1E293B",
            relief=tk.SOLID,
            bd=1,
            width=22
        )
        search_entry.pack(side=tk.LEFT, ipady=3, padx=(4, 0))

        # 4. MAIN DEVICE TABLE (TREEVIEW)
        table_container = tk.Frame(self.root, bg="#FFFFFF", padx=24, pady=0)
        table_container.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        table_border = tk.Frame(table_container, bg="#E2E8F0", bd=1)
        table_border.pack(fill=tk.BOTH, expand=True)

        columns = ("status", "name", "category", "installed", "latest", "vendor")
        self.tree = ttk.Treeview(
            table_border,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Treeview"
        )

        self.tree.heading("status", text="Status")
        self.tree.heading("name", text="Device Name")
        self.tree.heading("category", text="Category")
        self.tree.heading("installed", text="Installed Driver")
        self.tree.heading("latest", text="Latest Found (Catalog)")
        self.tree.heading("vendor", text="Manufacturer / Provider")

        # Status has to fit "Windows-Managed" in full; the rest yield space to it.
        self.tree.column("status", width=178, minwidth=170, anchor=tk.W)
        self.tree.column("name", width=310, minwidth=200, anchor=tk.W)
        self.tree.column("category", width=126, minwidth=100, anchor=tk.W)
        self.tree.column("installed", width=162, minwidth=140, anchor=tk.W)
        self.tree.column("latest", width=162, minwidth=140, anchor=tk.W)
        self.tree.column("vendor", width=140, minwidth=110, anchor=tk.W)

        v_scroll = ttk.Scrollbar(table_border, orient=tk.VERTICAL, command=self.tree.yview)
        h_scroll = ttk.Scrollbar(table_border, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.bind("<<TreeviewSelect>>", self.on_device_selected)
        self.tree.bind("<Double-1>", lambda e: self.action_check_current_device())

        self.tree.tag_configure("update_available", foreground="#B45309", background="#FFFBEB")
        self.tree.tag_configure("up_to_date", foreground="#15803D", background="#F0FDF4")
        self.tree.tag_configure("ready", foreground="#1E293B", background="#FFFFFF")
        self.tree.tag_configure("check_failed", foreground="#B91C1C", background="#FEF2F2")
        self.tree.tag_configure("windows_managed", foreground="#475569", background="#F1F5F9")

        # 5. BOTTOM SELECTED DEVICE DETAIL PANEL
        self.detail_frame = tk.Frame(
            self.root,
            bg="#FFFFFF",
            padx=24,
            pady=12,
            highlightthickness=1,
            highlightbackground="#CBD5E1"
        )
        self.detail_frame.pack(fill=tk.X, side=tk.TOP, pady=(4, 0))

        self.lbl_sel_title = tk.Label(
            self.detail_frame,
            text="Select a device to view driver status, manufacturer updates, and download/install options.",
            font=("Segoe UI Semibold", 11),
            fg="#0F172A",
            bg="#FFFFFF",
            anchor=tk.W
        )
        self.lbl_sel_title.pack(fill=tk.X)

        self.lbl_sel_details = tk.Label(
            self.detail_frame,
            text="Hardware ID: -  |  Provider: -  |  INF Name: -",
            font=("Segoe UI", 9),
            fg="#64748B",
            bg="#FFFFFF",
            anchor=tk.W
        )
        self.lbl_sel_details.pack(fill=tk.X, pady=(2, 8))

        self.detail_actions = tk.Frame(self.detail_frame, bg="#FFFFFF")
        self.detail_actions.pack(fill=tk.X)

        self.btn_install_single = tk.Button(
            self.detail_actions,
            text="⬇️ Install This Driver",
            font=("Segoe UI", 9, "bold"),
            bg="#059669",
            fg="#FFFFFF",
            activebackground="#047857",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
            state=tk.DISABLED,
            command=self.action_install_single_device
        )
        self.btn_install_single.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_check_single = tk.Button(
            self.detail_actions,
            text="🌐 Check Online",
            font=("Segoe UI", 9),
            bg="#2563EB",
            fg="#FFFFFF",
            activebackground="#1D4ED8",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            state=tk.DISABLED,
            command=self.action_check_current_device
        )
        self.btn_check_single.pack(side=tk.LEFT, padx=6)

        self.btn_download = tk.Button(
            self.detail_actions,
            text="🌐 View in Catalog / OEM",
            font=("Segoe UI", 9),
            bg="#F1F5F9",
            fg="#1E293B",
            activebackground="#E2E8F0",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            state=tk.DISABLED,
            command=self.action_open_download
        )
        self.btn_download.pack(side=tk.LEFT, padx=6)

        self.btn_vendor = tk.Button(
            self.detail_actions,
            text="🏢 Manufacturer Site",
            font=("Segoe UI", 9),
            bg="#F1F5F9",
            fg="#1E293B",
            activebackground="#E2E8F0",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            state=tk.DISABLED,
            command=self.action_open_vendor
        )
        self.btn_vendor.pack(side=tk.LEFT, padx=6)

        self.btn_copy_hwid = tk.Button(
            self.detail_actions,
            text="📋 Copy Hardware ID",
            font=("Segoe UI", 9),
            bg="#F1F5F9",
            fg="#1E293B",
            activebackground="#E2E8F0",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            state=tk.DISABLED,
            command=self.action_copy_hwid
        )
        self.btn_copy_hwid.pack(side=tk.LEFT, padx=6)

        # 6. BOTTOM STATUS BAR
        status_bar = tk.Frame(self.root, bg="#F1F5F9", padx=16, pady=4, highlightthickness=1, highlightbackground="#E2E8F0")
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_status = tk.Label(
            status_bar,
            text="Ready.",
            font=("Segoe UI", 9),
            fg="#475569",
            bg="#F1F5F9"
        )
        self.lbl_status.pack(side=tk.LEFT)

        self.lbl_ver_badge = tk.Label(
            status_bar,
            text=f"Driver Finder {APP_BUILD_INFO}",
            font=("Segoe UI", 8),
            fg="#64748B",
            bg="#F1F5F9"
        )
        self.lbl_ver_badge.pack(side=tk.RIGHT, padx=10)

        self.progress = ttk.Progressbar(status_bar, mode="indeterminate", length=180)

    def create_kpi_badge(self, parent, label, val, fg, bg):
        frame = tk.Frame(parent, bg=bg, padx=12, pady=4, bd=0)
        frame.pack(side=tk.LEFT, padx=4)

        val_lbl = tk.Label(frame, text=val, font=("Segoe UI", 12, "bold"), fg=fg, bg=bg)
        val_lbl.pack(side=tk.LEFT)

        txt_lbl = tk.Label(frame, text=f" {label}", font=("Segoe UI", 9), fg=fg, bg=bg)
        txt_lbl.pack(side=tk.LEFT)

        return val_lbl

    def update_kpis(self):
        total = len(self.all_devices)
        primary = len([d for d in self.all_devices if d.get("is_primary")])
        updates = len([d for d in self.all_devices if d.get("catalog_status") == "Update Available"])
        uptodate = len([d for d in self.all_devices if d.get("catalog_status") in ["Up to Date", "Up to Date / OEM", "Windows-Managed", "Up to Date / Windows"]])

        self.kpi_total.config(text=str(total))
        self.kpi_primary.config(text=str(primary))
        self.kpi_updates.config(text=str(updates))
        self.kpi_uptodate.config(text=str(uptodate))

        if updates > 0:
            self.btn_update_all.config(
                text=f"🚀  Update All Drivers ({updates})",
                bg="#059669"
            )
        else:
            self.btn_update_all.config(
                text="🚀  Update All Drivers",
                bg="#059669"
            )

    def set_status(self, text, is_busy=False):
        self.lbl_status.config(text=text)
        if is_busy:
            self.progress.pack(side=tk.RIGHT, padx=4)
            self.progress.start(10)
        else:
            self.progress.stop()
            self.progress.pack_forget()

    # --- Scanning & Background Tasks (100% Silent) ---

    def trigger_scan(self, initial=False):
        self.btn_scan.config(state=tk.DISABLED)
        self.btn_check_all.config(state=tk.DISABLED)
        self.btn_update_all.config(state=tk.DISABLED)
        self.set_status("Scanning connected hardware devices silently...", is_busy=True)

        def worker():
            if not self.system_info:
                self.system_info = driver_scanner.get_system_info()
            devices = driver_scanner.scan_devices()
            self.root.after(0, lambda: self.on_scan_completed(devices, initial))

        threading.Thread(target=worker, daemon=True).start()

    def on_scan_completed(self, devices, initial):
        if not devices and getattr(driver_scanner, "LAST_SCAN_ERROR", ""):
            reason = driver_scanner.LAST_SCAN_ERROR
            self.set_status(f"Scan failed: {reason}", is_busy=False)
            self.btn_scan.config(state=tk.NORMAL)
            self.btn_check_all.config(state=tk.NORMAL)
            self.btn_update_all.config(state=tk.NORMAL)
            messagebox.showerror("Could not read devices", reason)
            return

        self.all_devices = devices
        self.btn_scan.config(state=tk.NORMAL)
        self.btn_check_all.config(state=tk.NORMAL)
        self.btn_update_all.config(state=tk.NORMAL)

        sys_str = f"💻 {self.system_info.get('manufacturer', '')} {self.system_info.get('model', '')}"
        if self.system_info.get("service_tag"):
            sys_str += f"  •  Service Tag: {self.system_info['service_tag']}"
        if self.system_info.get("os_version"):
            sys_str += f"  •  OS: {self.system_info['os_version']}"
        sys_str += f"  •  Arch: {driver_scanner.get_architecture()}"
        self.pc_info_label.config(text=sys_str)

        if self.system_info.get("oem_url"):
            self.btn_oem.config(text=f"🌐 {self.system_info.get('oem_name', 'OEM Support')}")

        self.apply_filters()
        self.update_kpis()
        self.set_status(f"Scan complete: {len(devices)} devices found. Ready.", is_busy=False)

        if initial:
            self.trigger_check_updates()

    CHECK_WORKERS = 8

    def _on_one_check_done(self, dev, done, total):
        self.refresh_table_row(dev)
        self.set_status(f"Checked {done}/{total}: {dev['description']}...", is_busy=True)

    def trigger_check_updates(self, devices=None):
        """Check the devices in the current tab, not just those marked primary."""
        if devices is None:
            devices = self._filtered_devices(updates_only=False)

        if not devices:
            messagebox.showinfo(
                "Driver Finder",
                f"There are no devices in '{self.current_category}' to check."
            )
            return

        self.btn_check_all.config(state=tk.DISABLED)
        self.btn_update_all.config(state=tk.DISABLED)
        scope = "all devices" if self.current_category == "📋 All Devices" else f"'{self.current_category}'"
        self.set_status(
            f"Checking manufacturer updates for {len(devices)} device(s) in {scope}...",
            is_busy=True
        )

        total = len(devices)
        self._last_check_devices = devices
        self._last_check_scope = self.current_category

        def worker():
            done = 0
            with ThreadPoolExecutor(max_workers=self.CHECK_WORKERS) as pool:
                futures = {pool.submit(driver_scanner.check_device_update, dev): dev for dev in devices}
                for future in as_completed(futures):
                    dev = futures[future]
                    done += 1
                    try:
                        future.result()
                    except Exception as exc:
                        print(f"Check failed for {dev.get('description')}: {exc}")
                    self.root.after(0, self._on_one_check_done, dev, done, total)

            self.root.after(0, self.on_check_all_completed)

        threading.Thread(target=worker, daemon=True).start()

    def on_check_all_completed(self):
        self.btn_check_all.config(state=tk.NORMAL)
        self.btn_update_all.config(state=tk.NORMAL)
        self.apply_filters()
        self.update_kpis()
        # Report on what was actually checked, not on every device on the machine.
        checked = getattr(self, "_last_check_devices", None) or self.all_devices
        scope = getattr(self, "_last_check_scope", "⭐ Key Hardware")
        scope_name = "all devices" if scope == "📋 All Devices" else scope

        updates_count = sum(1 for d in checked if d.get("catalog_status") == "Update Available")
        failed_count = sum(1 for d in checked if d.get("catalog_status") == "Check Failed")
        windows_count = sum(1 for d in checked if d.get("catalog_status") in ("Windows-Managed", "Up to Date / Windows"))

        parts = []
        if updates_count:
            parts.append(f"{updates_count} newer manufacturer driver update(s) found")
        else:
            parts.append("everything checked is current")
        if windows_count:
            parts.append(f"{windows_count} managed by Windows (updated via Windows Update, not here)")
        if failed_count:
            parts.append(f"{failed_count} could not be checked - highlighted in red")

        self.set_status(f"Check complete for {scope_name}: " + "; ".join(parts) + ".", is_busy=False)

    def action_check_current_device(self):
        if not self.selected_device:
            return
        dev = self.selected_device
        self.btn_check_single.config(state=tk.DISABLED)
        self.set_status(f"Checking update for {dev['description']}...", is_busy=True)

        def worker():
            driver_scanner.check_device_update(dev)
            self.root.after(0, lambda: self.on_single_check_completed(dev))

        threading.Thread(target=worker, daemon=True).start()

    def on_single_check_completed(self, dev):
        self.btn_check_single.config(state=tk.NORMAL)
        self.refresh_table_row(dev)
        self.show_device_details(dev)
        self.update_kpis()
        self.set_status(f"Check complete for {dev['description']}: {dev['catalog_status']}.", is_busy=False)

    # --- Driver Installation ---

    def action_update_all_drivers(self):
        updates = [d for d in self.all_devices if d.get("catalog_status") == "Update Available"]

        # Storage controllers are separated out: a bad or interrupted storage
        # driver can leave Windows unable to boot, so they need a deliberate yes.
        storage_updates = [d for d in updates if d.get("is_storage")]
        if storage_updates:
            updates = [d for d in updates if not d.get("is_storage")]
            listing = "\n".join("• " + d["description"] for d in storage_updates[:8])
            include = messagebox.askyesno(
                "Storage driver updates - read this first",
                f"{len(storage_updates)} available update(s) are storage controllers:\n\n"
                f"{listing}\n\n"
                "Replacing a storage driver can leave Windows unable to boot if the package "
                "is wrong for this machine or the install is interrupted.\n\n"
                "Continue only if you have a restore point or Windows install media.\n\n"
                "Include them in this update?",
                icon="warning"
            )
            if include:
                updates = updates + storage_updates

        
        if not updates:
            untested = [d for d in self.all_devices if d.get("is_primary") and d.get("catalog_status") == "Ready to Check"]
            if untested:
                res = messagebox.askyesno(
                    "Driver Finder",
                    "Key devices have not been checked for updates yet.\n\nWould you like to check all key devices first to find available updates?"
                )
                if res:
                    self.trigger_check_updates()
                return
            else:
                messagebox.showinfo("Driver Finder", "All devices are currently up to date! No updates needed.")
                return

        InstallationDialog(self.root, updates, self.on_installation_completed)

    def action_install_single_device(self):
        if not self.selected_device:
            return
        InstallationDialog(self.root, [self.selected_device], self.on_installation_completed)

    def on_installation_completed(self, reboot_required):
        if reboot_required:
            self.reboot_pending = True
            self.reboot_banner.pack(fill=tk.X, side=tk.TOP, before=self.btn_update_all.master.master)

        self.trigger_scan(initial=False)

    def trigger_restart_now(self):
        res = messagebox.askokcancel(
            "Restart Computer",
            "Your computer will restart in 10 seconds to finish driver installation.\n\nPlease save all open work before proceeding.\n\nClick OK to restart now."
        )
        if res:
            driver_installer.restart_computer(10)
            messagebox.showinfo(
                "Restarting",
                "Restart command issued! Windows will restart in 10 seconds.\n\nTo cancel at any time, run 'shutdown /a' in Command Prompt."
            )

    # --- Filtering & Display ---

    def select_category(self, cat):
        self.current_category = cat
        for c, btn in self.category_buttons.items():
            if c == cat:
                btn.config(bg="#2563EB", fg="#FFFFFF", font=("Segoe UI", 9, "bold"))
            else:
                btn.config(bg="#FFFFFF", fg="#475569", font=("Segoe UI", 9))
        self.apply_filters()

    def apply_filters(self):
        self.displayed_devices = self._filtered_devices()
        self.populate_tree()

    def _filtered_devices(self, category=None, search=None, updates_only=None):
        """Devices matching the current tab and search box."""
        if category is None:
            category = self.current_category
        if search is None:
            search = self.search_var.get().lower().strip()
        if updates_only is None:
            updates_only = self.filter_updates_only.get()

        filtered = []
        for d in self.all_devices:
            if self.current_category == "⭐ Key Hardware" and not d.get("is_primary"):
                continue
            elif self.current_category == "🖥️ Display" and d.get("category") != "Display & Graphics":
                continue
            elif self.current_category == "🌐 Network" and d.get("category") != "Network & Wi-Fi":
                continue
            elif self.current_category == "🔊 Audio" and "Audio" not in d.get("category", ""):
                continue
            elif self.current_category == "🔵 Bluetooth" and d.get("category") != "Bluetooth":
                continue
            elif self.current_category == "💾 Storage" and "Storage" not in d.get("category", ""):
                continue

            if updates_only and d.get("catalog_status") != "Update Available":
                continue

            if search:
                combined = f"{d['description']} {d['manufacturer']} {d['driver_provider']} {d['vendor']} {d['category']}".lower()
                if search not in combined:
                    continue

            filtered.append(d)

        return filtered

    def _row_values(self, dev):
        """One place that renders a device row, used by both refresh paths."""
        status = dev.get("catalog_status", "Ready to Check")
        if status == "Update Available":
            status_text, tag = "⬆️ UPDATE AVAILABLE", "update_available"
        elif status in ("Up to Date", "Up to Date / OEM"):
            status_text, tag = "✓ Up to Date", "up_to_date"
        elif status in ("Windows-Managed", "Up to Date / Windows"):
            status_text, tag = "🛡️ Windows-Managed", "windows_managed"
        elif status == "Check Failed":
            status_text, tag = "⚠️ Check Failed", "check_failed"
        else:
            status_text, tag = "🔍 Ready to Check", "ready"

        installed_version = str(dev.get("driver_version") or "N/A")
        installed = installed_version.upper() if installed_version.lower() == "n/a" else f"v{installed_version}"
        if dev.get("driver_date") and dev["driver_date"] != "N/A":
            installed += f" ({dev['driver_date']})"

        latest = "-"
        latest_version = str(dev.get("latest_version") or "")
        if latest_version and latest_version != "-":
            latest = "N/A" if latest_version.lower() == "n/a" else f"v{latest_version}"
            if dev.get("latest_date") and dev["latest_date"] != "-":
                latest += f" ({dev['latest_date']})"

        vendor_display = dev.get("vendor", "")
        if dev.get("driver_provider") and dev["driver_provider"] != dev.get("vendor"):
            vendor_display += f" ({dev['driver_provider']})"

        return (status_text, dev["description"], dev["category"], installed, latest, vendor_display), tag

    def populate_tree(self):
        self.tree.delete(*self.tree.get_children())

        for idx, dev in enumerate(self.displayed_devices):
            values, tag = self._row_values(dev)
            self.tree.insert("", tk.END, iid=str(idx), values=values, tags=(tag,))

    def refresh_table_row(self, dev):
        for idx, d in enumerate(self.displayed_devices):
            if d.get("instance_id") == dev.get("instance_id"):
                values, tag = self._row_values(dev)
                self.tree.item(str(idx), values=values, tags=(tag,))
                break

    def on_device_selected(self, event):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        idx = int(selected_items[0])
        if idx < len(self.displayed_devices):
            dev = self.displayed_devices[idx]
            self.selected_device = dev
            self.show_device_details(dev)

    def show_device_details(self, dev):
        status = dev.get("catalog_status", "Ready to Check")
        title_text = f"{dev['description']}   [{status.upper()}]"
        self.lbl_sel_title.config(text=title_text)

        installed_str = f"Installed: v{dev['driver_version']} ({dev.get('driver_date', 'N/A')})"
        latest_str = f"Latest: v{dev.get('latest_version', '-')} ({dev.get('latest_date', '-')})"
        hwid_str = f"Hardware ID: {dev.get('primary_hwid', 'N/A')}"
        provider_str = f"Provider: {dev.get('driver_provider', 'N/A')} ({dev.get('vendor', 'Unknown')})"
        inf_str = f"INF: {dev.get('driver_name', 'N/A')}"

        details_line = f"{installed_str}   |   {latest_str}\n{hwid_str}   |   {provider_str}   |   {inf_str}"
        if dev.get("is_storage") and status == "Update Available":
            details_line += "\n⚠️ Boot-critical device: a bad storage driver install can stop Windows from starting. This one is not included in Update All unless you confirm it."

        if dev.get("oem_note"):
            if status in ("Windows-Managed", "Up to Date / Windows"):
                details_line += f"\n🛡️ Windows-managed: {dev['oem_note']}"
            else:
                details_line += f"\n💡 Note: {dev['oem_note']}"
        self.lbl_sel_details.config(text=details_line)

        self.btn_copy_hwid.config(state=tk.NORMAL)

        windows_managed = status in ("Windows-Managed", "Up to Date / Windows")
        if windows_managed:
            # Nothing here is actionable in this app; point at where it IS handled.
            self.btn_check_single.config(state=tk.DISABLED)
            self.btn_install_single.config(state=tk.DISABLED)
            self.btn_download.config(
                state=tk.NORMAL,
                text="🛡️ Open Windows Update",
                command=self.open_windows_update,
            )
            return

        self.btn_check_single.config(state=tk.NORMAL)
        self.btn_download.config(command=self.action_open_download)

        if status == "Update Available":
            self.btn_install_single.config(state=tk.NORMAL)
        else:
            self.btn_install_single.config(state=tk.DISABLED)

        if dev.get("download_url") or dev.get("catalog_url"):
            self.btn_download.config(state=tk.NORMAL)
            if status == "Update Available":
                self.btn_download.config(text="⬇️ Download .CAB Manually")
            else:
                self.btn_download.config(text="🌐 View in Catalog / OEM")
        else:
            self.btn_download.config(state=tk.DISABLED)

        if dev.get("vendor_url"):
            self.btn_vendor.config(state=tk.NORMAL, text=f"🏢 {dev.get('vendor', 'OEM')} Site")
        else:
            self.btn_vendor.config(state=tk.DISABLED, text="🏢 Manufacturer Site")

    # --- Actions ---

    def action_open_download(self):
        if not self.selected_device:
            return
        url = self.selected_device.get("download_url") or self.selected_device.get("catalog_url")
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("Driver Finder", "No direct link available for this device.")

    def action_open_vendor(self):
        if not self.selected_device:
            return
        url = self.selected_device.get("vendor_url")
        if url:
            webbrowser.open(url)

    def action_copy_hwid(self):
        if not self.selected_device:
            return
        hwid = self.selected_device.get("primary_hwid") or ""
        if hwid:
            self.root.clipboard_clear()
            self.root.clipboard_append(hwid)
            self.set_status(f"Copied Hardware ID '{hwid}' to clipboard.", is_busy=False)

    def open_oem_portal(self):
        url = self.system_info.get("oem_url")
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("Driver Finder", "OEM support URL not found.")

    # --- Application self-update ---

    def check_app_updates(self, manual=False):
        if self._update_check_running:
            return
        self._update_check_running = True
        if manual:
            self.set_status("Checking GitHub for a newer Driver Finder release...", is_busy=True)

        def worker():
            try:
                release = updater.fetch_latest_release()
                error = None
            except Exception as exc:
                release, error = None, str(exc)
            self.root.after(0, self._on_update_checked, release, error, manual)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_checked(self, release, error, manual):
        self._update_check_running = False

        if error:
            # Never fail silently: a broken check should be diagnosable.
            try:
                import datetime as _dt
                log_path = os.path.join(paths.cache_dir(), "update.log")
                with open(log_path, "a", encoding="utf-8") as handle:
                    handle.write(f"{_dt.datetime.now().isoformat(timespec='seconds')} manual={manual} error={error}\n")
            except Exception:
                pass
            if manual:
                self.set_status(f"Update check failed: {error}", is_busy=False)
            return

        if updater.is_newer(release["version"], APP_VERSION):
            self.update_release = release
            self.show_update_banner(release)
            if manual:
                self.set_status(f"Driver Finder {release['version']} is available.", is_busy=False)
        elif manual:
            self.set_status(f"Driver Finder {APP_VERSION} is the newest version.", is_busy=False)
            messagebox.showinfo(
                "Driver Finder",
                f"You are up to date.\n\nInstalled: v{APP_VERSION}\nLatest on GitHub: v{release['version']}"
            )

    def show_update_banner(self, release):
        self.lbl_update_msg.config(
            text=f"🎉 Driver Finder {release['version']} is available (you have v{APP_VERSION})."
        )
        self.update_banner.pack(fill=tk.X, side=tk.TOP, before=self.btn_update_all.master.master)

    def on_click_dismiss_update(self):
        self.update_banner.pack_forget()

    def on_click_update_notes(self):
        release = self.update_release or {}
        if release.get("page"):
            webbrowser.open(release["page"])

    def on_click_install_update(self):
        release = self.update_release
        if not release:
            return

        if not paths.is_frozen():
            messagebox.showinfo(
                "Driver Finder",
                "This copy is running from source, so it cannot update itself.\n\n"
                "Download the installer from the release page instead."
            )
            self.on_click_update_notes()
            return

        notes = (release.get("notes") or "").strip()
        preview = notes[:900] + ("..." if len(notes) > 900 else "")
        approved = messagebox.askyesno(
            f"Install Driver Finder {release['version']}",
            f"Download and install Driver Finder {release['version']}?\n\n"
            f"Installed: v{APP_VERSION}\nAvailable: v{release['version']}\n\n"
            + (f"{preview}\n\n" if preview else "")
            + "Driver Finder closes, installs the update, then reopens."
        )
        if not approved:
            return

        self.btn_update_install.config(state=tk.DISABLED)
        self.set_status("Downloading update...", is_busy=True)

        def worker():
            try:
                installer = updater.download_installer(release, self._on_update_progress)
            except Exception as exc:
                self.root.after(0, self._on_update_download_failed, str(exc))
                return
            self.root.after(0, self._on_update_downloaded, installer)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_progress(self, downloaded, total, percent):
        mb = downloaded / 1048576
        self.root.after(0, self._set_update_status, f"Downloading update... {percent}% ({mb:.1f} MB)")

    def _set_update_status(self, text):
        self.set_status(text, is_busy=True)

    def _on_update_download_failed(self, message):
        self.btn_update_install.config(state=tk.NORMAL)
        self.set_status("Update download failed.", is_busy=False)
        messagebox.showerror("Update failed", f"Could not download the update:\n\n{message}")

    def _on_update_downloaded(self, installer_path):
        self.set_status("Installing update...", is_busy=True)
        try:
            updater.launch_installer_and_relaunch(installer_path, sys.executable)
        except Exception as exc:
            self.btn_update_install.config(state=tk.NORMAL)
            messagebox.showerror("Update failed", f"Could not start the installer:\n\n{exc}")
            return

        messagebox.showinfo(
            "Updating Driver Finder",
            "Driver Finder will close now and reopen automatically when the update finishes."
        )
        self.root.after(500, self.root.destroy)

    def open_windows_update(self):
        try:
            os.startfile("ms-settings:windowsupdate")
        except Exception:
            webbrowser.open("ms-settings:windowsupdate")

    def open_device_manager(self):
        """Open Device Manager.

        A .msc is not an executable: CreateProcess fails with error 193
        ("%1 is not a valid Win32 application"). It has to go through shell
        association or mmc.exe — and it must be shown, not launched hidden.
        """
        try:
            os.startfile("devmgmt.msc")
            return
        except Exception as shell_error:
            reason = str(shell_error)

        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        candidate = os.path.join(system_root, "System32", "devmgmt.msc")
        for command in (["mmc.exe", candidate], ["mmc.exe", "devmgmt.msc"]):
            try:
                subprocess.Popen(command)
                return
            except Exception as exc:
                reason = str(exc)

        messagebox.showerror(
            "Could not open Device Manager",
            f"Windows refused to start Device Manager.\n\n{reason}\n\n"
            "You can open it yourself with: devmgmt.msc"
        )

    def make_desktop_shortcut(self):
        success = create_shortcut.create_desktop_shortcuts(self.project_dir)
        if success:
            messagebox.showinfo(
                "Desktop Shortcut Created",
                "A Driver Finder shortcut has been created on your Desktop."
            )
        else:
            messagebox.showerror("Error", "Could not create desktop shortcut.")

    def export_report(self):
        if not self.all_devices:
            messagebox.showwarning("Export Report", "No devices scanned yet.")
            return

        now_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"Driver_Scan_Report_{now_str}.txt"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=filename,
            filetypes=[("Text files", "*.txt"), ("JSON files", "*.json")]
        )
        if not filepath:
            return

        try:
            if filepath.endswith(".json"):
                data = {
                    "system": self.system_info,
                    "scan_date": str(datetime.now()),
                    "devices": self.all_devices
                }
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write("=" * 70 + "\n")
                    f.write(f"DRIVER FINDER {APP_BUILD_INFO} - PC HARDWARE & DRIVER REPORT\n")
                    f.write("=" * 70 + "\n")
                    f.write(f"Scan Date:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Computer:      {self.system_info.get('manufacturer')} {self.system_info.get('model')}\n")
                    f.write(f"Service Tag:   {self.system_info.get('service_tag') or self.system_info.get('serial_number')}\n")
                    f.write(f"OS:            {self.system_info.get('os_version')}\n")
                    f.write(f"OEM Drivers:   {self.system_info.get('oem_url')}\n")
                    f.write("=" * 70 + "\n\n")

                    updates = [d for d in self.all_devices if d.get("catalog_status") == "Update Available"]
                    f.write(f"SUMMARY: {len(self.all_devices)} Total Devices | {len(updates)} Update(s) Available\n\n")

                    if updates:
                        f.write(">>> UPDATES AVAILABLE:\n")
                        for d in updates:
                            f.write(f" - {d['description']}\n")
                            f.write(f"   Category:  {d['category']}\n")
                            f.write(f"   Installed: v{d['driver_version']} ({d.get('driver_date')})\n")
                            f.write(f"   Latest:    v{d.get('latest_version')} ({d.get('latest_date')})\n")
                            f.write(f"   Download:  {d.get('download_url')}\n\n")

                    f.write("=" * 70 + "\n")
                    f.write("KEY HARDWARE DEVICES:\n")
                    f.write("=" * 70 + "\n")
                    for d in self.all_devices:
                        if d.get("is_primary"):
                            f.write(f"[{d['category']}] {d['description']}\n")
                            f.write(f"  Status:    {d.get('catalog_status')}\n")
                            f.write(f"  Installed: v{d['driver_version']} ({d.get('driver_date')})\n")
                            f.write(f"  Latest:    v{d.get('latest_version', '-')}\n")
                            f.write(f"  Provider:  {d.get('driver_provider')} ({d.get('vendor')})\n")
                            f.write(f"  HW ID:     {d.get('primary_hwid')}\n\n")

            messagebox.showinfo("Export Complete", f"Report saved successfully to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"Could not save report: {e}")

def main():
    enable_dpi_awareness()
    root = tk.Tk()
    apply_tk_scaling(root)
    app = DriverFinderApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
