#!/usr/bin/env python3
# Software Lite - an F-Droid-style app store for Nura (Alpine apk) on the YT3-850F.
# Real app names, summaries and icons come from the system AppStream catalog;
# screenshots are fetched from the web on the detail page. Installing and
# removing run through pkexec; if no polkit agent answers, the app tells you to
# use the terminal instead.
import glob
import os
import re
import subprocess
import threading
import urllib.request

import gi
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

APP_ID = "eco.nura.SoftwareLite"
ICON_BASES = ("/var/lib/swcatalog/icons", "/usr/share/swcatalog/icons")
ICON_SIZES = ("128x128", "96x96", "64x64", "48x48")
CACHE = os.path.join(GLib.get_user_cache_dir(), "software-lite")
SKIP_SUFFIX = ("-dev", "-doc", "-dbg", "-static", "-lang", "-pyc", "-openrc",
               "-libs", "-bash-completion", "-zsh-completion", "-fish-completion")

CSS = b"""
window { background: #0f1115; }
.bar { padding: 8px 10px; background: #161a21; }
entry { min-height: 46px; font-size: 17px; border-radius: 12px; padding: 0 14px; }
button { min-height: 44px; border-radius: 12px; }
.cat { min-height: 96px; font-size: 19px; font-weight: 700; background: #161a21; }
.row { background: #161a21; border-radius: 14px; padding: 10px; }
.name { font-size: 17px; font-weight: 600; color: #ffffff; }
.sum { font-size: 14px; color: #9aa4b2; }
.desc { font-size: 15px; color: #d7dde6; }
.h1 { font-size: 24px; font-weight: 700; color: #ffffff; }
.hint { font-size: 17px; color: #9aa4b2; }
.install { background: #3b9dff; color: #05070a; font-weight: 700; min-width: 116px; }
.remove { background: #2a2f38; color: #ff6b6b; font-weight: 700; min-width: 116px; }
.shot { background: #000000; border-radius: 10px; }
.toast { background: #3b9dff; color: #05070a; padding: 12px 20px; border-radius: 12px; font-weight: 600; font-size: 16px; }
"""


def run(cmd, timeout=120):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def pkgname(nv):
    name = re.sub(r"-r[0-9]+$", "", nv)
    name = re.sub(r"-[0-9][^-]*$", "", name)
    return name


def is_installed(name):
    return run(["apk", "info", "-e", name], timeout=20).returncode == 0


def icon_for_pkg(pkg, iconfile=None):
    pats = []
    for b in ICON_BASES:
        for s in ICON_SIZES:
            if iconfile:
                pats.append("%s/*/%s/%s" % (b, s, iconfile))
            pats.append("%s/*/%s/%s_*.png" % (b, s, pkg))
    for p in pats:
        m = sorted(glob.glob(p))
        if m:
            return m[0]
    return None


def appstream_search(query):
    res = run(["appstreamcli", "search", query])
    out, cur = [], {}
    for line in res.stdout.splitlines():
        if line.strip() == "---":
            if cur:
                out.append(cur)
            cur = {}
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            cur[k.strip()] = v.strip()
    if cur:
        out.append(cur)
    apps, seen = [], set()
    for c in out:
        pkg = c.get("Package")
        if not pkg or pkg in seen or pkg.endswith(SKIP_SUFFIX):
            continue
        seen.add(pkg)
        apps.append({
            "pkg": pkg,
            "name": c.get("Name", pkg),
            "summary": c.get("Summary", ""),
            "icon": c.get("Icon"),
            "id": c.get("Identifier", "").split(" ")[0],
        })
        if len(apps) >= 60:
            break
    return apps


def appstream_screenshots(identifier):
    if not identifier:
        return []
    res = run(["appstreamcli", "get", identifier], timeout=30)
    urls = re.findall(r"https?://\S+?\.(?:png|jpg|jpeg|webp)", res.stdout, re.I)
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:3]


def apk_description(name):
    res = run(["apk", "info", "-d", name], timeout=20)
    lines = res.stdout.splitlines()
    body = [l for l in lines[1:] if l.strip()] if lines else []
    return "\n".join(body) if body else ""


def apk_app_entry(name):
    d = run(["apk", "info", "-d", name], timeout=10).stdout.splitlines()
    summ = ""
    if d and " " in d[0]:
        summ = d[0].split(" ", 1)[1].rstrip(":")
    return {"pkg": name, "name": name, "summary": summ, "icon": None, "id": ""}


