#!/usr/bin/env python3
# Software Lite - an F-Droid-style app store for Nura (Alpine apk) on the YT3-850F.
# Browse categories, search, open an app for its full description, and install or
# remove it. Privileged actions run through pkexec; if no polkit agent answers,
# the app tells you to use the terminal "apps" helper instead.
import os
import subprocess
import threading

import gi
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

APP_ID = "eco.nura.SoftwareLite"

CATEGORIES = [
    ("Browsers", "web browser"),
    ("Internet", "chat messenger email"),
    ("Media", "music player audio video"),
    ("Graphics", "image editor viewer paint"),
    ("Games", "game"),
    ("Office", "office document editor pdf"),
    ("Development", "editor terminal programming"),
    ("System", "files manager monitor utility"),
]
# subpackages that should never appear as installable apps
SKIP_SUFFIX = ("-dev", "-doc", "-dbg", "-static", "-lang", "-pyc", "-openrc",
               "-bash-completion", "-zsh-completion", "-fish-completion", "-libs")

CSS = b"""
window { background: #0f1115; }
.bar { padding: 8px 10px; background: #161a21; }
entry { min-height: 46px; font-size: 17px; border-radius: 12px; padding: 0 14px; }
button { min-height: 44px; border-radius: 12px; }
.cat { min-height: 92px; font-size: 17px; font-weight: 600; background: #161a21; }
.row { background: #161a21; border-radius: 14px; padding: 10px; }
.name { font-size: 17px; font-weight: 600; color: #ffffff; }
.sum { font-size: 14px; color: #9aa4b2; }
.desc { font-size: 15px; color: #d7dde6; }
.h1 { font-size: 24px; font-weight: 700; color: #ffffff; }
.hint { font-size: 19px; color: #9aa4b2; }
.install { background: #3b9dff; color: #05070a; font-weight: 700; min-width: 120px; }
.remove { background: #2a2f38; color: #ff6b6b; font-weight: 700; min-width: 120px; }
.toast { background: #3b9dff; color: #05070a; padding: 12px 20px; border-radius: 12px; font-weight: 600; font-size: 16px; }
"""


def run(cmd, timeout=120):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        r = subprocess.CompletedProcess(cmd, 1, "", str(e))
        return r


def pkgname(nv):
    name = nv
    # strip -rN then -version
    import re
    name = re.sub(r"-r[0-9]+$", "", name)
    name = re.sub(r"-[0-9][^-]*$", "", name)
    return name


def is_installed(name):
    return run(["apk", "info", "-e", name], timeout=20).returncode == 0


def search_pkgs(query):
    seen, out = set(), []
    res = run(["apk", "search", "-v"] + query.split())
    res2 = run(["apk", "search", "-v", "-d"] + query.split())
    for line in (res.stdout + "\n" + res2.stdout).splitlines():
        line = line.strip()
        if not line:
            continue
        nv = line.split(" ", 1)[0]
        summary = line.split(" ", 1)[1] if " " in line else ""
        name = pkgname(nv)
        if name in seen or name.endswith(SKIP_SUFFIX):
            continue
        seen.add(name)
        out.append((name, summary))
        if len(out) >= 60:
            break
    out.sort(key=lambda x: x[0])
    return out


def full_description(name):
    res = run(["apk", "info", "-d", name], timeout=20)
    lines = res.stdout.splitlines()
    body = [l for l in lines[1:] if l.strip()] if lines else []
    return "\n".join(body) if body else "No description available."


