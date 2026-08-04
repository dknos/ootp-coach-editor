#!/usr/bin/env python3
"""OOTP Coach Editor - pick a save, a team, coaches; max ratings and contracts."""
import base64, os, sys, threading, traceback, webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import ootplib as O
import theme as TH
from icon_data import ICON_PNG_B64

APP = "OOTP Coach Editor"
GITHUB = "https://github.com/dknos/ootp-coach-editor"
KOFI = "https://ko-fi.com/dknos"


def ootp_running():
    """True only if the GAME is running.

    Must not match this editor: our own executable is OOTPCoachEditor.exe, so a
    plain "ootp" substring test detects ourselves and blocks every write.
    The game is ootp<year>.exe (e.g. ootp27.exe).
    """
    if os.name != "nt":
        return False
    import re as _re
    game = _re.compile(r"^ootp\s*\d+.*\.exe$", _re.I)
    me = os.path.basename(sys.executable).lower()
    mypid = str(os.getpid())
    try:
        import subprocess, csv, io
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, creationflags=0x08000000).stdout
        for row in csv.reader(io.StringIO(out)):
            if len(row) < 2:
                continue
            name, pid = row[0].strip(), row[1].strip()
            if pid == mypid or name.lower() == me:
                continue
            if game.match(name):
                return True
    except Exception:
        return False
    return False


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP)
        self.geometry("1280x780")
        self.minsize(1040, 620)
        self.coaches = None          # O.Coaches
        self.tnames = {}             # team id -> name
        self.rows = []               # coach ids in list order
        self.mode = self._load_pref()
        self.style = ttk.Style(self)
        self.fonts = TH.fonts(self)
        self.themed = []             # plain tk widgets needing manual repaint
        try:
            self._icon = tk.PhotoImage(data=base64.b64decode(ICON_PNG_B64))
            self.iconphoto(True, self._icon)
        except Exception:
            self._icon = None
        self._build()
        self.after(100, self.scan_saves)

    # ---------------------------------------------------------------- UI
    def _pref_path(self):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "OOTPCoachEditor")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "theme.txt")

    def _load_pref(self):
        try:
            v = open(self._pref_path()).read().strip()
            return v if v in TH.THEMES else "light"
        except Exception:
            return "light"

    def toggle_theme(self):
        self.mode = "dark" if self.mode == "light" else "light"
        try:
            open(self._pref_path(), "w").write(self.mode)
        except Exception:
            pass
        self._paint()
        if self.coaches:
            self.fill_coaches()

    def _paint(self):
        t = TH.THEMES[self.mode]
        TH.apply(self.style, self, t, self.fonts)
        for w, role in self.themed:
            if role == "panel":
                w.configure(bg=t["panel"])
            elif role == "bg":
                w.configure(bg=t["bg"])
            elif role == "wordmark":
                w.configure(bg=t["bg"], fg=t["ink"])
            elif role == "sub":
                w.configure(bg=t["bg"], fg=t["ink_soft"])
            elif role == "link":
                w.configure(bg=t["bg"], fg=t["link"])
            elif role == "primary":
                w.configure(bg=t["accent"], fg=t["accent_ink"],
                            activebackground=t["ink"], activeforeground=t["panel"])
        self.btn_theme.configure(text="Night game" if self.mode == "light" else "Daylight")
        self.tree.tag_configure("odd", background=t["panel_alt"])
        self.tree.tag_configure("even", background=t["panel"])
        # done work recedes; only the exception gets colour
        self.tree.tag_configure("done", foreground=t["ink_soft"])
        self.tree.tag_configure("partial", foreground=t["partial"])

    def _eyebrow(self, parent, num, text):
        row = ttk.Frame(parent)
        ttk.Label(row, text="%s" % num, style="Eyebrow.TLabel").pack(side="left")
        ttk.Label(row, text="  " + text.upper(), style="Eyebrow.TLabel").pack(side="left")
        return row

    def _build(self):
        # ---- header -------------------------------------------------------
        head = ttk.Frame(self)
        head.pack(fill="x", padx=18, pady=(14, 0))
        if self._icon:
            self._icon_lbl = tk.Label(head, image=self._icon, bd=0)
            self._icon_lbl.pack(side="left", padx=(0, 12))
            self.themed.append((self._icon_lbl, "bg"))
        box = ttk.Frame(head); box.pack(side="left", anchor="w")
        wm = tk.Label(box, text="OOTP COACH EDITOR", font=self.fonts["wordmark"], bd=0, anchor="w")
        wm.pack(anchor="w"); self.themed.append((wm, "wordmark"))
        sub = tk.Label(box, text="Max out coach ratings and contracts in an Out of the Park 27 save",
                       font=self.fonts["small"], bd=0, anchor="w")
        sub.pack(anchor="w"); self.themed.append((sub, "sub"))

        right = ttk.Frame(head); right.pack(side="right", anchor="e")
        self.btn_theme = ttk.Button(right, text="Night game", width=12, command=self.toggle_theme)
        self.btn_theme.pack(side="right", padx=(10, 0))
        lk = ttk.Frame(right); lk.pack(side="right")
        for text, url in (("github.com/dknos", GITHUB), ("Support on Ko-fi", KOFI)):
            l = tk.Label(lk, text=text, font=self.fonts["link"], cursor="hand2", bd=0)
            l.pack(anchor="e")
            l.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            self.themed.append((l, "link"))

        ttk.Separator(self).pack(fill="x", padx=18, pady=(12, 0))

        # ---- 1. scope -----------------------------------------------------
        scope = ttk.Frame(self); scope.pack(fill="x", padx=18, pady=(12, 0))
        self._eyebrow(scope, "1", "Scope").pack(anchor="w")
        r1 = ttk.Frame(scope); r1.pack(fill="x", pady=(6, 0))
        ttk.Label(r1, text="Save").pack(side="left")
        self.cb_save = ttk.Combobox(r1, state="readonly", width=42)
        self.cb_save.pack(side="left", padx=(8, 6))
        self.cb_save.bind("<<ComboboxSelected>>", lambda e: self.load_save())
        ttk.Button(r1, text="Browse", command=self.browse).pack(side="left", padx=3)
        ttk.Button(r1, text="Rescan", command=self.scan_saves).pack(side="left", padx=3)
        self.lbl_ver = ttk.Label(r1, text="", style="Soft.TLabel")
        self.lbl_ver.pack(side="left", padx=12)

        r2 = ttk.Frame(scope); r2.pack(fill="x", pady=(8, 0))
        ttk.Label(r2, text="Organization").pack(side="left")
        self.cb_org = ttk.Combobox(r2, state="readonly", width=30)
        self.cb_org.pack(side="left", padx=(8, 16))
        self.cb_org.bind("<<ComboboxSelected>>", lambda e: self.fill_teams())
        ttk.Label(r2, text="Team").pack(side="left")
        self.cb_team = ttk.Combobox(r2, state="readonly", width=30)
        self.cb_team.pack(side="left", padx=8)
        self.cb_team.bind("<<ComboboxSelected>>", lambda e: self.fill_coaches())
        self.lbl_teamnote = ttk.Label(r2, text="", style="Soft.TLabel")
        self.lbl_teamnote.pack(side="left", padx=12)

        # ---- 2. coaches ---------------------------------------------------
        mid = ttk.Frame(self); mid.pack(fill="both", expand=True, padx=18, pady=(14, 0))
        bar = ttk.Frame(mid); bar.pack(fill="x")
        self._eyebrow(bar, "2", "Coaches").pack(side="left")
        ttk.Label(bar, text="   click a column to sort", style="Soft.TLabel").pack(side="left")
        ttk.Button(bar, text="Select none",
                   command=lambda: self.tree.selection_remove(self.tree.selection())).pack(side="right", padx=3)
        ttk.Button(bar, text="Select all",
                   command=lambda: self.tree.selection_set(self.tree.get_children())).pack(side="right", padx=3)

        wrap = ttk.Frame(mid, style="Panel.TFrame")
        wrap.pack(fill="both", expand=True, pady=(6, 0))
        cols = ("st", "id", "name", "team", "salary", "yrs", "ext", "ratings")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="extended")
        spec = (("st", 30, ""), ("id", 62, "ID"), ("name", 200, "Name"), ("team", 200, "Team"),
                ("salary", 104, "Salary"), ("yrs", 58, "Years"), ("ext", 78, "Extension"),
                ("ratings", 330, "Ratings (12 edited)"))
        for c, w, t in spec:
            self.tree.heading(c, text=t, command=lambda col=c: self.sort_by(col))
            self.tree.column(c, width=w, anchor="w", stretch=(c in ("name", "team", "ratings")))
        for c in ("id", "salary", "yrs", "ext", "ratings"):
            self.tree.column(c, anchor="e" if c in ("salary", "yrs") else "w")
        self._headings = {c: t for c, _w, t in spec}
        self._sort = (None, False)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

        # ---- 3. apply -----------------------------------------------------
        low = ttk.Frame(self); low.pack(fill="x", padx=18, pady=(14, 0))
        self._eyebrow(low, "3", "Apply").pack(anchor="w")
        opt = ttk.Frame(low); opt.pack(fill="x", pady=(6, 0))
        self.v_rat = tk.BooleanVar(value=True)
        self.v_unk = tk.BooleanVar(value=False)
        self.v_con = tk.BooleanVar(value=True)
        c1 = ttk.Frame(opt); c1.pack(side="left", anchor="n")
        ttk.Checkbutton(c1, text="Set all 12 coach ratings", variable=self.v_rat).pack(anchor="w")
        rr = ttk.Frame(c1); rr.pack(anchor="w", pady=(4, 0))
        ttk.Label(rr, text="to").pack(side="left", padx=(0, 6))
        self.cb_rat = ttk.Combobox(rr, state="readonly", width=22, values=[
            "200 - the best possible",
            "%d - the worst allowed" % O.MIN_RATING,
            "Custom..."])
        self.cb_rat.current(0); self.cb_rat.pack(side="left")
        self.cb_rat.bind("<<ComboboxSelected>>", self._rating_mode)
        self.sp_rat = ttk.Spinbox(rr, from_=O.MIN_RATING, to=O.MAX_RATING, width=5, state="disabled")
        self.sp_rat.pack(side="left", padx=(6, 0))
        self.sp_rat.delete(0, "end"); self.sp_rat.insert(0, str(O.MAX_RATING))
        ttk.Label(c1, text="the 6 manager fields are categorical, not scales - left alone",
                  style="Soft.TLabel").pack(anchor="w")
        c2 = ttk.Frame(opt); c2.pack(side="left", anchor="n", padx=(34, 0))
        ttk.Checkbutton(c2, text="Set contract", variable=self.v_con).pack(anchor="w")
        g = ttk.Frame(c2); g.pack(anchor="w", pady=(4, 0))
        ttk.Label(g, text="Years").grid(row=0, column=0, sticky="e", padx=(0, 6))
        self.sp_yrs = ttk.Spinbox(g, from_=0, to=15, width=4); self.sp_yrs.grid(row=0, column=1)
        ttk.Label(g, text="Extension").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=(4, 0))
        self.sp_ext = ttk.Spinbox(g, from_=0, to=15, width=4); self.sp_ext.grid(row=1, column=1, pady=(4, 0))
        for sp, val in ((self.sp_yrs, 10), (self.sp_ext, 10)):
            sp.delete(0, "end"); sp.insert(0, str(val))
        c3 = ttk.Frame(opt); c3.pack(side="left", anchor="n", padx=(34, 0))
        ttk.Label(c3, text="Salary").pack(anchor="w")
        self.cb_sal = ttk.Combobox(c3, state="readonly", width=27, values=[
            "Leave unchanged", "$1 (free)", "Minimum (lowest the game uses)",
            "League average", "This organization's average", "Custom..."])
        self.cb_sal.current(0); self.cb_sal.pack(anchor="w", pady=(4, 0))
        self.cb_sal.bind("<<ComboboxSelected>>",
                         lambda e: self.e_sal.configure(
                             state="normal" if self.cb_sal.current() == 5 else "disabled"))
        self.e_sal = ttk.Entry(c3, width=14, state="disabled")
        self.e_sal.pack(anchor="w", pady=(4, 0))
        ttk.Label(c3, text="$1, or multiples of $1,000 from $25,000",
                  style="Soft.TLabel").pack(anchor="w")

        act = ttk.Frame(low); act.pack(fill="x", pady=(12, 0))
        self.btn_go = tk.Button(act, text="Max out all coaches shown", bd=0,
                                relief="flat", padx=18, pady=8, cursor="hand2",
                                font=self.fonts["btn"], command=lambda: self.apply(True))
        self.btn_go.pack(side="left")
        self.themed.append((self.btn_go, "primary"))
        ttk.Button(act, text="Apply to selected only",
                   command=lambda: self.apply(False)).pack(side="left", padx=8)

        statuswrap = ttk.Frame(self, style="Panel.TFrame")
        statuswrap.pack(fill="x", side="bottom", pady=(14, 0))
        self.status = ttk.Label(statuswrap, text="", anchor="w", style="Status.TLabel")
        self.status.pack(fill="x")
        self._paint()
        self._retitle()

    def rating_target(self):
        """The value the 12 ratings will be set to."""
        i = self.cb_rat.current()
        if i == 0:
            return O.MAX_RATING
        if i == 1:
            return O.MIN_RATING
        try:
            return int(self.sp_rat.get())
        except (ValueError, AttributeError):
            return None

    def _rating_mode(self, _e=None):
        custom = self.cb_rat.current() == 2
        self.sp_rat.configure(state="normal" if custom else "disabled")
        if not custom:
            v = self.rating_target()
            self.sp_rat.configure(state="normal")
            self.sp_rat.delete(0, "end"); self.sp_rat.insert(0, str(v))
            self.sp_rat.configure(state="disabled")
        self._retitle()
        if self.coaches:
            self.fill_coaches()

    def _retitle(self):
        v = self.rating_target()
        if not self.v_rat.get():
            txt = "Apply to all coaches shown"
        elif v == O.MAX_RATING:
            txt = "Max out all coaches shown"
        elif v is not None and v <= O.MIN_RATING + 9:
            txt = "Wreck all coaches shown"
        else:
            txt = "Apply to all coaches shown"
        self.btn_go.configure(text=txt)

    def say(self, msg):
        self.status.config(text=msg)
        self.update_idletasks()

    # ------------------------------------------------------------- saves
    def scan_saves(self):
        self.saves = O.find_saves()
        self.cb_save["values"] = ["%s   [v%d]" % (l, v) for l, p, v in self.saves]
        if self.saves and not self.cb_save.get():
            pref = [i for i, s in enumerate(self.saves) if s[2] == 27]
            self.cb_save.current(pref[0] if pref else 0)
            self.load_save()
        elif not self.saves:
            self.say("No OOTP saves found - use Browse to pick a .lg folder.")

    def browse(self):
        p = filedialog.askdirectory(title="Select an OOTP .lg save folder")
        if not p:
            return
        if not os.path.exists(os.path.join(p, "coaches.dat")):
            messagebox.showerror(APP, "That folder has no coaches.dat.")
            return
        try:
            v = O.read_header(os.path.join(p, "coaches.dat"))["version"]
        except Exception as e:
            messagebox.showerror(APP, str(e)); return
        self.saves.append((os.path.basename(p), p, v))
        self.cb_save["values"] = ["%s   [v%d]" % (l, vv) for l, pp, vv in self.saves]
        self.cb_save.current(len(self.saves) - 1)
        self.load_save()

    def load_save(self):
        i = self.cb_save.current()
        if i < 0:
            return
        label, path, ver = self.saves[i]
        self.tree.delete(*self.tree.get_children())
        self.coaches = None
        if ver not in O.SUPPORTED:
            self.lbl_ver.config(text="OOTP %d - not supported" % ver, style="Bad.TLabel")
            self.say("This tool only supports OOTP 27. The OOTP %d record layout is "
                     "different (team/org fields read as garbage), so editing it would "
                     "corrupt the save." % ver)
            self.cb_org["values"] = []; self.cb_team["values"] = []
            return
        self.lbl_ver.config(text="OOTP %d" % ver, style="Ok.TLabel")
        self.say("Loading %s ..." % label)

        def work():
            try:
                c = O.Coaches(path, progress=lambda m: self.after(0, self.say, m))
                self.after(0, self._loaded, c, path)
            except Exception as e:
                traceback.print_exc()
                self.after(0, lambda: messagebox.showerror(APP, "Failed to read save:\n%s" % e))
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, c, path):
        # team names come straight out of teams.dat with the save, so they are
        # present even in a brand-new game that has generated no news yet
        self.coaches = c
        self.tnames = c.tnames
        self.fill_orgs()
        self.say("Ready - %d coaches, %d teams." % (len(c.starts), len(c.tnames)))

    def tname(self, tid):
        return self.tnames.get(tid) or "Team #%d" % tid

    # ------------------------------------------------------------ filters
    def fill_orgs(self):
        if not self.coaches:
            return
        c = self.coaches
        counts = {}
        for cid in c.starts:
            o = c.org(cid)
            if 0 < o < 5000:
                counts[o] = counts.get(o, 0) + 1
        self.orgs = [None] + sorted(counts, key=lambda o: self.tname(o))
        self.cb_org["values"] = ["All organizations"] + \
            ["%s  (%d)" % (self.tname(o), counts[o]) for o in self.orgs[1:]]
        if self.cb_org.current() < 0:
            self.cb_org.current(0)
        self.fill_teams()

    def fill_teams(self):
        if not self.coaches:
            return
        c = self.coaches
        org = self.orgs[self.cb_org.current()] if self.cb_org.current() >= 0 else None
        counts = {}
        for cid in c.starts:
            if org is not None and c.org(cid) != org:
                continue
            t = c.team(cid)
            if 0 < t < 5000:
                counts[t] = counts.get(t, 0) + 1
        self.teams = [None] + sorted(counts, key=lambda t: self.tname(t))
        self.cb_team["values"] = ["All teams in selection"] + \
            ["%s  (%d)" % (self.tname(t), counts[t]) for t in self.teams[1:]]
        self.cb_team.current(0)
        self.fill_coaches()

    @staticmethod
    def _sort_key(col, v):
        """Columns hold display strings, so parse them back to sort sensibly."""
        v = (v or "").strip()
        if col == "st":
            return {"\u25cf": 2, "\u25d0": 1}.get(v, 0)
        if col in ("id", "yrs"):
            return int(v or 0)
        if col == "salary":
            return int(v.replace("$", "").replace(",", "") or 0)
        if col == "ext":
            return int(v.rstrip("y") or 0)
        if col == "ratings":
            # "200 200 195 ..." -> compare numerically, weakest rating first
            nums = [int(x) for x in v.split() if x.isdigit()]
            return (sum(nums) / len(nums)) if nums else -1
        return v.lower()

    def sort_by(self, col):
        prev, desc = self._sort
        desc = not desc if prev == col else False
        rows = [(self.tree.set(i, col), i) for i in self.tree.get_children("")]
        try:
            rows.sort(key=lambda r: self._sort_key(col, r[0]), reverse=desc)
        except (TypeError, ValueError):
            rows.sort(key=lambda r: (r[0] or "").lower(), reverse=desc)
        for pos, (_v, item) in enumerate(rows):
            self.tree.move(item, "", pos)
        for pos, item in enumerate(self.tree.get_children("")):
            tags = [t for t in self.tree.item(item, "tags") if t in ("done", "partial")]
            self.tree.item(item, tags=tuple(tags) + ("odd" if pos % 2 else "even",))
        self._sort = (col, desc)
        for c, t in self._headings.items():
            arrow = ("  \u25bc" if desc else "  \u25b2") if c == col else ""
            self.tree.heading(c, text=t + arrow)
        # keep the id list in the order shown, so "max out all" follows the view
        self.rows = [int(self.tree.item(i)["values"][1]) for i in self.tree.get_children("")]

    def fill_coaches(self):
        self.tree.delete(*self.tree.get_children())
        self.rows = []
        if not self.coaches:
            return
        c = self.coaches
        org = self.orgs[self.cb_org.current()] if self.cb_org.current() >= 0 else None
        ti = self.cb_team.current()
        team = self.teams[ti] if 0 <= ti < len(self.teams) else None
        for cid in sorted(c.starts):
            if org is not None and c.org(cid) != org:
                continue
            if team is not None and c.team(cid) != team:
                continue
            if org is None and team is None and not (0 < c.team(cid) < 5000):
                continue
            con = c.contract(cid) or {}
            rat = c.ratings(cid)
            tail = c.tail_ratings(cid)
            vals = ([rat[i] for i in sorted(O.RATING_LABELS)] if rat else []) + \
                   list(tail.values())
            shown = " ".join(str(v) for v in vals) if vals else "unreadable"
            # the list doubles as a checklist: filled = every rating already
            # maxed, half = some done, empty = untouched
            target = self.rating_target() or O.MAX_RATING
            if vals and all(v == target for v in vals):
                mark, tag = "\u25cf", "done"
            elif any(v == target for v in vals):
                mark, tag = "\u25d0", "partial"
            else:
                mark, tag = "\u25cb", ""
            stripe = "odd" if len(self.rows) % 2 else "even"
            self.tree.insert("", "end", tags=((tag, stripe) if tag else (stripe,)), values=(
                mark, cid, c.name(cid), self.tname(c.team(cid)),
                "${:,}".format(con.get("salary", 0)), con.get("years", 0),
                "%dy" % con.get("ext_years", 0), shown))
            self.rows.append(cid)
        done = sum(1 for i in self.tree.get_children("")
                   if self.tree.set(i, "st") == "\u25cf")
        self.lbl_teamnote.config(
            text="%d coaches   %d already at %s" % (len(self.rows), done,
                                                    self.rating_target()))
        if self._sort[0]:
            col, desc = self._sort
            self._sort = (col, not desc)     # sort_by toggles; keep the direction
            self.sort_by(col)

    # -------------------------------------------------------------- apply
    def apply(self, everything):
        if not self.coaches:
            return
        if everything:
            ids = list(self.rows)
        else:
            ids = [int(self.tree.item(i)["values"][1]) for i in self.tree.selection()]
        if not ids:
            messagebox.showinfo(APP, "No coaches selected."); return
        if ootp_running():
            messagebox.showerror(APP, "OOTP is running. Close it completely first -\n"
                                      "otherwise the game will overwrite these changes\n"
                                      "the next time it saves.")
            return
        rating = self.rating_target() if self.v_rat.get() else None
        if self.v_rat.get() and (rating is None or not O.rating_ok(rating)):
            messagebox.showerror(APP, "Ratings must be a whole number between %d and %d.\n\n"
                                      "Lower than %d is not offered: the tool locates each "
                                      "coach partly by the bytes that follow the ratings, and "
                                      "very small values imitate them well enough that the "
                                      "next run would edit the wrong place."
                                 % (O.MIN_RATING, O.MAX_RATING, O.MIN_RATING))
            return
        yrs = ext = sal = None
        if self.v_con.get():
            try:
                yrs, ext = int(self.sp_yrs.get()), int(self.sp_ext.get())
            except ValueError:
                messagebox.showerror(APP, "Contract years must be numbers."); return
            mode = self.cb_sal.current()
            if mode == 1:
                sal = O.SALARY_NOMINAL
            elif mode == 2:
                sal = O.SALARY_MIN
            elif mode == 3:
                sal = self.coaches.average_salary()
            elif mode == 4:
                org = self.orgs[self.cb_org.current()] if self.cb_org.current() > 0 else None
                sal = self.coaches.average_salary(org)
            elif mode == 5:
                raw = self.e_sal.get().replace("$", "").replace(",", "").strip()
                try:
                    sal = int(raw)
                except ValueError:
                    messagebox.showerror(APP, "Custom salary must be a number."); return
            if sal is not None and not (O.salary_valid(sal) and sal):
                messagebox.showerror(APP, "Salary must be $1, or a multiple of $%s between "
                                          "$%s and $%s.\n\nBelow that range the game "
                                          "itself never goes, and the coach's record "
                                          "could not be located again afterwards."
                                     % ("{:,}".format(O.SALARY_STEP),
                                        "{:,}".format(O.SALARY_MIN),
                                        "{:,}".format(O.SALARY_MAX)))
                return
        if not messagebox.askyesno(APP, "Apply to %d coaches?\n\nA backup of coaches.dat "
                                        "is written first." % len(ids)):
            return
        try:
            # reload from disk: OOTP rewrites records at variable lengths on every
            # save, so any cached offsets are only valid until the game saves again
            self.say("Re-reading save...")
            c = O.Coaches(self.coaches.dir)
            tally = {"ok": 0, "no_contract": 0, "partial": 0, "unresolved": 0}
            for cid in ids:
                if cid in c.starts:
                    tally[c.apply(cid, max_ratings=self.v_rat.get(), years=yrs,
                                  ext_years=ext, salary=sal,
                                  include_unknown=self.v_unk.get(),
                                  rating_value=rating or O.MAX_RATING)] += 1
            c.save(backup=True)
            self.coaches = c
            self.fill_coaches()
            msg = "Done - %d coaches updated." % (tally["ok"] + tally["no_contract"] + tally["partial"])
            if tally["no_contract"]:
                msg += ("\n\n%d had no contract on file (minor-league staff). They got "
                        "the maxed ratings, but no contract was written: the game never "
                        "creates a term with no salary, and writing one would make the "
                        "record unreadable next time." % tally["no_contract"])
            if tally["partial"]:
                msg += ("\n\n%d had an unreadable ratings block; only Teach Running "
                        "and In-game Running were set for them." % tally["partial"])
            if tally["unresolved"]:
                msg += "\n\n%d could not be read and were skipped." % tally["unresolved"]
            self.say(msg.split("\n")[0] + "  Backup written next to coaches.dat.")
            messagebox.showinfo(APP, msg + "\n\nLoad the save in OOTP to see the changes.")
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror(APP, "Failed:\n%s" % e)


if __name__ == "__main__":
    App().mainloop()
