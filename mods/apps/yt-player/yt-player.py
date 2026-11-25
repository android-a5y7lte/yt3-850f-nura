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
# H.264 at 360p is what this tablet decodes smoothly
PLAY_FORMAT = "bestvideo[height<=360][vcodec^=avc1]+bestaudio/best[height<=360]"
# one ready-made file with picture and sound, so no merge step is needed
DOWNLOAD_FORMAT = "best[height<=360][ext=mp4]/best[height<=360]"
VIDEOS = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS) or os.path.expanduser("~/Videos")
INPUT_CONF = os.path.join(GLib.get_user_config_dir(), "yt-player", "input.conf")
TOUCH_LUA = os.path.join(GLib.get_user_config_dir(), "yt-player", "yt-touch.lua")
MPV_ARGS = [
    "mpv", "--fs", "--profile=fast", "--ytdl-format=" + PLAY_FORMAT,
    # mpv's default renderer (gpu-next/libplacebo) cannot compile its overlay shader
    # on this tablet's Adreno 304, so nothing is drawn over the video. The older
    # gpu renderer with OpenGL ES works.
    "--vo=gpu", "--opengl-es=yes",
    # the stock control bar is off; yt-touch.lua draws finger-sized controls
    "--osc=no",
    "--input-conf=" + INPUT_CONF,
    "--script=" + TOUCH_LUA,
]
# Touch controls for mpv, written to TOUCH_LUA at start-up.
TOUCH_SCRIPT = r"""
-- YT Player touch controls for mpv (stock control bar is switched off).
-- Tap: show/hide controls. Centre: back 10 s, play/pause, forward 10 s.
-- Bottom: seek bar. Top-left: download. Top-right: close.
-- Slide left/right: seek. Slide up/down: volume.
local start, visible, hide_timer, tick = nil, false, nil, nil
local ov = mp.create_osd_overlay("ass-events")
local downloading = {}

local function dims()
    local w = mp.get_property_number("osd-width", 0)
    local h = mp.get_property_number("osd-height", 0)
    if w <= 0 or h <= 0 then w, h = 1280, 800 end
    return w, h
end

local function layout()
    local w, h = dims()
    local L = { w = w, h = h }
    L.S = math.floor(h * 0.17)            -- play/pause size
    L.s2 = math.floor(L.S * 0.7)          -- back/forward size
    L.cy = math.floor(h / 2)
    L.gap = math.floor(L.S * 2.3)
    L.cx = math.floor(w / 2)
    L.bx0 = math.floor(w * 0.12)
    L.bx1 = math.floor(w * 0.88)
    L.by = math.floor(h * 0.88)
    L.bh = math.max(8, math.floor(h * 0.012))
    L.D = math.floor(h * 0.10)            -- download icon size
    L.fs = math.floor(h * 0.04)
    return L
end

local function fmt_time(t)
    if not t or t < 0 then t = 0 end
    t = math.floor(t)
    local hh, mm, ss = math.floor(t / 3600), math.floor(t % 3600 / 60), t % 60
    if hh > 0 then return string.format("%d:%02d:%02d", hh, mm, ss) end
    return string.format("%d:%02d", mm, ss)
end

local function shape(x, y, path, alpha)
    return string.format("{\\an7\\pos(%d,%d)\\bord2\\shad0\\1c&HFFFFFF&\\3c&H000000&\\1a&H%s&\\p1}%s{\\p0}",
        math.floor(x), math.floor(y), alpha or "00", path)
end

local function text(x, y, an, size, str)
    return string.format("{\\an%d\\pos(%d,%d)\\fs%d\\bord2\\shad0\\1c&HFFFFFF&\\3c&H000000&}%s",
        an, math.floor(x), math.floor(y), math.floor(size), str)
end

local function rect(wd, ht)
    return string.format("m 0 0 l %d 0 l %d %d l 0 %d", wd, wd, ht, ht)
end

local function draw()
    local L = layout()
    local out = {}
    local S, s2, f = L.S, L.s2, math.floor

    -- play / pause
    if mp.get_property_bool("pause") then
        out[#out + 1] = shape(L.cx - S / 2, L.cy - S / 2, string.format("m 0 0 l %d %d l 0 %d", S, f(S / 2), S))
    else
        local bw = f(S * 0.34)
        out[#out + 1] = shape(L.cx - S / 2, L.cy - S / 2, string.format(
            "m 0 0 l %d 0 l %d %d l 0 %d m %d 0 l %d 0 l %d %d l %d %d",
            bw, bw, S, S, S - bw, S, S, S, S - bw, S))
    end
    -- back 10 s (two left-pointing triangles)
    local hf, md = f(s2 / 2), f(s2 / 2)
    out[#out + 1] = shape(L.cx - L.gap - s2 / 2, L.cy - s2 / 2, string.format(
        "m %d 0 l 0 %d l %d %d m %d 0 l %d %d l %d %d", hf, md, hf, s2, s2, hf, md, s2, s2))
    out[#out + 1] = text(L.cx - L.gap, L.cy + s2 / 2 + 6, 8, L.fs, "-10")
    -- forward 10 s (two right-pointing triangles)
    out[#out + 1] = shape(L.cx + L.gap - s2 / 2, L.cy - s2 / 2, string.format(
        "m 0 0 l %d %d l 0 %d m %d 0 l %d %d l %d %d", hf, md, s2, hf, s2, md, hf, s2))
    out[#out + 1] = text(L.cx + L.gap, L.cy + s2 / 2 + 6, 8, L.fs, "+10")

    -- seek bar with times
    local pos = mp.get_property_number("time-pos", 0) or 0
    local dur = mp.get_property_number("duration", 0) or 0
    local len = L.bx1 - L.bx0
    local frac = 0
    if dur > 0 then frac = math.max(0, math.min(1, pos / dur)) end
    out[#out + 1] = shape(L.bx0, L.by, rect(len, L.bh), "90")
    if frac > 0 then out[#out + 1] = shape(L.bx0, L.by, rect(math.max(1, f(len * frac)), L.bh)) end
    local k = L.bh * 3
    out[#out + 1] = shape(L.bx0 + len * frac - k / 2, L.by + L.bh / 2 - k / 2, rect(k, k))
    out[#out + 1] = text(L.bx0 - 14, L.by + L.bh / 2, 6, L.fs, fmt_time(pos))
    out[#out + 1] = text(L.bx1 + 14, L.by + L.bh / 2, 4, L.fs, fmt_time(dur))

    -- download arrow (top-left): shaft, head, tray
    local D = L.D
    out[#out + 1] = shape(28, 20, string.format(
        "m %d 0 l %d 0 l %d %d l %d %d m %d %d l %d %d l %d %d m %d %d l %d %d l %d %d l %d %d",
        f(D * 0.38), f(D * 0.62), f(D * 0.62), f(D * 0.45), f(D * 0.38), f(D * 0.45),
        f(D * 0.15), f(D * 0.45), f(D * 0.85), f(D * 0.45), f(D * 0.5), f(D * 0.82),
        f(D * 0.1), f(D * 0.9), f(D * 0.9), f(D * 0.9), f(D * 0.9), D, f(D * 0.1), D))
    -- close (top-right)
    out[#out + 1] = text(L.w - 28, 12, 9, L.h * 0.11, "×")

    ov.res_x, ov.res_y = L.w, L.h
    ov.data = table.concat(out, "\n")
    ov:update()
end

local function set_visible(v)
    visible = v
    if v then
        draw()
        if tick then tick:resume() else tick = mp.add_periodic_timer(0.5, draw) end
    else
        if tick then tick:stop() end
        ov:remove()
    end
end

local function hide()
    if mp.get_property_bool("pause") then
        hide_timer = mp.add_timeout(5, hide)  -- keep the controls while paused
        return
    end
    set_visible(false)
end

local function show()
    if hide_timer then hide_timer:kill() end
    if visible then draw() else set_visible(true) end
    hide_timer = mp.add_timeout(5, hide)
end

local function download()
    local url = mp.get_property("path", "")
    if not url:match("^https?://") then
        mp.osd_message("Nothing to download", 2)
        return
    end
    if downloading[url] then
        mp.osd_message("Already downloading this video", 2)
        return
    end
    downloading[url] = true
    local dir = os.getenv("YT_PLAYER_VIDEOS") or ((os.getenv("HOME") or "") .. "/Videos")
    local fmt = os.getenv("YT_PLAYER_DLFMT") or "best[height<=360][ext=mp4]/best[height<=360]"
    mp.commandv("run", "sh", "-c",
        'mkdir -p "$2"; if yt-dlp --no-warnings --no-playlist -f "$1" -o "$2/%(title).80s [%(id)s].%(ext)s" "$3"; ' ..
        'then notify-send "YT Player" "Video saved to Videos" 2>/dev/null; ' ..
        'else notify-send "YT Player" "Download failed" 2>/dev/null; fi',
        "sh", fmt, dir, url)
    mp.osd_message("Download started - it is saved to Videos when finished", 3)
end

local function pos()
    local p = mp.get_property_native("mouse-pos")
    return p.x, p.y
end

local function near(a, b, r) return math.abs(a - b) <= r end

mp.add_key_binding("MBTN_LEFT", "yt-touch", function(t)
    if t.event == "down" then
        local x, y = pos()
        start = { x = x, y = y }
        return
    end
    if t.event ~= "up" or not start then return end
    local x, y = pos()
    local sx, sy = start.x, start.y
    local dx, dy = x - sx, y - sy
    start = nil
    local L = layout()
    local w, h = L.w, L.h

    -- touch that began on the seek bar: jump to where the finger ended
    if visible and sy > h * 0.80 and sx > L.bx0 - 40 and sx < L.bx1 + 40 then
        local frac = math.max(0, math.min(1, (x - L.bx0) / (L.bx1 - L.bx0)))
        mp.commandv("seek", string.format("%.2f", frac * 100), "absolute-percent")
        show()
        return
    end
    if math.abs(dx) > w * 0.06 and math.abs(dx) > math.abs(dy) then
        local secs = math.floor(dx / w * 120)
        mp.commandv("seek", secs, "relative")
        mp.osd_message(string.format("%+d s", secs), 1.5)
        if visible then show() end
        return
    end
    if math.abs(dy) > h * 0.08 then
        mp.commandv("add", "volume", math.floor(-dy / h * 60))
        mp.osd_message("Volume " .. math.floor(mp.get_property_number("volume", 0)), 1.5)
        return
    end
    if not visible then
        show()
        return
    end
    -- taps on the controls
    if x > w * 0.86 and y < h * 0.18 then
        mp.commandv("quit")
    elseif x < w * 0.14 and y < h * 0.20 then
        download()
        show()
    elseif near(y, L.cy, L.S * 0.8) and near(x, L.cx, L.S * 0.9) then
        mp.commandv("cycle", "pause")
        show()
    elseif near(y, L.cy, L.S * 0.8) and near(x, L.cx - L.gap, L.S * 0.9) then
        mp.commandv("seek", -10, "relative")
        show()
    elseif near(y, L.cy, L.S * 0.8) and near(x, L.cx + L.gap, L.S * 0.9) then
        mp.commandv("seek", 10, "relative")
        show()
    else
        if hide_timer then hide_timer:kill() end
        set_visible(false)
    end
end, { complex = true })

mp.observe_property("pause", "bool", function() if visible then draw() end end)
"""

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
        try:  # gestures live in the Lua script; a double tap must not leave fullscreen
            os.makedirs(os.path.dirname(INPUT_CONF), exist_ok=True)
            with open(INPUT_CONF, "w", encoding="utf-8") as f:
                f.write("MBTN_LEFT_DBL ignore\n")
            with open(TOUCH_LUA, "w", encoding="utf-8") as f:
                f.write(TOUCH_SCRIPT)
        except OSError:
            pass

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
        videos = Gtk.Button(label="Downloads")
        videos.connect("clicked", self.on_open_videos)
        bar.pack_start(self.entry, True, True, 0)
        bar.pack_start(search, False, False, 0)
        bar.pack_start(videos, False, False, 0)
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
            dl = Gtk.Button(label="Download")
            dl.connect("clicked", self.on_download, e["id"], e.get("title") or e["id"])
            card.pack_start(dl, False, False, 0)
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
            env = dict(os.environ, YT_PLAYER_VIDEOS=VIDEOS, YT_PLAYER_DLFMT=DOWNLOAD_FORMAT)
            self.player = subprocess.Popen(MPV_ARGS + [url], env=env,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            self.show_toast("Could not start mpv: %s" % e)
            return
        self.show_toast("Loading video...")

    # ----- downloads -----
    def on_open_videos(self, _button):
        os.makedirs(VIDEOS, exist_ok=True)
        try:
            Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(VIDEOS, None), None)
        except GLib.Error as e:
            self.show_toast("Could not open %s: %s" % (VIDEOS, e.message))

    def on_download(self, button, vid, title):
        button.set_sensitive(False)
        button.set_label("Downloading...")
        self.show_toast("Downloading: %s" % title[:50], 6)
        threading.Thread(target=self.download_worker, args=(button, vid, title), daemon=True).start()

    def download_worker(self, button, vid, title):
        ok, error = False, ""
        try:
            os.makedirs(VIDEOS, exist_ok=True)
            out = subprocess.run(
                ["yt-dlp", "--no-warnings", "--no-playlist", "-f", DOWNLOAD_FORMAT,
                 "-o", os.path.join(VIDEOS, "%(title).80s [%(id)s].%(ext)s"),
                 "https://www.youtube.com/watch?v=%s" % vid],
                capture_output=True, text=True, timeout=3600)
            ok = out.returncode == 0
            if not ok:
                error = (out.stderr.strip().splitlines() or ["unknown error"])[-1]
        except Exception as e:  # noqa: BLE001 - shown to the user
            error = str(e)
        GLib.idle_add(self.download_done, button, title, ok, error)

    def download_done(self, button, title, ok, error):
        button.set_label("Downloaded" if ok else "Download")
        button.set_sensitive(not ok)
        self.show_toast(("Saved to Videos: %s" % title[:40]) if ok else ("Download failed: %s" % error[:80]), 8)
        return False

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
