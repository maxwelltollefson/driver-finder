"""Secondary tool windows: Device Health, App Updates, Driver Backups.

These live outside the main window so the driver table keeps its focus. Each one
follows the app's visual language: dark header strip, white card, treeview of
facts, actions in a footer, and a plain-English explanation panel.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import app_updater
import device_health
import driver_backup
import driver_installer
import paths

FONT = "Segoe UI"
FONT_BOLD = "Segoe UI Semibold"


class ToolWindow(tk.Toplevel):
    TITLE = "Tool"
    SUBTITLE = ""
    GEOMETRY = "1000x700"

    def __init__(self, parent, palette):
        super().__init__(parent)
        self.palette = palette
        self.parent = parent
        self.title(self.TITLE + " - Driver Finder")
        self.geometry(self.GEOMETRY)
        self.minsize(780, 520)
        self.configure(bg=palette["bg"])

        header = tk.Frame(self, bg=palette["header"], height=78)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text=self.TITLE, font=(FONT_BOLD, 15), bg=palette["header"],
                 fg="#FFFFFF").pack(anchor="w", padx=20, pady=(13, 0))
        tk.Label(header, text=self.SUBTITLE, font=(FONT, 9), bg=palette["header"],
                 fg="#94A3B8", justify="left", wraplength=900).pack(anchor="w", padx=20)

        self.footer = tk.Frame(self, bg=palette["card"], height=56)
        self.footer.pack(fill=tk.X, side=tk.BOTTOM)
        self.footer.pack_propagate(False)
        self.footer_inner = tk.Frame(self.footer, bg=palette["card"])
        self.footer_inner.pack(fill=tk.X, padx=14, pady=11)

        self.body = tk.Frame(self, bg=palette["bg"])
        self.body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(10, 8))

        self.status_var = tk.StringVar(value="")
        self.build()

    # ---- helpers -------------------------------------------------------
    def button(self, parent, text, command, kind="ghost", state=tk.NORMAL):
        colors = {
            "primary": (self.palette["blue"], "#FFFFFF"),
            "success": (self.palette["green"], "#FFFFFF"),
            "danger": ("#B91C1C", "#FFFFFF"),
            "ghost": ("#F1F5F9", self.palette["text"]),
        }
        bg, fg = colors.get(kind, colors["ghost"])
        return tk.Button(parent, text=text, command=command, state=state, bg=bg, fg=fg,
                         font=(FONT_BOLD, 9), relief="flat", bd=0, padx=14, pady=7,
                         activebackground=bg, activeforeground=fg, cursor="hand2")

    def make_tree(self, parent, columns, widths, height=14):
        style = ttk.Style(self)
        style.configure("Tool.Treeview", font=(FONT, 9), rowheight=24)
        style.configure("Tool.Treeview.Heading", font=(FONT_BOLD, 9))
        frame = tk.Frame(parent, bg=self.palette["card"], highlightthickness=1,
                         highlightbackground=self.palette["border"])
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height,
                            style="Tool.Treeview", selectmode="browse")
        for name, width in zip(columns, widths):
            tree.heading(name, text=name)
            tree.column(name, width=width, anchor="w", stretch=(name in (columns[1],)))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        return frame, tree

    def log_box(self, parent, height=7):
        frame = tk.Frame(parent, bg=self.palette["card"], highlightthickness=1,
                         highlightbackground=self.palette["border"])
        text = tk.Text(frame, height=height, bg="#0F172A", fg="#E2E8F0", font=("Consolas", 8),
                       relief="flat", bd=0, wrap="word", state=tk.DISABLED)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=5)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        return frame, text

    @staticmethod
    def log_to(text_widget, message):
        text_widget.configure(state=tk.NORMAL)
        text_widget.insert(tk.END, str(message).rstrip() + "\n")
        text_widget.see(tk.END)
        text_widget.configure(state=tk.DISABLED)

    def build(self):
        raise NotImplementedError


class DeviceHealthWindow(ToolWindow):
    TITLE = "Device Health"
    SUBTITLE = ("Devices Windows currently reports as broken, with the meaning of the error "
                "code and the fix that applies. Disconnected hardware is not counted.")
    GEOMETRY = "1000x680"

    def build(self):
        top = tk.Frame(self.body, bg=self.palette["bg"])
        top.pack(fill=tk.X, pady=(0, 8))
        self.btn_rescan = self.button(top, "Rescan", self.refresh, "primary")
        self.btn_rescan.pack(side=tk.LEFT)
        self.button(top, "Open Device Manager", self.open_device_manager, "ghost").pack(side=tk.LEFT, padx=8)
        self.lbl_summary = tk.Label(top, text="Scanning...", font=(FONT, 9),
                                    bg=self.palette["bg"], fg=self.palette["muted"])
        self.lbl_summary.pack(side=tk.LEFT, padx=12)

        frame, self.tree = self.make_tree(
            self.body, ("Code", "Device", "Class", "Status"), (70, 420, 190, 120), height=12)
        frame.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        detail = tk.Frame(self.body, bg=self.palette["card"], highlightthickness=1,
                          highlightbackground=self.palette["border"])
        detail.pack(fill=tk.X, pady=(10, 0))
        tk.Label(detail, text="What this means", font=(FONT_BOLD, 9), bg=self.palette["card"],
                 fg=self.palette["text"]).pack(anchor="w", padx=12, pady=(8, 0))
        self.detail = tk.Label(detail, text="Select a device above to see the explanation.",
                               font=(FONT, 9), bg=self.palette["card"], fg=self.palette["muted"],
                               justify="left", anchor="w", wraplength=940)
        self.detail.pack(fill=tk.X, padx=12, pady=(2, 10))

        self.results = {}
        self.refresh()

    def refresh(self):
        self.btn_rescan.config(state=tk.DISABLED)
        self.lbl_summary.config(text="Scanning devices...")
        threading.Thread(target=self._scan, daemon=True).start()

    def _scan(self):
        result = device_health.scan_problems()
        self.after(0, lambda: self._render(result))

    def _render(self, result):
        self.btn_rescan.config(state=tk.NORMAL)
        self.tree.delete(*self.tree.get_children())
        self.results = {}
        devices = result.get("devices", [])
        for device in devices:
            item = self.tree.insert("", tk.END, values=(
                device["code"], device["description"], device["device_class"], device["status"]))
            self.results[item] = device

        ignored = result.get("ignored", 0)
        if result.get("error"):
            self.lbl_summary.config(text="Scan failed: " + result["error"][:90], fg="#B91C1C")
        elif not devices:
            self.lbl_summary.config(
                text="No problems reported. %d disconnected device(s) skipped." % ignored,
                fg=self.palette["green"])
        else:
            self.lbl_summary.config(
                text="%d device(s) need attention, %d disconnected skipped." % (len(devices), ignored),
                fg=self.palette["amber"])

        if not devices and not result.get("error"):
            self.detail.config(
                text="Nothing to fix. Windows reports every connected device as working. "
                     "Devices that were once attached but are unplugged now are excluded on purpose.")

    def on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        device = self.results.get(selection[0])
        if not device:
            return
        self.detail.config(
            text="%s\n\nWhat it means: %s\n\nWhat fixes it: %s" % (
                device["title"], device["meaning"], device["fix"]),
            fg=self.palette["text"])

    def open_device_manager(self):
        try:
            os.startfile("devmgmt.msc")
        except Exception:
            os.system("start devmgmt.msc")


class AppUpdatesWindow(ToolWindow):
    TITLE = "App Updates"
    SUBTITLE = ("Installed programs with a newer version in the winget repository. "
                "One package at a time, on your click - nothing updates behind your back.")
    GEOMETRY = "1080x740"

    def build(self):
        top = tk.Frame(self.body, bg=self.palette["bg"])
        top.pack(fill=tk.X, pady=(0, 8))
        self.btn_refresh = self.button(top, "Refresh", self.refresh, "primary")
        self.btn_refresh.pack(side=tk.LEFT)
        self.btn_update = self.button(top, "Update Selected", self.update_selected, "success",
                                      state=tk.DISABLED)
        self.btn_update.pack(side=tk.LEFT, padx=8)
        self.btn_select_all = self.button(top, "Select All", self.toggle_all, "ghost")
        self.btn_select_all.pack(side=tk.LEFT)
        self.lbl_summary = tk.Label(top, text="Loading...", font=(FONT, 9),
                                    bg=self.palette["bg"], fg=self.palette["muted"])
        self.lbl_summary.pack(side=tk.LEFT, padx=12)

        frame, self.tree = self.make_tree(
            self.body, ("", "Application", "Installed", "Available", "Package id"),
            (34, 320, 130, 130, 300), height=13)
        frame.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Button-1>", self.on_click)

        log_frame, self.log = self.log_box(self.body, height=8)
        log_frame.pack(fill=tk.BOTH, expand=False, pady=(10, 0))

        self.selected = set()
        self.updates = {}
        self.refresh()

    def refresh(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.lbl_summary.config(text="Asking winget for available updates...", fg=self.palette["muted"])
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        result = app_updater.list_upgrades()
        self.after(0, lambda: self._render(result))

    def _render(self, result):
        self.btn_refresh.config(state=tk.NORMAL)
        self.tree.delete(*self.tree.get_children())
        self.updates = {}
        self.selected = set()
        rows = result.get("updates", [])
        for row in rows:
            item = self.tree.insert("", tk.END, values=(
                "\u2610", row["name"], row["version"], row["available"], row["id"]))
            self.updates[item] = row
        if result.get("error"):
            self.lbl_summary.config(text="Failed: " + result["error"][:90], fg="#B91C1C")
            self.log_to(self.log, "winget error: " + result["error"])
        elif not rows:
            self.lbl_summary.config(text="Everything installed is current.", fg=self.palette["green"])
        else:
            self.lbl_summary.config(text="%d update(s) available." % len(rows),
                                    fg=self.palette["amber"])
        self._sync_buttons()

    def on_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        if item in self.selected:
            self.selected.discard(item)
            self.tree.set(item, "", "\u2610")
        else:
            self.selected.add(item)
            self.tree.set(item, "", "\u2611")
        self._sync_buttons()
        return "break"

    def toggle_all(self):
        if len(self.selected) == len(self.updates):
            for item in self.updates:
                self.selected.discard(item)
                self.tree.set(item, "", "\u2610")
            self.btn_select_all.config(text="Select All")
        else:
            for item in self.updates:
                self.selected.add(item)
                self.tree.set(item, "", "\u2611")
            self.btn_select_all.config(text="Clear Selection")
        self._sync_buttons()

    def _sync_buttons(self):
        states = tk.NORMAL if self.selected else tk.DISABLED
        self.btn_update.config(state=states)
        self.btn_select_all.config(
            text="Clear Selection" if len(self.selected) == len(self.updates) and self.updates else "Select All")

    def update_selected(self):
        if not self.selected:
            return
        targets = [self.updates[item] for item in self.selected]
        if not messagebox.askyesno(
                "Update %d application(s)?" % len(targets),
                "These will be upgraded now, one at a time:\n\n" +
                "\n".join("\u2022 " + t["name"] for t in targets[:12]) +
                ("\n\u2022 ...and %d more" % (len(targets) - 12) if len(targets) > 12 else "") +
                "\n\nSilent installers are used, so an app that needs a wizard may not finish."):
            return
        self.btn_update.config(state=tk.DISABLED)
        self.btn_refresh.config(state=tk.DISABLED)
        threading.Thread(target=self._run_updates, args=(targets,), daemon=True).start()

    def _run_updates(self, targets):
        ok_count = 0
        for index, target in enumerate(targets, start=1):
            self.after(0, lambda t=target, i=index: self.log_to(
                self.log, "[%d/%d] Updating %s (%s -> %s)..." % (
                    i, len(targets), t["name"], t["version"], t["available"])))
            ok, output = app_updater.upgrade(target["id"])
            if ok:
                ok_count += 1
            self.after(0, lambda t=target, o=ok, out=output: self.log_to(
                self.log, ("  done: " if o else "  FAILED: ") + (out or "")[-600:]))
        self.after(0, lambda: self._finish(ok_count, len(targets)))

    def _finish(self, ok_count, total):
        self.log_to(self.log, "Finished: %d of %d updated." % (ok_count, total))
        self.btn_refresh.config(state=tk.NORMAL)
        self.refresh()


class BackupsWindow(ToolWindow):
    TITLE = "Driver Backups & Rollback"
    SUBTITLE = ("Every install made from this app backs up the driver it replaces first. "
                "Back up everything to survive a Windows reinstall, or roll a device back.")
    GEOMETRY = "1080x740"

    def build(self):
        top = tk.Frame(self.body, bg=self.palette["bg"])
        top.pack(fill=tk.X, pady=(0, 8))
        self.btn_refresh = self.button(top, "Refresh", self.refresh, "primary")
        self.btn_refresh.pack(side=tk.LEFT)
        self.btn_backup_all = self.button(top, "Back Up All Drivers", self.backup_all, "ghost")
        self.btn_backup_all.pack(side=tk.LEFT, padx=8)
        self.btn_pack = self.button(top, "Export Offline Pack (ZIP)", self.export_pack, "ghost")
        self.btn_pack.pack(side=tk.LEFT)
        self.btn_rollback = self.button(top, "Roll Back Selected", self.rollback, "danger",
                                        state=tk.DISABLED)
        self.btn_rollback.pack(side=tk.LEFT, padx=8)
        self.button(top, "Open Folder", self.open_folder, "ghost").pack(side=tk.LEFT)

        self.lbl_summary = tk.Label(self.body, text="Loading backups...", font=(FONT, 9),
                                    bg=self.palette["bg"], fg=self.palette["muted"])
        self.lbl_summary.pack(anchor="w", pady=(0, 6))

        frame, self.tree = self.make_tree(
            self.body, ("Backed up", "Device", "Package", "Version", "Size"), (150, 380, 110, 130, 90),
            height=12)
        frame.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._sync())

        log_frame, self.log = self.log_box(self.body, height=7)
        log_frame.pack(fill=tk.BOTH, expand=False, pady=(10, 0))

        self.entries = {}
        self.manifests = []
        self.refresh()

    def refresh(self):
        self.btn_refresh.config(state=tk.DISABLED)
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        manifests = driver_backup.list_backups()
        self.after(0, lambda: self._render(manifests))

    def _render(self, manifests):
        self.btn_refresh.config(state=tk.NORMAL)
        self.tree.delete(*self.tree.get_children())
        self.entries = {}
        self.manifests = manifests
        total = 0
        for manifest in manifests:
            for entry in manifest.get("entries", []):
                folder = os.path.join(manifest.get("base", ""), entry.get("folder", ""))
                size = _folder_size(folder)
                total += size
                label = "ok" if entry.get("ok") else "failed"
                item = self.tree.insert("", tk.END, values=(
                    manifest.get("created", ""),
                    entry.get("description", "")[:60],
                    "%s (%s)" % (entry.get("inf", ""), label),
                    entry.get("version", "") or "-",
                    "%.1f MB" % (size / 1048576.0) if size else "-"))
                self.entries[item] = (manifest, entry)

        if not manifests:
            self.lbl_summary.config(
                text="No backups yet. The first driver update will create one automatically.",
                fg=self.palette["muted"])
        else:
            self.lbl_summary.config(
                text="%d backup set(s), %d device package(s), %.1f MB on disk." % (
                    len(manifests), len(self.entries), total / 1048576.0),
                fg=self.palette["text"])
        self._sync()

    def _selected_entry(self):
        """(manifest, entry) for the highlighted row, or (None, None) — selection is
        an empty tuple when nothing is highlighted, and indexing it raises."""
        selection = self.tree.selection()
        if not selection:
            return None, None
        return self.entries.get(selection[0], (None, None))

    def _sync(self):
        manifest, entry = self._selected_entry()
        usable = bool(entry and entry.get("ok") and driver_backup.backup_inf_path(manifest, entry))
        self.btn_rollback.config(state=tk.NORMAL if usable else tk.DISABLED)

    def open_folder(self):
        try:
            os.startfile(paths.backups_dir())
        except Exception as exc:
            messagebox.showerror("Could not open folder", str(exc), parent=self)

    def backup_all(self):
        if not messagebox.askyesno(
                "Back up every third-party driver?",
                "This exports every third-party driver package on this PC.\n\n"
                "It is the safe way to keep working Wi-Fi and storage drivers before a "
                "Windows reinstall.\n\n"
                "Graphics and audio packages are large - expect several GB and a few minutes.",
                parent=self):
            return
        self.btn_backup_all.config(state=tk.DISABLED)
        threading.Thread(target=self._run_backup_all, daemon=True).start()

    def _run_backup_all(self):
        self.after(0, lambda: self.log_to(self.log, "Exporting every third-party driver..."))
        destination = os.path.join(paths.backups_dir(), "full-" + _stamp())
        ok, message = driver_backup.export_all_drivers(destination)
        self.after(0, lambda: self.log_to(
            self.log, ("Exported to %s - %s" % (destination, message)) if ok
            else "Export failed: " + message))
        self.after(0, lambda: self.btn_backup_all.config(state=tk.NORMAL))
        self.refresh()

    def export_pack(self):
        target = filedialog.asksaveasfilename(
            parent=self, title="Save offline driver pack", defaultextension=".zip",
            initialfile="DriverFinder-OfflinePack.zip",
            filetypes=[("Zip archive", "*.zip")])
        if not target:
            return
        self.btn_pack.config(state=tk.DISABLED)
        threading.Thread(target=self._run_pack, args=(target,), daemon=True).start()

    def _run_pack(self, target):
        self.after(0, lambda: self.log_to(
            self.log, "Building the offline pack. This can take several minutes..."))
        ok, path, message = driver_backup.export_offline_pack(target)
        self.after(0, lambda: self.log_to(
            self.log, ("Saved: %s (%s)" % (path, message)) if ok else "Failed: " + message))
        self.after(0, lambda: self.btn_pack.config(state=tk.NORMAL))
        if ok:
            self.after(0, lambda: messagebox.showinfo(
                "Offline pack ready",
                "Saved to:\n%s\n\nOn a fresh Windows install, right-click each .inf and choose "
                "Install, or run:\npnputil /add-driver *.inf /subdirs /install" % path, parent=self))

    def rollback(self):
        manifest, entry = self._selected_entry()
        if not entry:
            return
        backup_inf = driver_backup.backup_inf_path(manifest, entry)
        if not backup_inf:
            messagebox.showerror("Cannot roll back",
                                 "The backup file for this device is missing from disk.", parent=self)
            return
        current = driver_backup.current_inf(entry.get("instance_id", ""))
        target_inf = current or entry.get("inf", "")
        if not target_inf:
            messagebox.showerror(
                "Cannot roll back",
                "Windows no longer shows this device, so there is nothing to replace.\n"
                "Reconnect the hardware and try again.", parent=self)
            return
        if not messagebox.askyesno(
                "Roll back this device?",
                "%s\n\nRemoves the package bound now (%s) and reinstalls the backup "
                "(%s, version %s).\n\nThis needs administrator approval and may ask for a reboot."
                % (entry.get("description", "Device"), target_inf,
                   os.path.basename(backup_inf), entry.get("version") or "unknown"),
                parent=self):
            return
        plan = {
            "job": "rollback_driver",
            "inf": target_inf,
            "backup_inf_path": backup_inf,
            "instance_id": entry.get("instance_id", ""),
            "device": entry.get("description", "Device"),
        }
        base = paths.downloads_dir()
        try:
            for name in ("install_status.json",):
                stale = os.path.join(base, name)
                if os.path.exists(stale):
                    os.remove(stale)
            import json
            with open(os.path.join(base, "install_plan.json"), "w", encoding="utf-8") as handle:
                json.dump(plan, handle, indent=2)
        except Exception as exc:
            messagebox.showerror("Could not prepare rollback", str(exc), parent=self)
            return
        RollbackProgress(self, base, entry.get("description", "Device"), on_done=self.refresh)


class RollbackProgress(tk.Toplevel):
    """Small progress window for the elevated rollback worker."""

    def __init__(self, parent, base_dir, device, on_done=None):
        super().__init__(parent)
        self.base = base_dir
        self.on_done = on_done
        self.finished = False
        self.title("Rolling back driver")
        self.geometry("560x260")
        self.resizable(False, False)
        self.configure(bg=parent.palette["bg"])
        self.transient(parent)

        tk.Label(self, text="Rolling back: " + device, font=(FONT_BOLD, 11),
                 bg=parent.palette["bg"], fg=parent.palette["text"]).pack(anchor="w", padx=16, pady=(14, 6))
        self.bar = ttk.Progressbar(self, length=520, mode="determinate", maximum=100)
        self.bar.pack(padx=16, pady=4)
        self.lbl = tk.Label(self, text="Waiting for administrator approval...", font=(FONT, 9),
                            bg=parent.palette["bg"], fg=parent.palette["muted"],
                            wraplength=510, justify="left")
        self.lbl.pack(anchor="w", padx=16, pady=6)
        self.btn_close = tk.Button(self, text="Close", command=self.destroy, state=tk.DISABLED,
                                   font=(FONT_BOLD, 9), relief="flat", bg="#F1F5F9", padx=14, pady=6)
        self.btn_close.pack(anchor="e", padx=16, pady=(4, 12))

        # Poll regardless of the launch result: Start-Process reports the UAC
        # decision, but the worker writes the status file either way.
        self.launch_ok = driver_installer.launch_elevated_worker(base_dir)
        if not self.launch_ok:
            self.lbl.config(text="Waiting for administrator approval... If no prompt appeared, "
                                 "close this window and try again.")
        self.after(600, self.poll)

    def poll(self):
        import json
        status_path = os.path.join(self.base, "install_status.json")
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as handle:
                    status = json.load(handle)
            except Exception:
                status = {}
            state = status.get("state", "")
            self.bar.config(value=status.get("percent", 0))
            self._saw_status = True
            line = status.get("log_line") or status.get("current_device") or ""
            self.lbl.config(text=line,
                            fg="#059669" if state == "finished" else
                               ("#B91C1C" if state == "error" else self.master.palette["muted"]))
            if state in ("finished", "error"):
                self.finished = True
                self.btn_close.config(state=tk.NORMAL)
                if self.on_done:
                    try:
                        self.on_done()
                    except Exception:
                        pass
                return
        self.after(500, self.poll)


def _stamp():
    import time
    return time.strftime("%Y%m%d-%H%M%S")


def _folder_size(path):
    total = 0
    if not path or not os.path.isdir(path):
        return 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat(follow_symlinks=False).st_size
            elif entry.is_dir(follow_symlinks=False):
                total += _folder_size(entry.path)
    except OSError:
        pass
    return total
