#!/usr/bin/env python3
# YT Player - a small touch-friendly video search front-end for the YT3-850F.
# Searches with yt-dlp, shows results with thumbnails, plays with mpv
# (mpv.conf limits playback to H.264 360p, which this tablet decodes smoothly).
import json
import os
import subprocess
import threading
import urllib.request

import gi
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

APP_ID = "eco.nura.YtPlayer"
CACHE = os.path.join(GLib.get_user_cache_dir(), "yt-player")
HIST = os.path.join(GLib.get_user_config_dir(), "yt-player", "history")
THUMB_W, THUMB_H = 300, 169
RESULTS = 20

CSS = b"""
window { background: #0f1115; }
.bar { padding: 10px; background: #161a21; }
entry { min-height: 48px; font-size: 18px; border-radius: 12px; padding: 0 14px; }
button { min-height: 48px; padding: 0 20px; border-radius: 12px; font-size: 16px; }
flowboxchild { padding: 0; border-radius: 14px; }
.card { background: #161a21; border-radius: 14px; padding: 8px; }
.title { font-size: 15px; font-weight: 600; color: #ffffff; }
.meta { font-size: 13px; color: #9aa4b2; }
.hint { font-size: 20px; color: #9aa4b2; }
.toast { background: #3b9dff; color: #05070a; padding: 12px 20px; border-radius: 12px; font-weight: 600; font-size: 16px; }
"""


def fmt_duration(sec):
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


def load_history():
    try:
        with open(HIST, encoding="utf-8") as f:
            return [x.strip() for x in f if x.strip()][:12]
    except OSError:
        return []