class Win(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Software Lite")
        self.set_default_size(1280, 800)
        self.theme = Gtk.IconTheme.get_default()
        self.busy = set()
        os.makedirs(CACHE, exist_ok=True)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        overlay = Gtk.Overlay()
        overlay.add(root)
        self.add(overlay)

        bar = Gtk.Box(spacing=8)
        bar.get_style_context().add_class("bar")
        self.back = Gtk.Button.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        self.back.set_no_show_all(True)
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

        # home: two buttons
        home_sc = Gtk.ScrolledWindow()
        home = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        home.set_border_width(24)
        home.set_valign(Gtk.Align.START)
        t = Gtk.Label(label="Software Lite", xalign=0)
        t.get_style_context().add_class("h1")
        home.pack_start(t, False, False, 0)
        b_new = Gtk.Button(label="New & Updated")
        b_new.get_style_context().add_class("cat")
        b_new.connect("clicked", lambda *_: self.show_new_updated())
        home.pack_start(b_new, False, False, 0)
        b_inst = Gtk.Button(label="Installed apps")
        b_inst.get_style_context().add_class("cat")
        b_inst.connect("clicked", lambda *_: self.show_installed())
        home.pack_start(b_inst, False, False, 0)
        hint = Gtk.Label(label="Or search for any app above.", xalign=0)
        hint.get_style_context().add_class("hint")
        home.pack_start(hint, False, False, 0)
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

        self.go_home()

    def go_home(self):
        self.back.set_visible(False)
        self.stack.set_visible_child_name("home")

    def busy_page(self, text):
        self.status.set_text(text)
        self.spinner.start()
        self.back.set_visible(True)
        self.stack.set_visible_child_name("status")

    def app_image(self, app, size):
        path = icon_for_pkg(app["pkg"], app.get("icon"))
        if path:
            try:
                return Gtk.Image.new_from_pixbuf(
                    GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True))
            except GLib.Error:
                pass
        img = Gtk.Image.new_from_icon_name("package-x-generic", Gtk.IconSize.DND)
        img.set_pixel_size(size)
        return img

    # ----- lists -----
    def on_search(self, _w):
        q = self.entry.get_text().strip()
        if q:
            self.busy_page("Searching…")
            threading.Thread(target=lambda: GLib.idle_add(
                self.show_results, appstream_search(q), "Results for “%s”" % q, False),
                daemon=True).start()

    def show_new_updated(self):
        self.busy_page("Checking for new and updated apps…")
        threading.Thread(target=self._new_worker, daemon=True).start()

    def _new_worker(self):
        res = run(["apk", "version", "-l", "<"], timeout=90)
        apps, seen = [], set()
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("installed"):
                continue
            name = pkgname(line.split()[0])
            if name in seen or name.endswith(SKIP_SUFFIX):
                continue
            seen.add(name)
            apps.append(apk_app_entry(name))
            if len(apps) >= 120:
                break
        apps.sort(key=lambda a: a["pkg"])
        GLib.idle_add(self.show_results, apps, "New & Updated", True)

    def show_installed(self):
        self.busy_page("Loading installed apps…")
        threading.Thread(target=self._installed_worker, daemon=True).start()

    def _installed_worker(self):
        names = [n for n in run(["apk", "info"], timeout=60).stdout.split()
                 if not n.endswith(SKIP_SUFFIX)]
        apps = [apk_app_entry(n) for n in sorted(names)[:150]]
        GLib.idle_add(self.show_results, apps, "Installed apps", False)

    def show_results(self, apps, title, update):
        self.spinner.stop()
        for c in self.results.get_children():
            self.results.remove(c)
        head = Gtk.Label(label=title, xalign=0)
        head.get_style_context().add_class("h1")
        self.results.pack_start(head, False, False, 4)
        if not apps:
            n = Gtk.Label(label="Nothing to show.")
            n.get_style_context().add_class("hint")
            self.results.pack_start(n, False, False, 0)
        for app in apps:
            self.results.pack_start(self.make_row(app, update), False, False, 0)
        self.results.show_all()
        self.back.set_visible(True)
        self.stack.set_visible_child_name("results")
        return False

    def make_row(self, app, update):
        row = Gtk.Box(spacing=12)
        row.get_style_context().add_class("row")
        row.pack_start(self.app_image(app, 48), False, False, 0)
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        txt.set_hexpand(True)
        nl = Gtk.Label(label=app["name"], xalign=0)
        nl.get_style_context().add_class("name")
        nl.set_ellipsize(Pango.EllipsizeMode.END)
        nl.set_max_width_chars(40)
        sl = Gtk.Label(label=app["summary"], xalign=0)
        sl.get_style_context().add_class("sum")
        sl.set_ellipsize(Pango.EllipsizeMode.END)
        sl.set_max_width_chars(48)
        txt.pack_start(nl, False, False, 0)
        txt.pack_start(sl, False, False, 0)
        details = Gtk.Button(label="Details")
        details.connect("clicked", lambda *_: self.open_detail(app))
        row.pack_start(txt, True, True, 0)
        row.pack_start(self.action_button(app["pkg"], update), False, False, 0)
        row.pack_start(details, False, False, 0)
        return row

    def action_button(self, pkg, update=False):
        if update:
            b = Gtk.Button(label="Update")
            b.get_style_context().add_class("install")
            b.connect("clicked", self.on_action, pkg, "update")
            return b
        installed = is_installed(pkg)
        b = Gtk.Button(label="Remove" if installed else "Install")
        b.get_style_context().add_class("remove" if installed else "install")
        b.connect("clicked", self.on_action, pkg, "toggle")
        return b

    # ----- detail -----
    def open_detail(self, app):
        self.busy_page("Loading %s…" % app["name"])
        threading.Thread(target=self._detail_worker, args=(app,), daemon=True).start()

    def _detail_worker(self, app):
        desc = apk_description(app["pkg"]) or app["summary"] or "No description available."
        shots = appstream_screenshots(app.get("id"))
        files = []
        for i, u in enumerate(shots):
            dest = os.path.join(CACHE, "%s-%d.img" % (app["pkg"], i))
            if not os.path.exists(dest):
                try:
                    with urllib.request.urlopen(u, timeout=20) as r, open(dest + ".part", "wb") as f:
                        f.write(r.read())
                    os.replace(dest + ".part", dest)
                except Exception:  # noqa: BLE001
                    continue
            files.append(dest)
        GLib.idle_add(self._show_detail, app, desc, files)

    def _show_detail(self, app, desc, shots):
        self.spinner.stop()
        for c in self.detail.get_children():
            self.detail.remove(c)
        top = Gtk.Box(spacing=14)
        top.pack_start(self.app_image(app, 72), False, False, 0)
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        head.set_valign(Gtk.Align.CENTER)
        head.set_hexpand(True)
        nl = Gtk.Label(label=app["name"], xalign=0)
        nl.get_style_context().add_class("h1")
        sl = Gtk.Label(label=app["summary"], xalign=0)
        sl.get_style_context().add_class("sum")
        sl.set_line_wrap(True)
        head.pack_start(nl, False, False, 0)
        head.pack_start(sl, False, False, 0)
        top.pack_start(head, True, True, 0)
        top.pack_start(self.action_button(app["pkg"]), False, False, 0)
        self.detail.pack_start(top, False, False, 0)

        if shots:
            strip = Gtk.ScrolledWindow()
            strip.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            strip.set_min_content_height(300)
            box = Gtk.Box(spacing=12)
            for f in shots:
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(f, 520, 300, True)
                    im = Gtk.Image.new_from_pixbuf(pb)
                    im.get_style_context().add_class("shot")
                    box.pack_start(im, False, False, 0)
                except GLib.Error:
                    pass
            strip.add(box)
            self.detail.pack_start(strip, False, False, 0)

        d = Gtk.Label(label=desc, xalign=0)
        d.get_style_context().add_class("desc")
        d.set_line_wrap(True)
        d.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.detail.pack_start(d, False, False, 0)
        self.detail.show_all()
        self.back.set_visible(True)
        self.stack.set_visible_child_name("detail")
        return False

    # ----- install / remove / update -----
    def on_action(self, button, pkg, mode):
        if pkg in self.busy:
            return
        self.busy.add(pkg)
        if mode == "update":
            remove, label = False, "Updating…"
            self.toast_msg("Updating " + pkg)
        else:
            remove = is_installed(pkg)
            label = "Removing…" if remove else "Installing…"
            self.toast_msg(("Removing " if remove else "Installing ") + pkg)
        button.set_sensitive(False)
        button.set_label(label)
        threading.Thread(target=self._action_worker, args=(pkg, remove, mode, button), daemon=True).start()

    def _action_worker(self, pkg, remove, mode, button):
        if mode == "update":
            cmd = ["pkexec", "apk", "add", "-q", "-u", pkg]
        else:
            cmd = ["pkexec", "apk", "del" if remove else "add", "-q", pkg]
        GLib.idle_add(self._action_done, pkg, remove, mode, button, run(cmd, timeout=1800))

    def _action_done(self, pkg, remove, mode, button, res):
        self.busy.discard(pkg)
        if res.returncode == 0:
            self.toast_msg(("Updated " if mode == "update" else ("Removed " if remove else "Installed ")) + pkg, 7)
        else:
            err = (res.stderr or "").lower()
            if "agent" in err or res.returncode == 127 or "authoriz" in err or "dismiss" in err:
                verb = "add -u" if mode == "update" else ("del" if remove else "add")
                self.toast_msg("Could not get permission. In the Console run:  sudo apk %s %s" % (verb, pkg), 12)
            else:
                self.toast_msg("Failed: " + ((res.stderr.strip().splitlines() or ["error"])[-1])[:80], 10)
        button.set_sensitive(True)
        if mode == "update":
            button.set_label("Updated" if res.returncode == 0 else "Update")
            return False
        now = is_installed(pkg)
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
        win = self.get_active_window() or Win(self)
        win.show_all()
        win.present()


if __name__ == "__main__":
    GLib.set_prgname(APP_ID)
    App().run(None)
