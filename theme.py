"""Visual theme for OOTP Coach Editor.

The look is borrowed from the subject rather than from generic app chrome: the
tool is front-office paperwork, so the light theme is blueprint paper with navy
ink and the dark theme is a night game - deep navy, never pure black. Stitch red
is the only accent and is spent on the primary action alone.

Type does three jobs: Bahnschrift Condensed (scoreboard signage) for eyebrows
and the wordmark, Segoe UI for prose, Consolas for anything numeric so salaries
and the 12-number ratings strip line up like a box score.
"""

THEMES = {
    "light": {
        "name": "light",
        "bg": "#E9EDF1",        # blueprint paper
        "panel": "#FFFFFF",
        "panel_alt": "#F4F7F9",  # zebra row
        "ink": "#12263A",        # navy ink
        "ink_soft": "#5B7185",
        "line": "#C6D2DC",
        "accent": "#B3372B",     # stitch red
        "accent_ink": "#FFFFFF",
        "link": "#14568C",
        "sel": "#D6E4F0",
        "sel_ink": "#0B1D2E",
        "done": "#1F7A4D",       # fully maxed
        "partial": "#B06A16",
        "field": "#FFFFFF",
    },
    "dark": {
        "name": "dark",
        "bg": "#0E1620",         # night game
        "panel": "#16212E",
        "panel_alt": "#1B2836",
        "ink": "#DCE6F0",
        "ink_soft": "#8AA0B6",
        "line": "#2A3B4F",
        "accent": "#E4574A",
        "accent_ink": "#0E1620",
        "link": "#6FB4EC",
        "sel": "#26405C",
        "sel_ink": "#EAF2FA",
        "done": "#4FCB8B",
        "partial": "#E0A040",
        "field": "#1C2836",
    },
}

DISPLAY = "Bahnschrift Condensed"
BODY = "Segoe UI"
MONO = "Consolas"


def fonts(root):
    """Fall back gracefully if a face is missing on this machine."""
    import tkinter.font as tkfont
    fams = set(tkfont.families(root))
    disp = DISPLAY if DISPLAY in fams else ("Segoe UI Semibold" if "Segoe UI Semibold" in fams else "Segoe UI")
    body = BODY if BODY in fams else "TkDefaultFont"
    mono = MONO if MONO in fams else "TkFixedFont"
    return {
        "wordmark": (disp, 20),
        "eyebrow": (disp, 10),
        "h": (disp, 12),
        "body": (body, 9),
        "body_b": (body, 9, "bold"),
        "small": (body, 8),
        "mono": (mono, 9),
        "link": (body, 9, "underline"),
        "btn": (disp, 11),
    }


def apply(style, root, t, f):
    """Paint every widget class used by the app."""
    style.theme_use("clam")
    root.configure(bg=t["bg"])

    style.configure(".", background=t["bg"], foreground=t["ink"],
                    fieldbackground=t["field"], font=f["body"],
                    bordercolor=t["line"], lightcolor=t["bg"], darkcolor=t["bg"])
    style.configure("TFrame", background=t["bg"])
    style.configure("Panel.TFrame", background=t["panel"])
    style.configure("TLabel", background=t["bg"], foreground=t["ink"], font=f["body"])
    style.configure("Soft.TLabel", background=t["bg"], foreground=t["ink_soft"], font=f["small"])
    style.configure("Eyebrow.TLabel", background=t["bg"], foreground=t["ink_soft"], font=f["eyebrow"])
    style.configure("TSeparator", background=t["line"])

    # inputs
    for cls in ("TCombobox", "TSpinbox", "TEntry"):
        style.configure(cls, fieldbackground=t["field"], background=t["field"],
                        foreground=t["ink"], arrowcolor=t["ink_soft"],
                        bordercolor=t["line"], insertcolor=t["ink"], padding=3)
        style.map(cls,
                  fieldbackground=[("readonly", t["field"]), ("disabled", t["bg"])],
                  foreground=[("disabled", t["ink_soft"])],
                  bordercolor=[("focus", t["link"])])
    root.option_add("*TCombobox*Listbox.background", t["field"])
    root.option_add("*TCombobox*Listbox.foreground", t["ink"])
    root.option_add("*TCombobox*Listbox.selectBackground", t["sel"])
    root.option_add("*TCombobox*Listbox.selectForeground", t["sel_ink"])
    root.option_add("*TCombobox*Listbox.font", f["body"])

    style.configure("TCheckbutton", background=t["bg"], foreground=t["ink"], font=f["body"],
                    indicatorbackground=t["field"], indicatorforeground=t["accent_ink"],
                    bordercolor=t["line"], focuscolor=t["link"], padding=(0, 2))
    style.map("TCheckbutton",
              background=[("active", t["bg"])],
              indicatorbackground=[("selected", t["accent"]), ("active", t["sel"])],
              indicatorforeground=[("selected", t["accent_ink"])])

    # buttons: quiet by default, red only for the primary action
    style.configure("TButton", background=t["panel"], foreground=t["ink"],
                    bordercolor=t["line"], focusthickness=1, focuscolor=t["link"],
                    padding=(10, 5), font=f["body"])
    style.map("TButton",
              background=[("active", t["sel"]), ("disabled", t["bg"])],
              foreground=[("disabled", t["ink_soft"])])
    style.configure("Primary.TButton", background=t["accent"], foreground=t["accent_ink"],
                    bordercolor=t["accent"], padding=(16, 7), font=f["btn"])
    style.map("Primary.TButton",
              background=[("active", t["ink"]), ("disabled", t["line"])],
              foreground=[("disabled", t["ink_soft"])])

    # the table carries the app, so it gets the most care
    style.configure("Treeview", background=t["panel"], fieldbackground=t["panel"],
                    foreground=t["ink"], rowheight=23, borderwidth=0, font=f["mono"])
    style.map("Treeview",
              background=[("selected", t["sel"])],
              foreground=[("selected", t["sel_ink"])])
    style.configure("Treeview.Heading", background=t["bg"], foreground=t["ink_soft"],
                    font=f["eyebrow"], relief="flat", padding=(6, 6), bordercolor=t["line"])
    style.map("Treeview.Heading", background=[("active", t["sel"])],
              foreground=[("active", t["ink"])])
    style.configure("Vertical.TScrollbar", background=t["bg"], troughcolor=t["bg"],
                    arrowcolor=t["ink_soft"], bordercolor=t["bg"])
    style.map("Vertical.TScrollbar", background=[("active", t["line"])])

    style.configure("Ok.TLabel", background=t["bg"], foreground=t["done"], font=f["small"])
    style.configure("Bad.TLabel", background=t["bg"], foreground=t["accent"], font=f["body_b"])
    style.configure("Status.TLabel", background=t["panel"], foreground=t["ink_soft"],
                    font=f["small"], padding=(8, 5))