class Win(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Software Lite")
        self.set_default_size(1280, 800)
        self.icon_theme = Gtk.IconTheme.get_default()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        overlay = Gtk.Overlay()
        overlay.add(root)
        self.add(overlay)

        bar = Gtk.Box(spacing=8)
        bar.get_style_context().add_class("bar")
        self.back = Gtk.Button.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        self.back.connect("clicked", lambda *_: self.go_home())
        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text("Search apps")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self.on_search)
        bar.pack_start(self.back, False, False, 0)
        bar.pack_start(self.entry, True, True, 0)
        root.pack_start(bar, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        root.pack_start(self.stack, True, True, 0)

        # home
        home_sc = Gtk.ScrolledWindow()
        home = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        home.set_border_width(20)
        h1 = Gtk.Label(label="Categories", xalign=0)
        h1.get_style_context().add_class("h1")
        home.pack_start(h1, False, False, 0)
        cats = Gtk.FlowBox()
        cats.set_selection_mode(Gtk.SelectionMode.NONE)
        cats.set_min_children_per_line(2)
        cats.set_max_children_per_line(4)
        cats.set_column_spacing(12)
        cats.set_row_spacing(12)
        cats.set_homogeneous(True)
        for label, query in CATEGORIES:
            b = Gtk.Button(label=label)
            b.get_style_context().add_class("cat")
            b.connect("clicked", self.on_category, label, query)
            cats.add(b)
        home.pack_start(cats, False, False, 0)
        inst = Gtk.Button(label="Installed apps")
        inst.get_style_context().add_class("cat")
        inst.connect("clicked", lambda *_: self.show_installed())
        home.pack_start(inst, False, False, 0)
        home_sc.add(home)
        self.stack.add_named(home_sc, "home")

        # status
        st = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        st.set_valign(Gtk.Align.CENTER)
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(48, 48)
        self.status = Gtk.Label()
        self.status.get_style_context().add_class("hint")
        st.pack_start(self.spinner, False, False, 0)
        st.pack_start(self.status, False, False, 0)
        self.stack.add_named(st, "status")

        # results
        res_sc = Gtk.ScrolledWindow()
        self.results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.results.set_border_width(14)
        res_sc.add(self.results)
        self.stack.add_named(res_sc, "results")

        # detail
        det_sc = Gtk.ScrolledWindow()
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.detail.set_border_width(24)
        det_sc.add(self.detail)
        self.stack.add_named(det_sc, "detail")

        # toast
        self.toast = Gtk.Revealer()
        self.toast.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.toast.set_halign(Gtk.Align.CENTER)
        self.toast.set_valign(Gtk.Align.END)
        self.toast.set_margin_bottom(22)
        self.toast_lbl = Gtk.Label()
        self.toast_lbl.get_style_context().add_class("toast")
        self.toast.add(self.toast_lbl)
        overlay.add_overlay(self.toast)

        self.busy = set()
        self.go_home()

    def go_home(self):
        self.back.set_visible(False)
        self.stack.set_visible_child_name("home")

    def icon_for(self, name):
        for cand in (name, name + "-symbolic"):
            if self.icon_theme.has_icon(cand):
                return cand
        return "package-x-generic"

    def busy_page(self, text):
        self.status.set_text(text)
        self.spinner.start()
        self.back.set_visible(True)
        self.stack.set_visible_child_name("status")

    # ----- search / browse -----
    def on_search(self, _w):
        q = self.entry.get_text().strip()
        if q:
            self.load(q, "Results for “%s”" % q)

    def on_category(self, _b, label, query):
        self.load(query, label)

    def show_installed(self):
        self.busy_page("Loading installed apps…")
        threading.Thread(target=self._installed_worker, daemon=True).start()

    def _installed_worker(self):
        res = run(["apk", "info"], timeout=60)
        names = [n for n in res.stdout.split() if not n.endswith(SKIP_SUFFIX)]
        rows = []
        for n in names:
            d = run(["apk", "info", "-d", n], timeout=10).stdout.splitlines()
            summ = ""
            if d:
                first = d[0]
                if " " in first:
                    summ = first.split(" ", 1)[1].rstrip(":")
            rows.append((n, summ))
            if len(rows) >= 120:
                break
        rows.sort(key=lambda x: x[0])
        GLib.idle_add(self.show_results, rows, "Installed apps")

    def load(self, query, title):
        self.busy_page("Searching…")
        threading.Thread(target=lambda: GLib.idle_add(self.show_results, search_pkgs(query), title),
                         daemon=True).start()

    def show_results(self, rows, title):
        self.spinner.stop()
        for c in self.results.get_children():
            self.results.remove(c)
        head = Gtk.Label(label=title, xalign=0)
        head.get_style_context().add_class("h1")
        self.results.pack_start(head, False, False, 4)
        if not rows:
            n = Gtk.Label(label="Nothing found.")
            n.get_style_context().add_class("hint")
            self.results.pack_start(n, False, False, 0)
        for name, summ in rows:
            self.results.pack_start(self.make_row(name, summ), False, False, 0)
        self.results.show_all()
        self.back.set_visible(True)
        self.stack.set_visible_child_name("results")
        return False

    def make_row(self, name, summ):
        row = Gtk.Box(spacing=12)
        row.get_style_context().add_class("row")
        img = Gtk.Image.new_from_icon_name(self.icon_for(name), Gtk.IconSize.DND)
        img.set_pixel_size(48)
        row.pack_start(img, False, False, 0)
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        txt.set_hexpand(True)
        nl = Gtk.Label(label=name, xalign=0)
        nl.get_style_context().add_class("name")
        sl = Gtk.Label(label=summ, xalign=0)
        sl.get_style_context().add_class("sum")
        sl.set_ellipsize(Pango.EllipsizeMode.END)
        sl.set_max_width_chars(48)
        txt.pack_start(nl, False, False, 0)
        txt.pack_start(sl, False, False, 0)
        open_btn = Gtk.Button(label="Details")
        open_btn.connect("clicked", lambda *_: self.open_detail(name))
        row.pack_start(txt, True, True, 0)
        row.pack_start(self.action_button(name), False, False, 0)
        row.pack_start(open_btn, False, False, 0)
        return row

    def action_button(self, name):
        installed = is_installed(name)
        b = Gtk.Button(label="Remove" if installed else "Install")
        b.get_style_context().add_class("remove" if installed else "install")
        b.connect("clicked", self.on_action, name)
        return b

    def open_detail(self, name):
        self.busy_page("Loading %s…" % name)
        threading.Thread(target=lambda: GLib.idle_add(self._show_detail, name, full_description(name)),
                         daemon=True).start()

    def _show_detail(self, name, desc):
        self.spinner.stop()
        for c in self.detail.get_children():
            self.detail.remove(c)
        top = Gtk.Box(spacing=14)
        img = Gtk.Image.new_from_icon_name(self.icon_for(name), Gtk.IconSize.DIALOG)
        img.set_pixel_size(72)
        top.pack_start(img, False, False, 0)
        nl = Gtk.Label(label=name, xalign=0)
        nl.get_style_context().add_class("h1")
        nl.set_valign(Gtk.Align.CENTER)
        top.pack_start(nl, True, True, 0)
        top.pack_start(self.action_button(name), False, False, 0)
        self.detail.pack_start(top, False, False, 0)
        d = Gtk.Label(label=desc, xalign=0)
        d.get_style_context().add_class("desc")
        d.set_line_wrap(True)
        d.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.detail.pack_start(d, False, False, 0)
        self.detail.show_all()
        self.back.set_visible(True)
        self.stack.set_visible_child_name("detail")
        return False

    # ----- install / remove -----
    def on_action(self, button, name):
        if name in self.busy:
            return
        self.busy.add(name)
        remove = is_installed(name)
        button.set_sensitive(False)
        button.set_label("Removing…" if remove else "Installing…")
        self.toast_msg(("Removing " if remove else "Installing ") + name)
        threading.Thread(target=self._action_worker, args=(name, remove, button), daemon=True).start()

    def _action_worker(self, name, remove, button):
        verb = "del" if remove else "add"
        res = run(["pkexec", "apk", verb, "-q", name], timeout=1800)
        GLib.idle_add(self._action_done, name, remove, button, res)

    def _action_done(self, name, remove, button, res):
        self.busy.discard(name)
        if res.returncode == 0:
            self.toast_msg(("Removed " if remove else "Installed ") + name, 7)
        else:
            err = (res.stderr or "").lower()
            if "agent" in err or res.returncode == 127 or "authoriz" in err or "dismiss" in err:
                self.toast_msg("Could not get permission. Open the Console and run: apk %s %s"
                               % ("del" if remove else "add", name), 12)
            else:
                tail = (res.stderr.strip().splitlines() or ["failed"])[-1]
                self.toast_msg("Failed: " + tail[:80], 10)
        now = is_installed(name)
        button.set_sensitive(True)
        button.set_label("Remove" if now else "Install")
        ctx = button.get_style_context()
        ctx.remove_class("install")
        ctx.remove_class("remove")
        ctx.add_class("remove" if now else "install")
        return False

    def toast_msg(self, text, seconds=6):
        self.toast_lbl.set_text(text)
        self.toast.set_reveal_child(True)
        GLib.timeout_add_seconds(seconds, lambda: (self.toast.set_reveal_child(False), False)[1])


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        p = Gtk.CssProvider()
        p.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        (self.get_active_window() or Win(self)).present()


if __name__ == "__main__":
    GLib.set_prgname(APP_ID)
    App().run(None)
