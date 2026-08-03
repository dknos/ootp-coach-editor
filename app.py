#!/usr/bin/env python3
"""OOTP Coach Editor - pick a save, a team, coaches; max ratings and contracts."""
import base64, os, sys, threading, traceback, webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import ootplib as O
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
        try:
            self._icon = tk.PhotoImage(data=base64.b64decode(ICON_PNG_B64))
            self.iconphoto(True, self._icon)
        except Exception:
            self._icon = None
        self._build()
        self.after(100, self.scan_saves)

    # ---------------------------------------------------------------- UI
    def _build(self):
        pad = dict(padx=6, pady=4)

        head = ttk.Frame(self)
        head.pack(fill="x", padx=6, pady=(6, 0))
        if self._icon:
            ttk.Label(head, image=self._icon).pack(side="left", padx=(0, 10))
        box = ttk.Frame(head)
        box.pack(side="left", anchor="w")
        tk.Label(box, text=APP, font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(box, text="Max out coach ratings and contracts in an OOTP 27 save",
                 foreground="#666").pack(anchor="w")
        links = ttk.Frame(head)
        links.pack(side="right", anchor="e")
        for text, url, colour in (("github.com/dknos", GITHUB, "#0a58ca"),
                                  ("Support on Ko-fi", KOFI, "#c2410c")):
            lbl = tk.Label(links, text=text, foreground=colour, cursor="hand2",
                           font=("Segoe UI", 9, "underline"))
            lbl.pack(anchor="e")
            lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=6, pady=(6, 0))

        top = ttk.LabelFrame(self, text="1. Save game")
        top.pack(fill="x", **pad)
        self.cb_save = ttk.Combobox(top, state="readonly", width=60)
        self.cb_save.pack(side="left", padx=6, pady=6)
        self.cb_save.bind("<<ComboboxSelected>>", lambda e: self.load_save())
        ttk.Button(top, text="Browse...", command=self.browse).pack(side="left", padx=4)
        ttk.Button(top, text="Rescan", command=self.scan_saves).pack(side="left", padx=4)
        self.lbl_ver = ttk.Label(top, text="")
        self.lbl_ver.pack(side="left", padx=12)

        mid = ttk.LabelFrame(self, text="2. Team")
        mid.pack(fill="x", **pad)
        ttk.Label(mid, text="Organization:").pack(side="left", padx=(6, 2))
        self.cb_org = ttk.Combobox(mid, state="readonly", width=32)
        self.cb_org.pack(side="left", padx=2, pady=6)
        self.cb_org.bind("<<ComboboxSelected>>", lambda e: self.fill_teams())
        ttk.Label(mid, text="Team:").pack(side="left", padx=(12, 2))
        self.cb_team = ttk.Combobox(mid, state="readonly", width=32)
        self.cb_team.pack(side="left", padx=2)
        self.cb_team.bind("<<ComboboxSelected>>", lambda e: self.fill_coaches())
        self.lbl_teamnote = ttk.Label(mid, text="")
        self.lbl_teamnote.pack(side="left", padx=10)

        lst = ttk.LabelFrame(self, text="3. Coaches  (select rows, or use Max Out All)")
        lst.pack(fill="both", expand=True, **pad)
        cols = ("id", "name", "team", "salary", "yrs", "ext", "ratings")
        self.tree = ttk.Treeview(lst, columns=cols, show="headings", selectmode="extended")
        for c, w, t in (("id", 60, "ID"), ("name", 210, "Name"), ("team", 190, "Team"),
                        ("salary", 100, "Salary"), ("yrs", 55, "Years"),
                        ("ext", 90, "Extension"), ("ratings", 320, "Ratings (12 edited)")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        vs = ttk.Scrollbar(lst, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

        btn = ttk.Frame(self)
        btn.pack(fill="x", **pad)
        ttk.Button(btn, text="Select all", command=lambda: self.tree.selection_set(self.tree.get_children())).pack(side="left", padx=3)
        ttk.Button(btn, text="Select none", command=lambda: self.tree.selection_remove(self.tree.selection())).pack(side="left", padx=3)

        opt = ttk.LabelFrame(self, text="4. What to apply")
        opt.pack(fill="x", **pad)
        self.v_rat = tk.BooleanVar(value=True)
        self.v_unk = tk.BooleanVar(value=False)
        self.v_con = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Max all 12 coach ratings (=200)", variable=self.v_rat).grid(row=0, column=0, sticky="w", padx=6, pady=2)
        ttk.Label(opt, text="(the 6 manager fields are categorical, not scales - left alone)",
                  foreground="#666").grid(row=1, column=0, sticky="w", padx=6)
        ttk.Checkbutton(opt, text="Set contract", variable=self.v_con).grid(row=0, column=1, sticky="w", padx=16)
        ttk.Label(opt, text="Years:").grid(row=0, column=2, sticky="e")
        self.sp_yrs = tk.Spinbox(opt, from_=0, to=15, width=5)
        self.sp_yrs.grid(row=0, column=3, sticky="w", padx=4)
        ttk.Label(opt, text="Extension years:").grid(row=1, column=2, sticky="e")
        self.sp_ext = tk.Spinbox(opt, from_=0, to=15, width=5)
        self.sp_ext.grid(row=1, column=3, sticky="w", padx=4)
        ttk.Label(opt, text="Salary:").grid(row=0, column=4, sticky="e", padx=(16, 2))
        self.cb_sal = ttk.Combobox(opt, state="readonly", width=26, values=[
            "Leave unchanged",
            "$1 (free)",
            "Minimum (lowest the game uses)",
            "League average",
            "This organization's average",
            "Custom..."])
        self.cb_sal.current(0)
        self.cb_sal.grid(row=0, column=5, sticky="w")
        self.cb_sal.bind("<<ComboboxSelected>>",
                         lambda e: self.e_sal.configure(
                             state="normal" if self.cb_sal.current() == 5 else "disabled"))
        self.e_sal = ttk.Entry(opt, width=12, state="disabled")
        self.e_sal.grid(row=1, column=5, sticky="w", pady=2)
        ttk.Label(opt, text="($1, or multiples of $1,000 from $25,000)",
                  foreground="#666").grid(row=2, column=4, columnspan=2, sticky="w", padx=4)
        for sp, val in ((self.sp_yrs, 10), (self.sp_ext, 10)):
            sp.delete(0, "end"); sp.insert(0, str(val))

        act = ttk.Frame(self)
        act.pack(fill="x", **pad)
        ttk.Button(act, text="Apply to selected", command=lambda: self.apply(False)).pack(side="left", padx=4)
        b = ttk.Button(act, text="MAX OUT ALL COACHES (shown)", command=lambda: self.apply(True))
        b.pack(side="left", padx=4)
        self.status = ttk.Label(self, text="", anchor="w", relief="sunken")
        self.status.pack(fill="x", side="bottom")

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
            self.lbl_ver.config(text="OOTP %d - NOT SUPPORTED" % ver, foreground="#b00")
            self.say("This tool only supports OOTP 27. The OOTP %d record layout is "
                     "different (team/org fields read as garbage), so editing it would "
                     "corrupt the save." % ver)
            self.cb_org["values"] = []; self.cb_team["values"] = []
            return
        self.lbl_ver.config(text="OOTP %d" % ver, foreground="#070")
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
            shown = "-" if not rat else " ".join(
                [str(rat[i]) for i in sorted(O.RATING_LABELS)] +
                [str(v) for v in tail.values()])
            self.tree.insert("", "end", values=(
                cid, c.name(cid), self.tname(c.team(cid)),
                "${:,}".format(con.get("salary", 0)), con.get("years", 0),
                "%dy" % con.get("ext_years", 0), shown))
            self.rows.append(cid)
        self.lbl_teamnote.config(text="%d coaches" % len(self.rows))

    # -------------------------------------------------------------- apply
    def apply(self, everything):
        if not self.coaches:
            return
        if everything:
            ids = list(self.rows)
        else:
            ids = [int(self.tree.item(i)["values"][0]) for i in self.tree.selection()]
        if not ids:
            messagebox.showinfo(APP, "No coaches selected."); return
        if ootp_running():
            messagebox.showerror(APP, "OOTP is running. Close it completely first -\n"
                                      "otherwise the game will overwrite these changes\n"
                                      "the next time it saves.")
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
                                  include_unknown=self.v_unk.get())] += 1
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