def save_history(items):
    try:
        os.makedirs(os.path.dirname(HIST), exist_ok=True)
        with open(HIST, "w", encoding="utf-8") as f:
            f.write("\n".join(items[:12]) + "\n")
    except OSError:
        pass


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="YT Player")
        self.set_default_size(1280, 800)
        self.generation = 0
        self.player = None
        self.history = load_history()
        os.makedirs(CACHE, exist_ok=True)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        overlay = Gtk.Overlay()
        overlay.add(root)
        self.add(overlay)

        bar = Gtk.Box(spacing=8)
        bar.get_style_context().add_class("bar")
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Search videos or paste a link")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self.on_search)
        search = Gtk.Button(label="Search")
        search.get_style_context().add_class("suggested-action")
        search.connect("clicked", self.on_search)
        bar.pack_start(self.entry, True, True, 0)
        bar.pack_start(search, False, False, 0)
        root.pack_start(bar, False, False, 0)

        self.stack = Gtk.Stack()
        root.pack_start(self.stack, True, True, 0)

        # home page: recent searches
        home = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        home.set_border_width(24)
        self.home_hint = Gtk.Label(label="Search for a video to start")
        self.home_hint.get_style_context().add_class("hint")
        home.pack_start(self.home_hint, False, False, 12)
        self.recent = Gtk.FlowBox()
        self.recent.set_selection_mode(Gtk.SelectionMode.NONE)
        self.recent.set_max_children_per_line(4)
        self.recent.set_column_spacing(10)
        self.recent.set_row_spacing(10)
        self.recent.set_valign(Gtk.Align.START)
        home.pack_start(self.recent, False, False, 0)
        self.stack.add_named(home, "home")

        # status page: spinner / message
        status = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        status.set_valign(Gtk.Align.CENTER)
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(48, 48)
        self.status_label = Gtk.Label()
        self.status_label.get_style_context().add_class("hint")
        self.status_label.set_line_wrap(True)
        status.pack_start(self.spinner, False, False, 0)
        status.pack_start(self.status_label, False, False, 0)
        self.stack.add_named(status, "status")

        # results page
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.grid = Gtk.FlowBox()
        self.grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.grid.set_activate_on_single_click(True)
        self.grid.set_homogeneous(True)
        self.grid.set_min_children_per_line(2)
        self.grid.set_max_children_per_line(4)
        self.grid.set_column_spacing(12)
        self.grid.set_row_spacing(12)
        self.grid.set_border_width(12)
        self.grid.set_valign(Gtk.Align.START)
        self.grid.connect("child-activated", self.on_card)
        scroller.add(self.grid)
        self.stack.add_named(scroller, "results")

        # toast
        self.toast = Gtk.Revealer()
        self.toast.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.toast.set_halign(Gtk.Align.CENTER)
        self.toast.set_valign(Gtk.Align.END)
        self.toast.set_margin_bottom(24)
        self.toast_label = Gtk.Label()
        self.toast_label.get_style_context().add_class("toast")
        self.toast.add(self.toast_label)
        overlay.add_overlay(self.toast)

        self.fill_recent()
        self.stack.set_visible_child_name("home")

    # ----- home -----
    def fill_recent(self):
        for child in self.recent.get_children():
            self.recent.remove(child)
        for q in self.history:
            b = Gtk.Button(label=q)
            b.connect("clicked", self.on_recent, q)
            self.recent.add(b)
        self.home_hint.set_text("Recent searches" if self.history else "Search for a video to start")
        self.recent.show_all()

    def on_recent(self, _button, q):
        self.entry.set_text(q)
        self.on_search(None)

    # ----- search -----
    def on_search(self, _widget):
        q = self.entry.get_text().strip()
        if not q:
            return
        if q.startswith("http://") or q.startswith("https://"):
            self.play(q)
            return
        if q in self.history:
            self.history.remove(q)
        self.history.insert(0, q)
        save_history(self.history)
        self.fill_recent()

        self.generation += 1
        self.status_label.set_text("Searching...")
        self.spinner.start()
        self.stack.set_visible_child_name("status")
        threading.Thread(target=self.search_worker, args=(q, self.generation), daemon=True).start()

    def search_worker(self, q, gen):
        entries, error = [], None
        try:
            out = subprocess.run(
                ["yt-dlp", "--flat-playlist", "-J", "--no-warnings", "ytsearch%d:%s" % (RESULTS, q)],
                capture_output=True, text=True, timeout=120)
            if out.stdout.strip():
                entries = (json.loads(out.stdout).get("entries") or [])
            else:
                error = (out.stderr.strip().splitlines() or ["no output"])[-1]
        except Exception as e:  # noqa: BLE001 - shown to the user
            error = str(e)
        GLib.idle_add(self.show_results, entries, error, gen)

    def show_results(self, entries, error, gen):
        if gen != self.generation:
            return False
        self.spinner.stop()
        for child in self.grid.get_children():
            self.grid.remove(child)
        entries = [e for e in entries if e and e.get("id")]
        if not entries:
            self.status_label.set_text("No results.\n%s" % error if error else "No results.")
            self.stack.set_visible_child_name("status")
            return False

        images = []
        for e in entries:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.get_style_context().add_class("card")
            img = Gtk.Image()
            img.set_size_request(THUMB_W, THUMB_H)
            title = Gtk.Label(label=e.get("title") or "(untitled)")
            title.get_style_context().add_class("title")
            title.set_xalign(0)
            title.set_line_wrap(True)
            title.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            title.set_lines(2)
            title.set_ellipsize(Pango.EllipsizeMode.END)
            title.set_max_width_chars(28)
            bits = [x for x in (e.get("channel") or e.get("uploader"), fmt_duration(e.get("duration"))) if x]
            meta = Gtk.Label(label="  ·  ".join(bits))
            meta.get_style_context().add_class("meta")
            meta.set_xalign(0)
            meta.set_ellipsize(Pango.EllipsizeMode.END)
            meta.set_max_width_chars(28)
            card.pack_start(img, False, False, 0)
            card.pack_start(title, False, False, 0)
            card.pack_start(meta, False, False, 0)
            child = Gtk.FlowBoxChild()
            child.video_id = e["id"]
            child.add(card)
            self.grid.add(child)
            images.append((e["id"], img))
        self.grid.show_all()
        self.stack.set_visible_child_name("results")
        threading.Thread(target=self.thumb_worker, args=(images, gen), daemon=True).start()
        return False

    def thumb_worker(self, images, gen):
        for vid, img in images:
            if gen != self.generation:
                return
            path = os.path.join(CACHE, vid + ".jpg")
            if not os.path.exists(path):
                try:
                    url = "https://i.ytimg.com/vi/%s/mqdefault.jpg" % vid
                    with urllib.request.urlopen(url, timeout=20) as r, open(path + ".part", "wb") as f:
                        f.write(r.read())
                    os.replace(path + ".part", path)
                except Exception:  # noqa: BLE001 - a missing thumbnail is fine
                    continue
            GLib.idle_add(self.set_thumb, img, path)

    def set_thumb(self, img, path):
        try:
            img.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(path, THUMB_W, THUMB_H, True))
        except GLib.Error:
            pass
        return False

    # ----- playback -----
    def on_card(self, _grid, child):
        self.play("https://www.youtube.com/watch?v=%s" % child.video_id)

    def play(self, url):
        if self.player is not None and self.player.poll() is None:
            return
        try:
            self.player = subprocess.Popen(["mpv", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            self.show_toast("Could not start mpv: %s" % e)
            return
        self.show_toast("Loading video...")

    def show_toast(self, text, seconds=12):
        self.toast_label.set_text(text)
        self.toast.set_reveal_child(True)
        GLib.timeout_add_seconds(seconds, self.hide_toast)

    def hide_toast(self):
        self.toast.set_reveal_child(False)
        return False


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        win = self.get_active_window() or Window(self)
        win.show_all()
        win.present()


if __name__ == "__main__":
    GLib.set_prgname(APP_ID)
    App().run(None)
