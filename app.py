from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import queue
import sys
import threading
import traceback
import webbrowser

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:
    print("Tkinter не установлен. Ubuntu/Debian: sudo apt install python3-tk", file=sys.stderr)
    raise

from save_format import (
    InventoryItem,
    OrphanItem,
    RawPatch,
    SaveError,
    SaveInfo,
    decompress_save,
    inspect_save,
    patch_save,
    record_hex,
)
from steam_cloud import APP_ID, CloudFile, SteamCloudError, SteamWorker, discover_helper

APP_NAME = "STALKER 2 Cloud Save Editor v0.3 EXPERIMENTAL"
APP_HOME = Path.home() / "Stalker2SaveEditor"
BACKUP_DIR = APP_HOME / "backups"
CONFIG_PATH = APP_HOME / "config.json"
RELEASES_URL = "https://github.com/Fldicoahkiin/SteamCloudFileManager/releases"


def human_size(n: int) -> str:
    v = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if v < 1024 or unit == "GB":
            return f"{v:.1f} {unit}" if unit != "B" else f"{int(v)} B"
        v /= 1024
    return str(n)


def fmt_time(ts: int) -> str:
    try:
        return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1280x900")
        self.minsize(1050, 760)
        APP_HOME.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        self.worker: SteamWorker | None = None
        self.files: list[CloudFile] = []
        self.msgq: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False

        # Analyzed source. source_kind = cloud/local.
        self.source_kind: str | None = None
        self.analysis_cloud_name: str | None = None
        self.analysis_local_path: Path | None = None
        self.analysis_sha256: str | None = None
        self.analysis_info: SaveInfo | None = None
        self.analysis_data: bytes | None = None
        self.analysis_raw: bytes | None = None

        self.inventory_by_iid: dict[str, InventoryItem] = {}
        self.orphan_by_iid: dict[str, OrphanItem] = {}

        # Staged safe + experimental edits.
        self.staged_counts: dict[int, int] = {}
        self.staged_moves: dict[int, tuple[int, int]] = {}
        self.staged_detach: dict[int, bool] = {}
        self.staged_attach: dict[int, tuple[int, int, int, int]] = {}
        self.staged_raw: list[RawPatch] = []

        cfg = self.load_config()
        helper = cfg.get("helper_path") or discover_helper() or ""
        self.helper_var = tk.StringVar(value=helper)
        self.status_var = tk.StringVar(value="Steam: не подключен")
        self.selected_var = tk.StringVar(value="Сейв не выбран")
        self.analysis_var = tk.StringVar(value="Сначала выбери cloud-save или локальный .sav")

        self.money_enabled_var = tk.BooleanVar(value=False)
        self.new_money_var = tk.StringVar(value="900000")
        self.stack_count_var = tk.StringVar(value="")
        self.stack_selected_var = tk.StringVar(value="Выбери строку в инвентаре")

        self.experimental_unlocked = tk.BooleanVar(value=False)
        self.move_x_var = tk.StringVar(value="0")
        self.move_y_var = tk.StringVar(value="0")
        self.deep_detach_var = tk.BooleanVar(value=False)
        self.orphan_x_var = tk.StringVar(value="0")
        self.orphan_y_var = tk.StringVar(value="20")
        self.orphan_w_var = tk.StringVar(value="1")
        self.orphan_h_var = tk.StringVar(value="1")
        self.raw_offset_var = tk.StringVar(value="+0x0")
        self.raw_kind_var = tk.StringVar(value="f32")
        self.raw_value_var = tk.StringVar(value="1.0")
        self.raw_note_var = tk.StringVar(value="durability candidate / test")
        self.staged_var = tk.StringVar(value="Изменений: 0")

        self.build_ui()
        self.after(100, self.poll_messages)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- config/common ----------------
    def load_config(self) -> dict:
        try:
            return json.loads(CONFIG_PATH.read_text("utf-8"))
        except Exception:
            return {}

    def save_config(self):
        CONFIG_PATH.write_text(
            json.dumps({"helper_path": self.helper_var.get().strip()}, ensure_ascii=False, indent=2),
            "utf-8",
        )

    def log(self, s: str):
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        self.logbox.configure(state="normal")
        self.logbox.insert("end", f"[{stamp}] {s}\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def set_busy(self, value: bool):
        self.busy = value
        state = "disabled" if value else "normal"
        for b in (self.analyze_btn, self.apply_btn, self.refresh_btn, self.local_btn):
            b.configure(state=state)

    def bg(self, fn):
        if self.busy:
            return
        self.set_busy(True)

        def run():
            try:
                fn()
            except Exception as exc:
                self.msgq.put(("error", f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"))
            finally:
                self.msgq.put(("busy", False))

        threading.Thread(target=run, daemon=True).start()

    def poll_messages(self):
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == "log":
                    self.log(str(payload))
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "files":
                    self.populate_saves(payload)  # type: ignore[arg-type]
                elif kind == "analysis":
                    self.apply_analysis(*payload)  # type: ignore[arg-type]
                elif kind == "busy":
                    self.set_busy(bool(payload))
                elif kind == "error":
                    text = str(payload)
                    self.log(text.splitlines()[0])
                    messagebox.showerror(APP_NAME, text)
                elif kind == "info":
                    messagebox.showinfo(APP_NAME, str(payload))
        except queue.Empty:
            pass
        self.after(100, self.poll_messages)

    # ---------------- UI ----------------
    def build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="S.T.A.L.K.E.R. 2 — Cloud Save Editor", font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text="v0.3 EXPERIMENTAL: money + stacks + move + detach + orphan attach + raw record lab + Steam Cloud upload",
        ).pack(anchor="w", pady=(2, 8))

        helper = ttk.LabelFrame(root, text="Steam Cloud backend", padding=7)
        helper.pack(fill="x")
        row = ttk.Frame(helper); row.pack(fill="x")
        ttk.Entry(row, textvariable=self.helper_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Выбрать helper…", command=self.choose_helper).pack(side="left", padx=5)
        ttk.Button(row, text="Releases", command=lambda: webbrowser.open(RELEASES_URL)).pack(side="left")
        self.refresh_btn = ttk.Button(row, text="Подключить / обновить", command=self.connect_refresh)
        self.refresh_btn.pack(side="left", padx=(5, 0))
        ttk.Label(helper, textvariable=self.status_var).pack(anchor="w", pady=(5, 0))

        paned = ttk.Panedwindow(root, orient="vertical")
        paned.pack(fill="both", expand=True, pady=(8, 0))

        saves = ttk.LabelFrame(paned, text="Источник", padding=7)
        paned.add(saves, weight=2)
        cols = ("time", "size", "persisted", "name")
        self.tree = ttk.Treeview(saves, columns=cols, show="headings", selectmode="browse", height=7)
        for col, txt, width, anc in [
            ("time", "Дата", 160, "w"), ("size", "Размер", 90, "e"),
            ("persisted", "Cloud", 70, "center"), ("name", "Файл", 700, "w")]:
            self.tree.heading(col, text=txt); self.tree.column(col, width=width, anchor=anc)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_save_select)
        controls = ttk.Frame(saves); controls.pack(fill="x", pady=(6, 0))
        ttk.Label(controls, textvariable=self.selected_var).pack(side="left", fill="x", expand=True)
        self.local_btn = ttk.Button(controls, text="Открыть локальный .sav…", command=self.open_local)
        self.local_btn.pack(side="right", padx=(5, 0))
        self.analyze_btn = ttk.Button(controls, text="Анализировать cloud-save", command=self.analyze_selected)
        self.analyze_btn.pack(side="right")

        editor = ttk.LabelFrame(paned, text="Редактор", padding=7)
        paned.add(editor, weight=6)
        ttk.Label(editor, textvariable=self.analysis_var).pack(anchor="w", pady=(0, 5))
        self.notebook = ttk.Notebook(editor); self.notebook.pack(fill="both", expand=True)

        self.build_money_tab()
        self.build_inventory_tab()
        self.build_experimental_tab()
        self.build_changes_tab()

        apply_row = ttk.Frame(editor); apply_row.pack(fill="x", pady=(8, 0))
        ttk.Label(apply_row, text="Cloud mode: fresh SHA256 check → backup → patch → round-trip → upload → persisted=true.").pack(side="left", fill="x", expand=True)
        self.apply_btn = ttk.Button(apply_row, text="BACKUP → APPLY → VERIFY → UPLOAD/EXPORT", command=self.apply_changes)
        self.apply_btn.pack(side="right")

        logf = ttk.LabelFrame(root, text="Лог", padding=5); logf.pack(fill="both", expand=False, pady=(8, 0))
        self.logbox = tk.Text(logf, height=8, wrap="word", state="disabled"); self.logbox.pack(fill="both", expand=True)
        self.log("v0.3 experimental готов. Для опасных функций включи отдельный чекбокс во вкладке «Экспериментально».")

    def build_money_tab(self):
        tab = ttk.Frame(self.notebook, padding=10); self.notebook.add(tab, text="Купоны")
        ttk.Checkbutton(tab, text="Изменить баланс при применении", variable=self.money_enabled_var).grid(row=0, column=0, sticky="w")
        ttk.Label(tab, text="Новая сумма:").grid(row=1, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(tab, textvariable=self.new_money_var, width=20).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(12, 0))
        ttk.Label(tab, text="Поле денег подтверждено на нескольких соседних реальных сейвах.").grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def build_inventory_tab(self):
        tab = ttk.Frame(self.notebook, padding=8); self.notebook.add(tab, text="Инвентарь")
        cols = ("pos", "wh", "kind", "type", "count", "weight", "handle")
        self.inv_tree = ttk.Treeview(tab, columns=cols, show="headings", selectmode="browse", height=13)
        specs = [
            ("pos","x,y",65,"center"),("wh","Размер",65,"center"),("kind","Тип",145,"w"),
            ("type","type-key",90,"w"),("count","Кол-во",120,"e"),("weight","Вес",90,"e"),("handle","Handle",130,"w")]
        for c,t,w,a in specs:
            self.inv_tree.heading(c,text=t); self.inv_tree.column(c,width=w,anchor=a)
        self.inv_tree.pack(fill="both", expand=True)
        self.inv_tree.tag_configure("readonly", foreground="#777777")
        self.inv_tree.tag_configure("staged", background="#fff2a8")
        self.inv_tree.bind("<<TreeviewSelect>>", self.on_inventory_select)
        ctl = ttk.Frame(tab); ctl.pack(fill="x", pady=(7,0))
        ttk.Label(ctl, textvariable=self.stack_selected_var).pack(side="left", fill="x", expand=True)
        ttk.Label(ctl, text="Новое кол-во:").pack(side="left", padx=(8,4))
        ttk.Entry(ctl, textvariable=self.stack_count_var, width=10).pack(side="left")
        ttk.Button(ctl, text="Поставить stack", command=self.stage_stack_change).pack(side="left", padx=5)
        ttk.Button(ctl, text="Снять stack", command=self.unstage_stack_change).pack(side="left")
        ttk.Label(tab, text="Safe path: count>1 + cached total weight. Count=1/weapon/armor остаются read-only для stack editor.", wraplength=1100).pack(anchor="w", pady=(4,0))

    def build_experimental_tab(self):
        tab = ttk.Frame(self.notebook, padding=8); self.notebook.add(tab, text="Экспериментально")
        ttk.Checkbutton(
            tab,
            text="Я понимаю: move/detach/attach/raw patch НЕ подтверждены самой игрой и могут сломать сейв. Backup обязателен.",
            variable=self.experimental_unlocked,
        ).pack(anchor="w")

        ops = ttk.LabelFrame(tab, text="Selected inventory object", padding=6); ops.pack(fill="x", pady=(6,0))
        row = ttk.Frame(ops); row.pack(fill="x")
        ttk.Label(row,text="Move x:").pack(side="left"); ttk.Entry(row,textvariable=self.move_x_var,width=5).pack(side="left")
        ttk.Label(row,text=" y:").pack(side="left"); ttk.Entry(row,textvariable=self.move_y_var,width=5).pack(side="left")
        ttk.Button(row,text="Stage move",command=self.stage_move).pack(side="left",padx=6)
        ttk.Checkbutton(row,text="Deep detach (also remove owned-handle)",variable=self.deep_detach_var).pack(side="left",padx=8)
        ttk.Button(row,text="Stage DETACH",command=self.stage_detach).pack(side="left")
        ttk.Button(row,text="Clear selected experimental",command=self.clear_selected_experimental).pack(side="right")

        split = ttk.Panedwindow(tab, orient="horizontal"); split.pack(fill="both", expand=True, pady=(6,0))
        left = ttk.LabelFrame(split,text="Owned handles без grid cells (orphans/equipped/hidden)",padding=5); split.add(left,weight=2)
        ocols=("kind","type","count","pos","handle")
        self.orphan_tree=ttk.Treeview(left,columns=ocols,show="headings",height=8)
        for c,t,w in [("kind","Тип",120),("type","type-key",80),("count","count",70),("pos","record x,y",85),("handle","handle",120)]:
            self.orphan_tree.heading(c,text=t); self.orphan_tree.column(c,width=w)
        self.orphan_tree.pack(fill="both",expand=True)
        ar=ttk.Frame(left); ar.pack(fill="x",pady=(5,0))
        for label,var,width in [("x",self.orphan_x_var,4),("y",self.orphan_y_var,4),("w",self.orphan_w_var,3),("h",self.orphan_h_var,3)]:
            ttk.Label(ar,text=label+":").pack(side="left"); ttk.Entry(ar,textvariable=var,width=width).pack(side="left")
        ttk.Button(ar,text="Stage ATTACH orphan",command=self.stage_attach).pack(side="left",padx=6)

        right = ttk.LabelFrame(split,text="Raw record lab",padding=5); split.add(right,weight=3)
        self.hexbox=tk.Text(right,height=10,wrap="none",font=("TkFixedFont",9)); self.hexbox.pack(fill="both",expand=True)
        rr=ttk.Frame(right); rr.pack(fill="x",pady=(5,0))
        ttk.Label(rr,text="offset:").pack(side="left"); ttk.Entry(rr,textvariable=self.raw_offset_var,width=12).pack(side="left")
        ttk.Label(rr,text=" type:").pack(side="left")
        ttk.Combobox(rr,textvariable=self.raw_kind_var,values=("u8","u16","u32","i32","f32","hex"),width=6,state="readonly").pack(side="left")
        ttk.Label(rr,text=" value:").pack(side="left"); ttk.Entry(rr,textvariable=self.raw_value_var,width=16).pack(side="left")
        ttk.Button(rr,text="Stage RAW patch",command=self.stage_raw_patch).pack(side="left",padx=6)
        ttk.Entry(right,textvariable=self.raw_note_var).pack(fill="x",pady=(4,0))
        ttk.Label(right,text="Offset '+0xNN' = relative to selected object record; '0xNN' = absolute raw payload offset. Use diff-record CLI to hunt durability.",wraplength=600).pack(anchor="w",pady=(4,0))

    def build_changes_tab(self):
        tab=ttk.Frame(self.notebook,padding=8); self.notebook.add(tab,text="Изменения")
        ttk.Label(tab,textvariable=self.staged_var).pack(anchor="w")
        self.changes_box=tk.Text(tab,wrap="word",state="disabled"); self.changes_box.pack(fill="both",expand=True,pady=(5,0))
        ttk.Button(tab,text="Сбросить ВСЕ staged changes",command=self.clear_all_staged).pack(anchor="e",pady=(5,0))

    # ---------------- Steam/source ----------------
    def choose_helper(self):
        p = filedialog.askopenfilename(title="Выбрать SteamCloudFileManager / AppImage")
        if p:
            self.helper_var.set(p); self.save_config()

    def get_worker(self) -> SteamWorker:
        helper = self.helper_var.get().strip()
        if not helper:
            raise SteamCloudError("Укажи SteamCloudFileManager binary/AppImage")
        if self.worker:
            self.worker.close()
        self.worker = SteamWorker(helper, log=lambda s: self.msgq.put(("log", s)))
        self.worker.start(); self.worker.connect(APP_ID); self.save_config(); return self.worker

    def ensure_connection(self) -> SteamWorker:
        if self.worker and self.worker.proc and self.worker.proc.poll() is None:
            return self.worker
        return self.get_worker()

    def connect_refresh(self):
        def job():
            self.msgq.put(("status","Подключение к Steamworks…"))
            w=self.get_worker(); fs=w.list_files(); self.files=fs
            self.msgq.put(("files",fs)); self.msgq.put(("status",f"Steam Cloud: подключено · {len(fs)} Data/*.sav"))
        self.bg(job)

    def populate_saves(self, files: list[CloudFile]):
        for x in self.tree.get_children(): self.tree.delete(x)
        for idx,f in enumerate(files):
            self.tree.insert("","end",iid=str(idx),values=(fmt_time(f.timestamp),human_size(f.size),"OK" if f.is_persisted else "WAIT",Path(f.name).name))

    def selected_cloud(self) -> CloudFile:
        sel=self.tree.selection()
        if not sel: raise SteamCloudError("Сначала выбери сейв в таблице")
        return self.files[int(sel[0])]

    def on_save_select(self,_evt=None):
        try:
            f=self.selected_cloud(); self.selected_var.set(Path(f.name).name)
        except Exception: pass

    def analyze_selected(self):
        try: cloud=self.selected_cloud()
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc)); return
        def job():
            w=self.ensure_connection(); self.msgq.put(("log",f"Скачиваю: {cloud.name}"))
            data=w.read_file(cloud.name); info=inspect_save(data,with_inventory=True); raw=decompress_save(data)
            self.msgq.put(("analysis",("cloud",cloud.name,None,info,data,raw)))
        self.bg(job)

    def open_local(self):
        p=filedialog.askopenfilename(title="Открыть STALKER 2 .sav",filetypes=[("STALKER 2 save","*.sav"),("All files","*")])
        if not p: return
        path=Path(p)
        def job():
            data=path.read_bytes(); info=inspect_save(data,with_inventory=True); raw=decompress_save(data)
            self.msgq.put(("analysis",("local",None,path,info,data,raw)))
        self.bg(job)

    # ---------------- Analysis/staging ----------------
    def apply_analysis(self, source_kind: str, cloud_name: str | None, local_path: Path | None, info: SaveInfo, data: bytes, raw: bytes):
        self.source_kind=source_kind; self.analysis_cloud_name=cloud_name; self.analysis_local_path=local_path
        self.analysis_sha256=info.sha256; self.analysis_info=info; self.analysis_data=data; self.analysis_raw=raw
        self.clear_all_staged(refresh=False)
        src=Path(cloud_name).name if cloud_name else str(local_path)
        self.analysis_var.set(f"{src} · money {fmt_int(info.money or 0)} · inventory {len(info.inventory)} · cells {info.grid_cell_count} · orphans {len(info.orphans)} · SHA {info.sha256[:12]}…")
        self.populate_inventory(info.inventory); self.populate_orphans(info.orphans); self.refresh_changes()
        self.log(f"Analysis OK: money={info.money}, inventory={len(info.inventory)}, owned={len(info.owned_handles)}, grid-cells={info.grid_cell_count}, orphans={len(info.orphans)}")

    def populate_inventory(self, items: tuple[InventoryItem,...]):
        for iid in self.inv_tree.get_children(): self.inv_tree.delete(iid)
        self.inventory_by_iid.clear()
        for idx,item in enumerate(items):
            iid=str(idx); self.inventory_by_iid[iid]=item
            staged = item.handle in self.staged_counts or item.handle in self.staged_moves or item.handle in self.staged_detach
            count_text=f"{item.count} → {self.staged_counts[item.handle]}" if item.handle in self.staged_counts else str(item.count)
            tags=("staged",) if staged else (() if item.editable_count else ("readonly",))
            self.inv_tree.insert("","end",iid=iid,values=(item.position,item.size_text,item.category,item.type_key,count_text,f"{item.total_weight:.3f}",item.handle_hex),tags=tags)

    def populate_orphans(self, items: tuple[OrphanItem,...]):
        for iid in self.orphan_tree.get_children(): self.orphan_tree.delete(iid)
        self.orphan_by_iid.clear()
        for idx,o in enumerate(items):
            iid=str(idx); self.orphan_by_iid[iid]=o
            self.orphan_tree.insert("","end",iid=iid,values=(o.category,o.type_key,o.count,f"{o.x},{o.y}",o.handle_hex))

    def selected_inventory_item(self) -> InventoryItem:
        sel=self.inv_tree.selection()
        if not sel: raise SaveError("Выбери предмет в таблице")
        return self.inventory_by_iid[sel[0]]

    def on_inventory_select(self,_evt=None):
        try:
            item=self.selected_inventory_item(); self.stack_count_var.set(str(self.staged_counts.get(item.handle,item.count)))
            self.move_x_var.set(str(self.staged_moves.get(item.handle,(item.x,item.y))[0])); self.move_y_var.set(str(self.staged_moves.get(item.handle,(item.x,item.y))[1]))
            self.stack_selected_var.set(f"{item.category} {item.handle_hex} @ {item.position} {item.size_text} count={item.count} type-key={item.type_key}")
            self.show_record_hex(item)
        except Exception: pass

    def show_record_hex(self,item:InventoryItem):
        if not self.analysis_raw: return
        try:
            base,blob=record_hex(self.analysis_raw,item.handle,limit=768)
            lines=[f"record base = 0x{base:X}; guessed window = {len(blob)} bytes; handle={item.handle_hex}; type-key={item.type_key}"]
            for i in range(0,len(blob),16):
                lines.append(f"+0x{i:04X}  " + blob[i:i+16].hex(" "))
            self.hexbox.delete("1.0","end"); self.hexbox.insert("1.0","\n".join(lines))
        except Exception as exc:
            self.hexbox.delete("1.0","end"); self.hexbox.insert("1.0",str(exc))

    def require_experimental(self):
        if not self.experimental_unlocked.get():
            raise SaveError("Сначала включи чекбокс подтверждения риска во вкладке «Экспериментально»")

    def stage_stack_change(self):
        try:
            item=self.selected_inventory_item()
            if not item.editable_count: raise SaveError("Safe stack editor разрешён только для подтверждённых stackable count>1")
            v=int(self.stack_count_var.get().replace(" ",""),0)
            if not (1<=v<=1_000_000): raise ValueError
            if v==item.count: self.staged_counts.pop(item.handle,None)
            else: self.staged_counts[item.handle]=v
            self.refresh_staged_ui(item.handle)
        except ValueError: messagebox.showerror(APP_NAME,"Количество 1..1 000 000")
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc))

    def unstage_stack_change(self):
        try:
            item=self.selected_inventory_item(); self.staged_counts.pop(item.handle,None); self.refresh_staged_ui(item.handle)
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc))

    def stage_move(self):
        try:
            self.require_experimental(); item=self.selected_inventory_item(); x=int(self.move_x_var.get(),0); y=int(self.move_y_var.get(),0)
            self.staged_moves[item.handle]=(x,y); self.refresh_staged_ui(item.handle)
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc))

    def stage_detach(self):
        try:
            self.require_experimental(); item=self.selected_inventory_item()
            self.staged_detach[item.handle]=bool(self.deep_detach_var.get()); self.refresh_staged_ui(item.handle)
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc))

    def clear_selected_experimental(self):
        try:
            item=self.selected_inventory_item(); self.staged_moves.pop(item.handle,None); self.staged_detach.pop(item.handle,None); self.refresh_staged_ui(item.handle)
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc))

    def stage_attach(self):
        try:
            self.require_experimental(); sel=self.orphan_tree.selection()
            if not sel: raise SaveError("Выбери orphan/owned handle")
            o=self.orphan_by_iid[sel[0]]
            vals=tuple(int(v.get(),0) for v in (self.orphan_x_var,self.orphan_y_var,self.orphan_w_var,self.orphan_h_var))
            self.staged_attach[o.handle]=vals  # type: ignore[assignment]
            self.refresh_changes()
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc))

    def stage_raw_patch(self):
        try:
            self.require_experimental(); s=self.raw_offset_var.get().strip()
            if s.startswith("+"):
                item=self.selected_inventory_item(); off=item.record_offset+int(s[1:],0)
            else: off=int(s,0)
            p=RawPatch(off,self.raw_kind_var.get(),self.raw_value_var.get(),self.raw_note_var.get())
            # validate encoding by running a local no-op-ish preflight through patch_save only at apply time;
            # here we at least prevent negative offsets.
            if off<0: raise SaveError("Отрицательный raw offset")
            self.staged_raw.append(p); self.refresh_changes()
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc))

    def refresh_staged_ui(self, handle:int|None=None):
        if self.analysis_info: self.populate_inventory(self.analysis_info.inventory)
        if handle is not None:
            for iid,it in self.inventory_by_iid.items():
                if it.handle==handle:
                    self.inv_tree.selection_set(iid); self.inv_tree.see(iid); break
        self.refresh_changes()

    def clear_all_staged(self, refresh: bool=True):
        self.staged_counts.clear(); self.staged_moves.clear(); self.staged_detach.clear(); self.staged_attach.clear(); self.staged_raw.clear(); self.money_enabled_var.set(False)
        if refresh and self.analysis_info:
            self.populate_inventory(self.analysis_info.inventory); self.refresh_changes()

    def refresh_changes(self):
        lines=[]
        if self.money_enabled_var.get(): lines.append(f"MONEY -> {self.new_money_var.get()}")
        for h,v in self.staged_counts.items(): lines.append(f"STACK 0x{h:08X} -> {v}")
        for h,(x,y) in self.staged_moves.items(): lines.append(f"EXPERIMENTAL MOVE 0x{h:08X} -> {x},{y}")
        for h,deep in self.staged_detach.items(): lines.append(f"EXPERIMENTAL DETACH 0x{h:08X} deep={deep}")
        for h,(x,y,w,hh) in self.staged_attach.items(): lines.append(f"EXPERIMENTAL ATTACH orphan 0x{h:08X} -> {x},{y} {w}x{hh}")
        for p in self.staged_raw: lines.append(f"RAW 0x{p.offset:X} {p.kind}={p.value} # {p.note}")
        self.staged_var.set(f"Staged changes: {len(lines)}")
        self.changes_box.configure(state="normal"); self.changes_box.delete("1.0","end"); self.changes_box.insert("1.0","\n".join(lines) if lines else "Нет staged changes"); self.changes_box.configure(state="disabled")

    def parse_new_money(self)->int:
        try: v=int(self.new_money_var.get().replace(" ",""),0)
        except Exception: raise SaveError("Новые купоны должны быть целым числом")
        if not (0<=v<=2_000_000_000): raise SaveError("Сумма 0..2 000 000 000")
        return v

    def backup_path(self, stem: str, suffix: str)->Path:
        ts=dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        return BACKUP_DIR/f"{stem}_{ts}_{suffix}.sav"

    def build_patch_args(self):
        money=self.parse_new_money() if self.money_enabled_var.get() else None
        if money is None and not (self.staged_counts or self.staged_moves or self.staged_detach or self.staged_attach or self.staged_raw):
            raise SaveError("Нет изменений")
        if (self.staged_moves or self.staged_detach or self.staged_attach or self.staged_raw) and not self.experimental_unlocked.get():
            raise SaveError("Есть experimental changes, но risk checkbox выключен")
        return money

    # ---------------- Apply/export/upload ----------------
    def apply_changes(self):
        try:
            if not self.analysis_info or not self.analysis_data or not self.analysis_sha256: raise SaveError("Сначала проанализируй сейв")
            money=self.build_patch_args(); self.refresh_changes()
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc)); return

        experimental=bool(self.staged_moves or self.staged_detach or self.staged_attach or self.staged_raw)
        warning="\n\nВНИМАНИЕ: есть EXPERIMENTAL structural/raw edits." if experimental else ""
        if not messagebox.askyesno(APP_NAME,"Будет создан backup и выполнен full round-trip check."+warning+"\nПродолжить?"):
            return

        if self.source_kind=="local":
            default=(self.analysis_local_path.stem+"_EDITED.sav") if self.analysis_local_path else "edited.sav"
            out=filedialog.asksaveasfilename(title="Сохранить edited .sav",defaultextension=".sav",initialfile=default,filetypes=[("STALKER 2 save","*.sav")])
            if not out: return
            self.apply_local(Path(out),money)
        elif self.source_kind=="cloud":
            self.apply_cloud(money)
        else:
            messagebox.showerror(APP_NAME,"Неизвестный source mode")

    def do_patch(self, original:bytes, money:int|None):
        return patch_save(
            original,
            new_money=money,
            stack_counts=dict(self.staged_counts),
            moves=dict(self.staged_moves),
            detach=dict(self.staged_detach),
            attach_orphans=dict(self.staged_attach),
            raw_patches=tuple(self.staged_raw),
        )

    def apply_local(self,out:Path,money:int|None):
        original=self.analysis_data; assert original is not None
        stem=(self.analysis_local_path.stem if self.analysis_local_path else "local")
        def job():
            bp=self.backup_path(stem,"ORIGINAL"); bp.write_bytes(original); self.msgq.put(("log",f"Backup: {bp}"))
            r=self.do_patch(original,money); out.write_bytes(r.data); after=inspect_save(r.data,with_inventory=True)
            self.msgq.put(("log",f"Local export OK: {out} ({human_size(len(r.data))})"))
            self.msgq.put(("analysis",("local",None,out,after,r.data,decompress_save(r.data))))
            self.msgq.put(("info",f"Готово.\nOutput: {out}\nBackup: {bp}\nCRC/Kraken round-trip: OK"))
        self.bg(job)

    def apply_cloud(self,money:int|None):
        try:
            cloud=self.selected_cloud()
            if cloud.name!=self.analysis_cloud_name: raise SaveError("Выбранный cloud slot не совпадает с анализированным")
        except Exception as exc: messagebox.showerror(APP_NAME,str(exc)); return
        analyzed_sha=self.analysis_sha256; assert analyzed_sha
        def job():
            w=self.ensure_connection(); self.msgq.put(("log",f"1/8 fresh download {cloud.name}"))
            original=w.read_file(cloud.name); fresh=hashlib.sha256(original).hexdigest()
            if fresh!=analyzed_sha: raise SaveError("Cloud save изменился после анализа. Re-analyze; upload отменён.")
            bp=self.backup_path(Path(cloud.name).stem,"ORIGINAL"); bp.write_bytes(original); self.msgq.put(("log",f"2/8 backup {bp}"))
            before=inspect_save(original,with_inventory=True); self.msgq.put(("log",f"3/8 source verify OK money={before.money}"))
            r=self.do_patch(original,money); edited=r.data; after=inspect_save(edited,with_inventory=True)
            ep=self.backup_path(Path(cloud.name).stem,"EDITED"); ep.write_bytes(edited); self.msgq.put(("log",f"4/8 patch+roundtrip OK; recovery {ep}"))
            self.msgq.put(("log","5/8 WriteFile same Steam RemoteStorage path")); w.write_file(cloud.name,edited); w.sync()
            self.msgq.put(("log","6/8 wait persisted=true"))
            if not w.wait_persisted(cloud.name,len(edited),timeout=180): raise SteamCloudError("WriteFile sent, but persisted=true not confirmed in 180s. Do NOT start GFN yet.")
            fs=w.list_files(); self.files=fs; self.msgq.put(("files",fs)); self.msgq.put(("log","7/8 cloud persisted=true"))
            fresh2=w.read_file(cloud.name); check=inspect_save(fresh2,with_inventory=True)
            if hashlib.sha256(fresh2).hexdigest()!=hashlib.sha256(edited).hexdigest(): raise SteamCloudError("8/8 cloud read-back SHA mismatch")
            self.msgq.put(("log","8/8 cloud read-back SHA/CRC/Kraken OK"))
            self.msgq.put(("analysis",("cloud",cloud.name,None,check,fresh2,decompress_save(fresh2))))
            self.msgq.put(("info",f"Cloud upload verified. persisted=true + read-back SHA OK.\nBackup: {bp}\nEdited recovery: {ep}"))
        self.bg(job)

    def on_close(self):
        try:
            self.save_config()
            if self.worker: self.worker.close()
        finally: self.destroy()


if __name__ == "__main__":
    App().mainloop()
