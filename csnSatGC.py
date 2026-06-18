#!/usr/bin/env python3
"""
S.A.T. GroundCrew  v3.0
========================
Satellite Antenna Tracker — Ground operations assistant for amateur satellite
station operators.

Author  : Michael Walker · VA3MW · Toronto, Ontario, Canada
Version : 3.0 · 2026-06-18
File    : csnSatGC.py

-------------------------------------------------------------------------------

OVERVIEW
--------
S.A.T. GroundCrew is a single-window Python application that keeps your CSN SAT
antenna controller running unattended between passes and announces upcoming
satellite passes by voice so you never miss a window.

  Wind Tracking   — Automatically points the antenna into the prevailing wind
                    when idle, protecting it from unexpected gusts.
  Voice Alerts    — Announces each approaching satellite pass by name and
                    time-to-AOS via Windows Text-to-Speech.
  SAT Integration — Listens on UDP port 9932 for CSNTracker broadcasts and
                    backs off the moment a pass begins.

FEATURES
--------
  - Auto-discovery: finds the CSN SAT on your LAN automatically via UDP
    broadcast; falls back to a manual IP entry dialog if nothing is heard
    within 30 seconds.
  - Wind-aware positioning: fetches live METAR data from NOAA (falling back to
    VATSIM) and rotates the antenna to face into the wind only when gusts or
    sustained winds exceed configurable thresholds.
  - Satellite-aware backoff: honours SAT,START TRACK / SAT,AOS / SAT,LOS events
    so the antenna is never repositioned during a live pass.
  - Voice pass alerts: spoken announcement ("<name> will be rising in <time>")
    on any SAT,FAOS broadcast within the configurable window (default 5 min to
    AOS); one alert per satellite per pass; announcements are serialised so two
    simultaneous passes never overlap.
  - Mute controls: instant mute/unmute toggle, timed 30-minute mute with
    automatic re-arm, and a Test Voice button to verify your speaker before a pass.
  - Dark theme GUI: live STATUS, WEATHER, and ANTENNA cards with colour-coded
    event log.
  - Keepalive: resends the last commanded azimuth every 60 seconds to hold
    position against mechanical drift.
  - HTTP position poll: polls /track on the CSN SAT every 30 s (60 s while
    tracking) to keep the ANTENNA card live and serve as a fallback LOS detector.
  - Compact mode: collapses to a button-only strip to minimise screen real estate
    during a pass.
  - Desktop shortcut creator: one-click shortcut that handles OneDrive path
    redirection correctly.

REQUIREMENTS
------------
  Python 3.8+   tkinter ships with standard Python on Windows
  requests   →  pip install requests
  Windows TTS   System.Speech via PowerShell — built into Windows 7+,
                no pip package needed.

INSTALLATION
------------
  pip install requests
  python csnSatGC.py

  On first run you will be prompted for:
    1. Your ICAO weather station code (e.g. CYYZ for Toronto Pearson)
    2. The CSN SAT IP address — auto-discovered in most cases; only prompted
       if the LAN scan times out.

CONFIGURATION
-------------
  Settings are stored in csnSatGC.json (same folder as the script) and can
  be changed from the GUI via the ⚙ Settings button.  Defaults:

  SAT_HOST_DEFAULT     xxx.xxx.xxx.xxx  Set to match your S.A.T. IP address
  SAT_PORT             12000            UDP port the SAT accepts PSTRotator commands on
  DISCOVERY_PORT       9932             UDP port CSNTracker broadcasts on
  DISCOVERY_SECS       30               Seconds to wait for auto-discovery before prompting
  INTERVAL_SEC         300              Seconds between automatic wind checks (5 min)
  IDLE_TIMEOUT         300              Seconds with no SAT event before antenna is free
  MIN_GUST_KT          15               Gust threshold in knots — antenna moves only above this
  MIN_WIND_KT          13               Sustained wind threshold used when no gusts reported
  ICAO_DEFAULT         CYYZ             Default ICAO airport code shown in the startup dialog
  ANNOUNCE_WINDOW_SECS 300              Only announce FAOS if timetogo <= this (5 min)
  COOLDOWN_SECS        300              Minimum seconds between repeat announcements per satellite

HOW IT WORKS — WIND TRACKING LOOP
----------------------------------
  Every INTERVAL_SEC seconds the worker thread:
    1. Checks whether the operator has manually paused updates (Pause button / P key)
    2. Checks whether the antenna is in use — a recent SAT,START TRACK / SAT,AOS
       UDP event, or the HTTP poll seeing mode=1
    3. Fetches a fresh METAR from NOAA (tgftp.nws.noaa.gov), falling back to VATSIM
    4. Parses wind direction, speed, and gusts from the dddssGggKT group
    5. Moves the antenna to the wind bearing if gusts exceed MIN_GUST_KT, or
       (when no gusts are reported) sustained wind exceeds MIN_WIND_KT

  A keepalive thread re-sends the last azimuth every 60 seconds to resist drift.

HOW IT WORKS — VOICE ALERT PIPELINE
-------------------------------------
  CSNTracker broadcast:  SAT,FAOS,<name>,<az>,<timetogo>
          |
          |-- timetogo > 300 s? ----------------------->  silent skip
          |
          |-- Voice muted? --------------------------->  silent skip
          |   (cooldown NOT stamped while muted)
          |
          |-- Announced within 5 min? --------------->  silent skip
          |
          +-- Stamp cooldown
              Queue  "<name> will be rising in <time>"
                   |
                   v
              TTS worker thread (serialised)
                   |
                   v
              Windows System.Speech  -->  [speaker]

SATELLITE BACKOFF EVENTS
-------------------------
  SAT,START TRACK,name,catno  Marks antenna IN USE — wind checks skipped
  SAT,AOS,az                  Refreshes IN USE timestamp
  SAT,LOS,az                  Clears IN USE — wind tracking resumes immediately
  SAT,FAOS,name,az,timetogo   Queues a voice announcement (see pipeline above)

  After IDLE_TIMEOUT (5 min) with no new SAT events, the antenna is automatically
  considered free even if a SAT,LOS packet was missed.

PROTOCOLS — PSTRotator (commands sent TO the CSN SAT on UDP port 12000)
------------------------------------------------------------------------
  <PST><AZIMUTH>270.0</AZIMUTH></PST>
  <PST><ELEVATION>0.0</ELEVATION></PST>

PROTOCOLS — CSNTracker (broadcasts received FROM the CSN SAT on UDP port 9932)
-------------------------------------------------------------------------------
  SAT,DISCOVERY,<ip>,<build>,<fw>
  SAT,START TRACK,<name>,<catno>
  SAT,AOS,<az>
  SAT,LOS,<az>
  SAT,FAOS,<name>,<az>,<timetogo>

PROTOCOLS — CSN SAT HTTP API (polled at http://{sat}/track)
------------------------------------------------------------
  mode     int     1 = Tracking a satellite   0 = Idle
  az       float   Rotator azimuth in degrees
  el       float   Rotator elevation in degrees
  satname  string  Currently scheduled satellite name

METAR SOURCES  (tried in order, first success wins)
----------------------------------------------------
  1. https://tgftp.nws.noaa.gov/data/observations/metar/stations/{ICAO}.TXT
  2. https://metar.vatsim.net/{ICAO}

ARCHITECTURE
------------
  Main thread (tkinter event loop)
    |
    |-- _runner_9932      UDP :9932  -- discovery + SAT event dispatch
    |-- _worker           wind tracking loop (METAR fetch -> antenna move)
    |-- _keepalive        resends last azimuth every 60 s
    |-- (no background HTTP poll — mode checked once before each antenna move)
    +-- _tts_worker       serialised TTS queue drain

  All background threads communicate with the GUI exclusively via queue.Queue
  and root.after(0, fn) — no direct widget access from worker threads.

KEYBOARD SHORTCUTS
------------------
  P  —  Pause automatic antenna updates
  R  —  Resume automatic antenna updates

LICENSE
-------
  No open-source license is granted.

  This software is released for personal and amateur radio use only.
  No permission is granted to use, copy, modify, or distribute this
  software for commercial purposes or as part of any commercial product
  or service.

  You are welcome to:
    - Run it for your own amateur radio station
    - Share it within the amateur radio community (with attribution)
    - Fork and adapt it for personal, non-commercial use

  © 2026 Michael Walker VA3MW — All rights reserved.
"""

import json
import math
import pathlib
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.messagebox
import webbrowser
from datetime import datetime

import requests


VERSION = "3.0"

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION  ←  edit these values to match your setup
# ══════════════════════════════════════════════════════════════════════════════

SAT_HOST_DEFAULT = "192.168.113.121"  # Set to match your S.A.T. IP address
SAT_PORT         = 12000   # SAT listens for PSTRotator commands on this port
DISCOVERY_PORT   = 9932    # CSNTracker broadcasts status on this port
DISCOVERY_SECS   = 30      # seconds to wait for a CSNTracker broadcast

INTERVAL_SEC = 300    # seconds between automatic wind checks  (300 = 5 min)
IDLE_TIMEOUT = 300    # seconds of silence before antenna is considered free
MIN_GUST_KT  = 15     # gusts must exceed this (kt) to trigger a move
MIN_WIND_KT  = 13     # sustained wind threshold used when no gusts are reported

ICAO_DEFAULT = "CYYZ" # Default ICAO station code — user is prompted at startup

ANNOUNCE_WINDOW_SECS = 300   # only speak a FAOS alert if timetogo <= 5 min
COOLDOWN_SECS        = 300   # suppress repeat FAOS alert for same bird within 5 min

# ── Persistent configuration ──────────────────────────────────────────────────
# Settings are stored in csnSatGC.json next to the script.
# On first run the file is created from DEFAULTS.  Edit via the GUI Settings
# dialog or directly in the JSON file (restart required for file edits).

CONFIG_PATH = pathlib.Path(__file__).with_suffix(".json")

CFG_DEFAULTS: dict = {
    "sat_host":             "xxx.xxx.xxx.xxx",  # Set to match your S.A.T. IP address
    "sat_port":             12000,
    "discovery_port":       9932,
    "discovery_secs":       30,
    "interval_sec":         300,
    "idle_timeout":         300,
    "min_gust_kt":          15,
    "min_wind_kt":          13,
    "icao":                 "CYYZ",
    "announce_window_secs": 300,
    "cooldown_secs":        300,
    "operator_grid":        "",
}


def _load_cfg() -> dict:
    """Load config from JSON, merging with defaults for any missing keys."""
    cfg = dict(CFG_DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass   # corrupt file — fall back to defaults silently
    return cfg


def _save_cfg(cfg: dict) -> None:
    """Persist config dict to JSON, ignoring unknown keys."""
    try:
        CONFIG_PATH.write_text(
            json.dumps({k: cfg[k] for k in CFG_DEFAULTS if k in cfg}, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass

METAR_SOURCES = [
    "https://tgftp.nws.noaa.gov/data/observations/metar/stations/{icao}.TXT",
    "https://metar.vatsim.net/{icao}",
]

# ══════════════════════════════════════════════════════════════════════════════
#  END OF CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════


# ── Colour palette (dark theme) ───────────────────────────────────────────────
C_WIN    = "#1e1e1e"
C_BG     = "#2b2b2b"
C_PANEL  = "#2d2d2d"
C_HDR    = "#0d2137"
C_BORDER = "#3a3a3a"
C_TEXT   = "#d4d4d4"
C_DIM    = "#6a6a6a"
C_GREEN  = "#4ec94e"
C_RED    = "#e05555"
C_ORANGE = "#e0943a"
C_YELLOW = "#d4c94a"
C_CYAN   = "#4ab8d4"
C_LOGBG  = "#141414"


# ── TTS helpers (module-level, no class dependency) ───────────────────────────

def _time_phrase(seconds: int) -> str:
    """
    Convert an integer number of seconds to a natural spoken phrase.
      123  →  "2 minutes and 3 seconds"
       45  →  "45 seconds"
      300  →  "5 minutes"
    """
    minutes, secs = divmod(seconds, 60)
    parts = []
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    return " and ".join(parts) if parts else "a few moments"


class _TTSSession:
    """
    Persistent PowerShell process with a single long-lived SpeechSynthesizer.

    Spawning a new PowerShell process for every utterance causes Windows to
    repeatedly load and tear down System.Speech DLLs.  Under timing pressure
    this produces error 0xc0000142 (STATUS_DLL_INIT_FAILED) on the next spawn.

    Keeping one process alive eliminates the init/teardown cycle entirely.
    A background reader thread pipes PowerShell stdout into a Queue; speak()
    sends the Speak() command followed by a sentinel line and blocks until
    the sentinel appears (success) or the timeout fires (restart).
    """

    _MARKER = "__SPEAK_DONE__"

    def __init__(self):
        self._proc = None
        self._out_q = queue.Queue()
        self._start()

    def _start(self):
        """(Re)start the PowerShell process and initialise the synthesizer."""
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._out_q = queue.Queue()
        self._proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        # Snapshot proc/queue so the reader thread keeps the right pair
        # even if _start() is called again later.
        proc, q = self._proc, self._out_q
        threading.Thread(target=self._reader, args=(proc, q),
                         daemon=True).start()
        self._write(
            "Add-Type -AssemblyName System.Speech\n"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        )

    def _reader(self, proc, q):
        """Daemon thread — pipes stdout lines into q until the process exits."""
        try:
            for line in proc.stdout:
                q.put(line.rstrip())
        except Exception:
            pass
        q.put(None)   # sentinel: process stdout closed

    def _write(self, cmd: str):
        self._proc.stdin.write(cmd)
        self._proc.stdin.flush()

    def speak(self, text: str, timeout: float = 30.0) -> bool:
        """
        Speak *text* synchronously.  Blocks until done or timeout.
        Returns True on success, False on error/timeout.
        Auto-restarts the PowerShell process if it has died.
        """
        safe = text.replace('"', '').replace("'", '')
        try:
            if self._proc.poll() is not None:
                print("[tts] PowerShell process exited — restarting.")
                self._start()
            self._write(
                f'$s.Speak("{safe}")\n'
                f'Write-Output "{self._MARKER}"\n'
            )
        except Exception as exc:
            print(f"[tts] Write to PowerShell failed: {exc} — restarting.")
            self._start()
            return False

        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                line = self._out_q.get(timeout=remaining)
            except queue.Empty:
                break
            if line is None:              # process ended mid-utterance
                print("[tts] PowerShell exited during Speak — restarting.")
                self._start()
                return False
            if self._MARKER in line:
                return True               # success

        print(f"[tts] Speak timed out after {timeout:.0f} s — restarting.")
        self._start()
        return False


# Module-level singleton — created on first call to _speak().
# Only ever accessed from the _tts_worker thread so no locking needed.
_tts_session = None


def _speak(text: str):
    """Synthesise *text* through the persistent TTS session."""
    global _tts_session
    if _tts_session is None:
        _tts_session = _TTSSession()
    _tts_session.speak(text)


# ══════════════════════════════════════════════════════════════════════════════
#  APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class App:
    """
    All tkinter widget access runs on the main thread.
    Background threads communicate via:
      self._q               — queue of (ts, tag, msg) log entries
      self.root.after(0, f) — schedule a one-shot GUI update on the main thread
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("S.A.T. GroundCrew  —  VA3MW")
        self._cfg = _load_cfg()
        self.root.configure(bg=C_WIN)
        self.root.minsize(900, 640)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Ask for ICAO station code before anything else is built ───────────
        self._icao = self._ask_icao()   # blocks on main thread via wait_window()

        # ── Runtime SAT host (set by discovery or user input) ─────────────────
        self._sat_host = self._cfg["sat_host"]

        # ── Last sent azimuth (int or None) — used by keepalive ───────────────
        self._last_az   = None
        self._at_park   = False   # True while antenna is at park position; keepalive skips
        self._az_lock   = threading.Lock()

        # ── Thread-safe shared state ──────────────────────────────────────────
        self._q             = queue.Queue()
        self._paused        = False
        self._pause_lock    = threading.Lock()
        self._last_cmd_time = 0.0           # epoch of last antenna-use event
        self._cmd_lock      = threading.Lock()
        self._next_check_at = time.time()
        self._wake          = threading.Event()  # set to interrupt worker sleep

        # Discovery sync — runner_9932 sets _discovery_done when it either finds
        # an IP or gives up.  _discovered_ip holds the result (None = not found).
        self._discovery_done = threading.Event()
        self._discovered_ip  = None             # set by runner_9932 on first packet

        # Manual IP dialog sync — worker posts the dialog to the main thread then
        # blocks on _ip_ready until the user clicks Connect.
        self._ip_ready  = threading.Event()
        self._ip_result = self._cfg["sat_host"]

        # ── TTS / FAOS announcement state ─────────────────────────────────────
        self._speech_q       = queue.Queue()
        self._announced      = {}              # { SAT_NAME_UPPER: last_announced_epoch }
        self._ann_lock       = threading.Lock()
        self._tts_muted      = False           # permanent manual mute
        self._tts_mute_until = 0.0             # epoch when timed mute expires (0 = none)
        self._mute_lock      = threading.Lock()
        self._mute_timer_id  = None            # root.after() ID for timed re-arm

        # ── Build UI ──────────────────────────────────────────────────────────
        self._build_ui()
        # Initialise Voice alert badge — armed state is green
        self._l_faos.configure(fg=C_GREEN)
        self._v_faos.set("Armed")

        # ── Start background threads ──────────────────────────────────────────
        # runner_9932   — ONE socket on port 9932 handles both auto-discovery
        #                 and ongoing CSNTracker event monitoring (START TRACK /
        #                 AOS / LOS / FAOS).  Sets _discovery_done when done.
        # worker        — waits for _discovery_done, then runs the wind loop.
        # keepalive     — resends the last azimuth/elevation every 60 s.
        # tts           — drains _speech_q, speaks one announcement at a time.
        threading.Thread(target=self._runner_9932,     daemon=True, name="9932").start()
        threading.Thread(target=self._worker,          daemon=True, name="worker").start()
        threading.Thread(target=self._keepalive,       daemon=True, name="keepalive").start()
        threading.Thread(target=self._tts_worker,      daemon=True, name="tts").start()

        # ── Recurring GUI callbacks ───────────────────────────────────────────
        self._drain_log()   # 100 ms — flush log queue → Text widget
        self._refresh()     # 1 s   — update mode badge + countdown

    # ══════════════════════════════════════════════════════════════════════════
    #  UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self._compact = False   # tracks whether the compact view is active

        # Title bar
        self._bar = tk.Frame(self.root, bg=C_HDR, pady=14)
        self._bar.pack(fill="x")
        bar = self._bar
        tk.Label(bar, text=f"  S.A.T. GroundCrew  v{VERSION}",
                 bg=C_HDR, fg="white",
                 font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Label(bar, text=f"Michael Walker  VA3MW  ",
                 bg=C_HDR, fg="#7aaabf",
                 font=("Segoe UI", 10)).pack(side="right")
        # Compact toggle — ⊟ collapses to button row only, ⊞ restores full view
        self._compact_icon = tk.StringVar(value="⊟")
        tk.Button(bar, textvariable=self._compact_icon,
                  command=self._toggle_compact,
                  bg=C_HDR, fg="#7aaabf",
                  activebackground=C_HDR, activeforeground="white",
                  font=("Segoe UI", 14), relief="flat",
                  cursor="hand2", bd=0, padx=10).pack(side="right")

        # Three info cards
        self._cards_row = tk.Frame(self.root, bg=C_BG)
        self._cards_row.pack(fill="x", padx=12, pady=10)
        row = self._cards_row
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)
        row.columnconfigure(2, weight=1)
        self._build_card_status(row, 0)
        self._build_card_weather(row, 1)
        self._build_card_antenna(row, 2)

        # Divider
        self._divider1 = tk.Frame(self.root, bg=C_BORDER, height=1)
        self._divider1.pack(fill="x", padx=12)

        # Control buttons
        self._btn_row = tk.Frame(self.root, bg=C_BG, pady=8)
        self._btn_row.pack(fill="x", padx=12)
        btn_row = self._btn_row
        self._button(btn_row, "⏸   PAUSE",    "#3d1f00", C_ORANGE,
                     self._do_pause).pack(side="left", padx=(0, 8))
        self._button(btn_row, "▶   RESUME",   "#0f2e0f", C_GREEN,
                     self._do_resume).pack(side="left", padx=(0, 8))
        self._button(btn_row, "🖥  Shortcut",  "#1a1a2e", C_CYAN,
                     self._create_shortcut).pack(side="left")

        # ── Thin vertical rule between antenna controls and voice controls ────
        tk.Frame(btn_row, bg=C_BORDER, width=1).pack(
            side="left", fill="y", padx=16, pady=4)

        # Test voice — always fires regardless of mute state
        self._button(btn_row, "🔊  Test Voice", "#0d2a1a", C_GREEN,
                     self._do_test_voice).pack(side="left", padx=(0, 8))

        # Mute / Unmute toggle — label + colour change with state
        self._btn_mute_var = tk.StringVar(value="🔇  Mute Voice")
        self._btn_mute = tk.Button(
            btn_row, textvariable=self._btn_mute_var,
            command=self._do_mute_toggle,
            bg="#1a2a0a", fg=C_GREEN,
            activebackground="#1a2a0a", activeforeground=C_GREEN,
            font=("Segoe UI", 10, "bold"),
            relief="flat", width=14, pady=7, cursor="hand2", bd=0)
        self._btn_mute.pack(side="left", padx=(0, 8))

        # Timed mute — 30 min then auto re-arm
        self._button(btn_row, "⏱  Mute 30 min", "#2a1a00", C_ORANGE,
                     self._do_mute_30min).pack(side="left")

        # Settings dialog
        tk.Frame(btn_row, bg=C_BORDER, width=1).pack(
            side="left", fill="y", padx=16, pady=4)
        self._button(btn_row, "🎯  Manual",   "#1a2a0a", C_GREEN,
                     self._do_manual_control).pack(side="left", padx=(0, 8))
        self._button(btn_row, "🌐  CSN SAT",  "#0d1f2e", C_CYAN,
                     self._do_open_sat).pack(side="left", padx=(0, 8))
        self._button(btn_row, "⚙  Settings", "#1a1a2a", "#7aaabf",
                     self._do_settings).pack(side="left", padx=(0, 8))

        for key in ("<p>", "<P>"):
            self.root.bind(key, lambda _: self._do_pause())
        for key in ("<r>", "<R>"):
            self.root.bind(key, lambda _: self._do_resume())

        # ── Compact button bar (hidden in full mode) ──────────────────────────
        # Shown instead of _bar + _btn_row when compact mode is active.
        # Three buttons only: pause/resume toggle · mute · mute-30.
        self._compact_bar = tk.Frame(self.root, bg=C_BG, pady=4)
        # (not packed — shown only when compact)

        self._compact_pause_var = tk.StringVar(value="⏸   PAUSE")
        self._compact_pause_btn = tk.Button(
            self._compact_bar,
            textvariable=self._compact_pause_var,
            command=self._do_pause_resume_toggle,
            bg="#3d1f00", fg=C_ORANGE,
            activebackground="#3d1f00", activeforeground=C_ORANGE,
            font=("Segoe UI", 10, "bold"),
            relief="flat", pady=8, cursor="hand2", bd=0)
        self._compact_pause_btn.pack(side="left", expand=True, fill="x", padx=(0, 2))

        # Mute toggle — shares _btn_mute_var so text stays in sync with full button
        tk.Button(
            self._compact_bar,
            textvariable=self._btn_mute_var,
            command=self._do_mute_toggle,
            bg="#1a2a0a", fg=C_GREEN,
            activebackground="#1a2a0a", activeforeground=C_GREEN,
            font=("Segoe UI", 10, "bold"),
            relief="flat", pady=8, cursor="hand2", bd=0
        ).pack(side="left", expand=True, fill="x", padx=(0, 2))

        tk.Button(
            self._compact_bar,
            text="⏱  Mute 30",
            command=self._do_mute_30min,
            bg="#2a1a00", fg=C_ORANGE,
            activebackground="#2a1a00", activeforeground=C_ORANGE,
            font=("Segoe UI", 10, "bold"),
            relief="flat", pady=8, cursor="hand2", bd=0
        ).pack(side="left", expand=True, fill="x")

        # Restore button — the ⊟ icon lives in _bar which is hidden in compact mode,
        # so we need a ⊞ here to get back to the full view.
        tk.Button(
            self._compact_bar,
            textvariable=self._compact_icon,
            command=self._toggle_compact,
            bg=C_BG, fg="#7aaabf",
            activebackground=C_BG, activeforeground="white",
            font=("Segoe UI", 13), relief="flat",
            cursor="hand2", bd=0, padx=6
        ).pack(side="right")

        # Divider
        self._divider2 = tk.Frame(self.root, bg=C_BORDER, height=1)
        self._divider2.pack(fill="x", padx=12)

        # Event log
        self._log_frame = tk.Frame(self.root, bg=C_BG)
        self._log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        log_frame = self._log_frame
        tk.Label(log_frame, text="  EVENT LOG",
                 bg=C_HDR, fg=C_DIM,
                 font=("Segoe UI", 8, "bold"),
                 anchor="w", pady=4).pack(fill="x")
        inner = tk.Frame(log_frame, bg=C_LOGBG)
        inner.pack(fill="both", expand=True)
        self._log_box = tk.Text(
            inner, bg=C_LOGBG, fg=C_TEXT,
            font=self._mono_font(9),
            wrap="none", state="disabled",
            relief="flat", padx=8, pady=6)
        self._log_box.pack(side="left", fill="both", expand=True)
        vsb = tk.Scrollbar(inner, orient="vertical", command=self._log_box.yview)
        vsb.pack(side="right", fill="y")
        self._log_box.configure(yscrollcommand=vsb.set)

        self._log_box.tag_config("info",     foreground=C_TEXT)
        self._log_box.tag_config("move",     foreground=C_GREEN)
        self._log_box.tag_config("skip",     foreground=C_DIM)
        self._log_box.tag_config("warn",     foreground=C_ORANGE)
        self._log_box.tag_config("error",    foreground=C_RED)
        self._log_box.tag_config("startup",  foreground=C_CYAN)
        self._log_box.tag_config("listen",   foreground="#6a9fbf")
        self._log_box.tag_config("discover", foreground="#c084fc")
        self._log_box.tag_config("tx",       foreground="#8888cc")
        self._log_box.tag_config("sat",      foreground="#f0a050")  # CSNTracker events
        self._log_box.tag_config("faos",     foreground="#e0c060")  # FAOS / TTS events

    def _toggle_compact(self):
        """
        Compact mode: hides the app title bar, cards, log, and full button row;
        shows a slim 300×50 strip with just Pause/Resume toggle · Mute · Mute 30.
        ⊞ restores the full window.
        """
        if not self._compact:
            # ── Go compact ────────────────────────────────────────────────────
            self._saved_geometry = self.root.geometry()
            self._bar.pack_forget()
            self._cards_row.pack_forget()
            self._divider1.pack_forget()
            self._btn_row.pack_forget()
            self._divider2.pack_forget()
            self._log_frame.pack_forget()
            self._compact_bar.pack(fill="x")
            self._compact_icon.set("⊞")
            self.root.minsize(0, 0)
            self.root.geometry("300x50")
            self._compact = True
        else:
            # ── Restore full view ─────────────────────────────────────────────
            self._compact_bar.pack_forget()
            self._bar.pack(fill="x")
            self._cards_row.pack(fill="x", padx=12, pady=10)
            self._divider1.pack(fill="x", padx=12)
            self._btn_row.pack(fill="x", padx=12)
            self._divider2.pack(fill="x", padx=12)
            self._log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            self._compact_icon.set("⊟")
            self.root.minsize(900, 640)
            self.root.geometry(self._saved_geometry)
            self._compact = False

    # ── Card / field helpers ──────────────────────────────────────────────────

    def _mono_font(self, size: int):
        for name in ("Cascadia Code", "Consolas", "Courier New"):
            try:
                if name.lower() in [f.lower() for f in tk.font.families()]:
                    return (name, size)
            except Exception:
                pass
        return ("Courier New", size)

    def _card(self, parent, title: str, col: int) -> tk.Frame:
        outer = tk.Frame(parent, bg=C_PANEL,
                         highlightthickness=1, highlightbackground=C_BORDER)
        outer.grid(row=0, column=col, sticky="nsew", padx=5)
        tk.Label(outer, text=f"  {title}",
                 bg=C_HDR, fg="#aac8df",
                 font=("Segoe UI", 9, "bold"),
                 anchor="w", pady=6).pack(fill="x")
        body = tk.Frame(outer, bg=C_PANEL, padx=14, pady=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        return body

    def _field(self, parent, label: str, row: int, init: str = "—"):
        tk.Label(parent, text=label, bg=C_PANEL, fg=C_DIM,
                 font=("Segoe UI", 9), anchor="w"
                 ).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 2))
        var = tk.StringVar(value=init)
        lbl = tk.Label(parent, textvariable=var, bg=C_PANEL, fg=C_TEXT,
                       font=self._mono_font(10), anchor="w")
        lbl.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=4)
        return var, lbl

    def _button(self, parent, text, bg, fg, cmd):
        return tk.Button(parent, text=text, command=cmd,
                         bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                         font=("Segoe UI", 10, "bold"),
                         relief="flat", width=13, pady=7, cursor="hand2", bd=0)

    def _build_card_status(self, parent, col):
        c = self._card(parent, "STATUS", col)
        self._v_sat,       self._l_sat       = self._field(c, "CSN SAT",     0, "Discovering…")
        self._v_mode,      self._l_mode      = self._field(c, "Mode",        1)
        self._v_interval,  _                 = self._field(c, "Interval",    2, f"{self._cfg['interval_sec']//60} min")
        self._v_idle,      _                 = self._field(c, "Idle guard",  3, f"{self._cfg['idle_timeout']//60} min")
        self._v_gust_thr,  _                 = self._field(c, "Gust min",    4,
                                                            f"{self._cfg['min_gust_kt']} kt  /  {self._cfg['min_wind_kt']} kt wind")
        self._v_next,      _                 = self._field(c, "Next check",  5)
        self._v_sat_event, self._l_sat_event = self._field(c, "SAT event",   6)
        self._v_faos,      self._l_faos      = self._field(c, "Voice alert", 7, "Armed")

    def _build_card_weather(self, parent, col):
        c = self._card(parent, f"WEATHER  ({self._icao})", col)
        self._v_metar, _            = self._field(c, "METAR",     0)
        self._v_wdir,  self._l_wdir = self._field(c, "Direction", 1)
        self._v_wspd,  _            = self._field(c, "Speed",     2)
        self._v_wgst,  self._l_wgst = self._field(c, "Gusts",     3)
        self._v_wtime, _            = self._field(c, "Updated",   4)

    def _build_card_antenna(self, parent, col):
        c = self._card(parent, "ANTENNA", col)
        self._v_az,     self._l_az     = self._field(c, "Azimuth",     0)
        self._v_el,     _              = self._field(c, "Elevation",   1, "0.0°")
        self._v_moved,  _              = self._field(c, "Last moved",  2, "Never")
        self._v_action, self._l_action = self._field(c, "Last action", 3)

    # ══════════════════════════════════════════════════════════════════════════
    #  GRID SQUARE HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _grid_to_latlon(grid: str) -> tuple:
        """Convert a 4- or 6-character Maidenhead locator to (lat, lon) centre."""
        g = grid.upper().strip()
        if len(g) < 4:
            raise ValueError("need at least 4 characters")
        if not (g[0].isalpha() and g[1].isalpha()):
            raise ValueError("first two characters must be letters (field)")
        if not (g[2].isdigit() and g[3].isdigit()):
            raise ValueError("third and fourth characters must be digits (square)")
        lon = (ord(g[0]) - ord('A')) * 20 - 180
        lat = (ord(g[1]) - ord('A')) * 10 - 90
        lon += int(g[2]) * 2
        lat += int(g[3])
        if len(g) >= 6:
            if not (g[4].isalpha() and g[5].isalpha()):
                raise ValueError("fifth and sixth characters must be letters (subsquare)")
            lon += (ord(g[4].lower()) - ord('a')) * (5 / 60)
            lat += (ord(g[5].lower()) - ord('a')) * (2.5 / 60)
            lon += 2.5 / 60    # centre of subsquare
            lat += 1.25 / 60
        else:
            lon += 1.0         # centre of square
            lat += 0.5
        return lat, lon

    @staticmethod
    def _calc_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Return the initial great-circle bearing (°, 0–360) from point 1 to point 2."""
        φ1 = math.radians(lat1)
        φ2 = math.radians(lat2)
        Δλ = math.radians(lon2 - lon1)
        x = math.sin(Δλ) * math.cos(φ2)
        y = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)
        return (math.degrees(math.atan2(x, y)) + 360) % 360

    # ══════════════════════════════════════════════════════════════════════════
    #  MANUAL CONTROL DIALOG
    # ══════════════════════════════════════════════════════════════════════════

    def _do_manual_control(self):
        """
        Modal dialog for one-shot manual antenna positioning.

        Three ways to set azimuth:
          1. Click or drag on the compass rose.
          2. Type a bearing (0–360°) directly.
          3. Enter home + target Maidenhead grid squares → bearing is calculated
             and fed back to the compass and entry field.

        Clicking "Point Antenna" sends an immediate PSTRotator command, updates
        _last_az so the keepalive holds the position, and stamps _last_cmd_time
        so the automatic wind-tracking loop backs off for idle_timeout seconds.
        """
        dlg = tk.Toplevel(self.root)
        dlg.title("Manual Antenna Control")
        dlg.configure(bg=C_BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()

        az_var = tk.DoubleVar(value=0.0)

        # ── Compass canvas ────────────────────────────────────────────────────
        CX, CY, R = 120, 120, 100
        SIZE = 240

        compass_frame = tk.Frame(dlg, bg=C_BG)
        compass_frame.pack(side="left", padx=(16, 8), pady=16, anchor="n")
        tk.Label(compass_frame, text="COMPASS", bg=C_BG, fg=C_DIM,
                 font=("Segoe UI", 8, "bold")).pack(pady=(0, 4))

        canvas = tk.Canvas(compass_frame, width=SIZE, height=SIZE,
                           bg=C_PANEL,
                           highlightthickness=1, highlightbackground=C_BORDER)
        canvas.pack()

        def _draw_compass(az=None):
            canvas.delete("all")
            canvas.create_oval(CX - R, CY - R, CX + R, CY + R,
                               outline=C_BORDER, width=2)
            for deg in range(0, 360, 5):
                rad = math.radians(deg)
                inner = R - (14 if deg % 90 == 0 else 8 if deg % 30 == 0
                             else 5 if deg % 10 == 0 else 3)
                x1 = CX + inner * math.sin(rad)
                y1 = CY - inner * math.cos(rad)
                x2 = CX + R * math.sin(rad)
                y2 = CY - R * math.cos(rad)
                w = 2 if deg % 90 == 0 else 1
                col = C_TEXT if deg % 90 == 0 else C_DIM
                canvas.create_line(x1, y1, x2, y2, fill=col, width=w)
            for label, deg in [("N", 0), ("E", 90), ("S", 180), ("W", 270)]:
                rad = math.radians(deg)
                x = CX + (R - 22) * math.sin(rad)
                y = CY - (R - 22) * math.cos(rad)
                col = C_RED if label == "N" else C_TEXT
                canvas.create_text(x, y, text=label, fill=col,
                                   font=("Segoe UI", 10, "bold"))
            for deg in range(30, 360, 30):
                if deg % 90 == 0:
                    continue
                rad = math.radians(deg)
                x = CX + (R - 18) * math.sin(rad)
                y = CY - (R - 18) * math.cos(rad)
                canvas.create_text(x, y, text=str(deg), fill=C_DIM,
                                   font=("Segoe UI", 7))
            canvas.create_oval(CX - 3, CY - 3, CX + 3, CY + 3,
                               fill=C_DIM, outline="")
            if az is not None:
                rad = math.radians(az)
                ex = CX + (R - 10) * math.sin(rad)
                ey = CY - (R - 10) * math.cos(rad)
                canvas.create_line(CX, CY, ex, ey,
                                   fill=C_CYAN, width=2,
                                   arrow="last", arrowshape=(10, 12, 4))
                canvas.create_text(CX, CY + 20, text=f"{az:.1f}°",
                                   fill=C_CYAN,
                                   font=("Segoe UI", 11, "bold"))

        _draw_compass(0.0)

        def _on_compass_click(event):
            dx, dy = event.x - CX, event.y - CY
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < 8 or dist > R + 12:
                return
            az = (math.degrees(math.atan2(dx, -dy)) + 360) % 360
            az = round(az, 1)
            az_var.set(az)
            _az_entry_var.set(f"{az:.1f}")
            _draw_compass(az)

        canvas.bind("<Button-1>", _on_compass_click)
        canvas.bind("<B1-Motion>", _on_compass_click)

        # ── Right panel ───────────────────────────────────────────────────────
        right = tk.Frame(dlg, bg=C_BG)
        right.pack(side="left", padx=(8, 16), pady=16, fill="both", expand=True)

        # Heading entry
        tk.Frame(right, bg=C_HDR).pack(fill="x")
        hdr = tk.Frame(right, bg=C_HDR)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  BEAM HEADING", bg=C_HDR, fg="#aac8df",
                 font=("Segoe UI", 9, "bold")).pack(side="left", pady=4)

        head_body = tk.Frame(right, bg=C_PANEL, padx=14, pady=12)
        head_body.pack(fill="x")

        tk.Label(head_body, text="Azimuth:", bg=C_PANEL, fg=C_DIM,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w",
                                            padx=(0, 8))
        _az_entry_var = tk.StringVar(value="0.0")
        az_entry = tk.Entry(head_body, textvariable=_az_entry_var,
                            bg=C_BG, fg=C_TEXT, insertbackground=C_TEXT,
                            font=("Segoe UI", 14, "bold"), width=7,
                            relief="flat", justify="center")
        az_entry.grid(row=0, column=1, sticky="w")
        tk.Label(head_body, text="°", bg=C_PANEL, fg=C_TEXT,
                 font=("Segoe UI", 14)).grid(row=0, column=2, sticky="w",
                                             padx=(2, 0))

        def _on_az_entry(*_):
            try:
                az = float(_az_entry_var.get())
                az = az % 360
                az_var.set(az)
                _draw_compass(az)
            except ValueError:
                pass

        _az_entry_var.trace_add("write", _on_az_entry)

        # Grid square section
        tk.Frame(right, bg=C_BORDER, height=1).pack(fill="x", pady=(10, 0))
        grid_hdr = tk.Frame(right, bg=C_HDR)
        grid_hdr.pack(fill="x")
        tk.Label(grid_hdr, text="  GRID SQUARE → BEARING", bg=C_HDR,
                 fg="#aac8df",
                 font=("Segoe UI", 9, "bold")).pack(side="left", pady=4)

        grid_body = tk.Frame(right, bg=C_PANEL, padx=14, pady=10)
        grid_body.pack(fill="x")
        grid_body.columnconfigure(1, weight=1)

        tk.Label(grid_body, text="My Grid:", bg=C_PANEL, fg=C_TEXT,
                 font=("Segoe UI", 9, "bold"), width=11,
                 anchor="w").grid(row=0, column=0, sticky="w", pady=3)
        home_grid_var = tk.StringVar(value=self._cfg.get("operator_grid", ""))
        home_entry = tk.Entry(grid_body, textvariable=home_grid_var,
                              bg="#3c3c3c", fg=C_TEXT, insertbackground=C_TEXT,
                              font=self._mono_font(11), width=9, relief="flat",
                              highlightthickness=1,
                              highlightbackground=C_CYAN,
                              highlightcolor=C_CYAN)
        home_entry.grid(row=0, column=1, sticky="w", padx=(4, 0), pady=3)

        tk.Label(grid_body, text="Target Grid:", bg=C_PANEL, fg=C_TEXT,
                 font=("Segoe UI", 9, "bold"), width=11,
                 anchor="w").grid(row=1, column=0, sticky="w", pady=3)
        target_grid_var = tk.StringVar()
        target_entry = tk.Entry(grid_body, textvariable=target_grid_var,
                                bg="#3c3c3c", fg=C_TEXT, insertbackground=C_TEXT,
                                font=self._mono_font(11), width=9, relief="flat",
                                highlightthickness=1,
                                highlightbackground=C_CYAN,
                                highlightcolor=C_CYAN)
        target_entry.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=3)

        bearing_var = tk.StringVar(value="—")
        bearing_lbl = tk.Label(grid_body, textvariable=bearing_var,
                               bg=C_PANEL, fg=C_CYAN,
                               font=self._mono_font(11))
        bearing_lbl.grid(row=2, column=0, columnspan=2, sticky="w",
                         pady=(6, 0))

        grid_err_var = tk.StringVar()
        tk.Label(grid_body, textvariable=grid_err_var, bg=C_PANEL, fg=C_RED,
                 font=("Segoe UI", 8)
                 ).grid(row=3, column=0, columnspan=2, sticky="w")

        def _calc_grid():
            grid_err_var.set("")
            home   = home_grid_var.get().strip()
            target = target_grid_var.get().strip()
            try:
                hlat, hlon = self._grid_to_latlon(home)
            except Exception as exc:
                grid_err_var.set(f"My grid: {exc}")
                return
            try:
                tlat, tlon = self._grid_to_latlon(target)
            except Exception as exc:
                grid_err_var.set(f"Target grid: {exc}")
                return
            brg = round(self._calc_bearing(hlat, hlon, tlat, tlon), 1)
            bearing_var.set(f"Bearing:  {brg}°")
            az_var.set(brg)
            _az_entry_var.set(f"{brg:.1f}")
            _draw_compass(brg)
            self._cfg["operator_grid"] = home.upper()
            _save_cfg(self._cfg)

        tk.Button(grid_body, text="Calculate Bearing",
                  command=_calc_grid,
                  bg="#1a1a2e", fg=C_CYAN,
                  activebackground="#1a1a2e", activeforeground=C_CYAN,
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", pady=5, cursor="hand2", bd=0
                  ).grid(row=4, column=0, columnspan=2, sticky="ew",
                         pady=(10, 0))

        home_entry.bind("<Return>",   lambda _: _calc_grid())
        target_entry.bind("<Return>", lambda _: _calc_grid())

        # ── Bottom action row ─────────────────────────────────────────────────
        tk.Frame(dlg, bg=C_BORDER, height=1).pack(fill="x", pady=(8, 0))
        btn_frame = tk.Frame(dlg, bg=C_BG, pady=10)
        btn_frame.pack(fill="x", padx=16)

        status_var = tk.StringVar()
        tk.Label(btn_frame, textvariable=status_var,
                 bg=C_BG, fg=C_GREEN,
                 font=("Segoe UI", 9)).pack(pady=(0, 6))

        def _point():
            az = az_var.get()
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
                    for inner in ("<ELEVATION>0.0</ELEVATION>",
                                  f"<AZIMUTH>{az:.1f}</AZIMUTH>"):
                        payload = f"<PST>{inner}</PST>"
                        tx.sendto(payload.encode("ascii"),
                                  (self._sat_host, self._cfg["sat_port"]))
                with self._az_lock:
                    self._last_az = int(round(az))
                    self._at_park = False
                with self._cmd_lock:
                    self._last_cmd_time = time.time()
                self._log("INFO", f"[manual] Operator commanded azimuth {az:.1f}°")

                def _ui():
                    self._v_az.set(f"{az:.1f}°")
                    self._l_az.configure(fg=C_CYAN)
                    self._v_moved.set(datetime.now().strftime("%H:%M:%S"))
                    self._v_action.set(f"MANUAL → {az:.1f}°")
                    self._l_action.configure(fg=C_CYAN)
                self.root.after(0, _ui)
                status_var.set(f"✓  Antenna commanded to {az:.1f}°")
            except Exception as exc:
                self._log("ERROR", f"[manual] Send failed: {exc}")
                status_var.set(f"Error: {exc}")

        tk.Button(btn_frame, text="⟳  Point Antenna",
                  command=_point,
                  bg="#0d2a1a", fg=C_GREEN,
                  activebackground="#0d2a1a", activeforeground=C_GREEN,
                  font=("Segoe UI", 11, "bold"),
                  relief="flat", pady=8, cursor="hand2", bd=0,
                  width=20).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="Close",
                  command=dlg.destroy,
                  bg=C_PANEL, fg=C_DIM,
                  activebackground=C_PANEL, activeforeground=C_TEXT,
                  font=("Segoe UI", 10),
                  relief="flat", pady=8, cursor="hand2", bd=0,
                  width=8).pack(side="left")

    # ══════════════════════════════════════════════════════════════════════════
    #  RECURRING GUI CALLBACKS
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh(self):
        with self._pause_lock:
            paused = self._paused
        with self._cmd_lock:
            idle = time.time() - self._last_cmd_time

        if paused:
            self._v_mode.set("⏸  PAUSED")
            self._l_mode.configure(fg=C_ORANGE)
            self._compact_pause_var.set("▶   RESUME")
            self._compact_pause_btn.configure(
                bg="#0f2e0f", fg=C_GREEN,
                activebackground="#0f2e0f", activeforeground=C_GREEN)
        elif self._last_cmd_time > 0 and idle < self._cfg["idle_timeout"]:
            self._v_mode.set("⏳  ANTENNA IN USE")
            self._l_mode.configure(fg=C_CYAN)
            self._compact_pause_var.set("⏸   PAUSE")
            self._compact_pause_btn.configure(
                bg="#3d1f00", fg=C_ORANGE,
                activebackground="#3d1f00", activeforeground=C_ORANGE)
        else:
            self._v_mode.set("●  RUNNING")
            self._l_mode.configure(fg=C_GREEN)
            self._compact_pause_var.set("⏸   PAUSE")
            self._compact_pause_btn.configure(
                bg="#3d1f00", fg=C_ORANGE,
                activebackground="#3d1f00", activeforeground=C_ORANGE)

        secs_left = max(0, int(self._next_check_at - time.time()))
        m, s = divmod(secs_left, 60)
        self._v_next.set(f"{m:02d}:{s:02d}")
        self.root.after(1000, self._refresh)

    def _drain_log(self):
        try:
            while True:
                ts, tag, msg = self._q.get_nowait()
                self._log_box.configure(state="normal")
                self._log_box.insert("end", f"{ts}  {msg}\n", tag)
                self._log_box.see("end")
                self._log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log)

    # ══════════════════════════════════════════════════════════════════════════
    #  THREAD-SAFE HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _log(self, level: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        if   "MOVING"      in msg:  tag = "move"
        elif "SKIPPED"    in msg:  tag = "skip"
        elif "TX →"       in msg:  tag = "tx"
        elif "[keepalive]"in msg:  tag = "tx"
        elif "[discover]" in msg:  tag = "discover"
        elif "[startup]"  in msg:  tag = "startup"
        elif "[faos]"     in msg:  tag = "faos"
        elif "[sat]"      in msg:  tag = "sat"
        elif "[listener]" in msg:  tag = "listen"
        elif level == "WARNING":   tag = "warn"
        elif level == "ERROR":     tag = "error"
        else:                      tag = "info"
        self._q.put((ts, tag, msg))
        print(f"{ts}  {level:<7}  {msg}")

    def _ui_sat(self, online: bool):
        def _f():
            label = f"●  {self._sat_host}  ONLINE" if online \
                else f"●  {self._sat_host}  OFFLINE"
            self._v_sat.set(label)
            self._l_sat.configure(fg=C_GREEN if online else C_RED)
        self.root.after(0, _f)

    def _ui_sat_host_discovered(self, ip: str):
        """Update the STATUS card to show the newly discovered SAT IP."""
        def _f():
            self._v_sat.set(f"●  {ip}  (discovered)")
            self._l_sat.configure(fg=C_CYAN)
        self.root.after(0, _f)

    def _ui_sat_event(self, text: str, colour: str):
        def _f():
            self._v_sat_event.set(text)
            self._l_sat_event.configure(fg=colour)
        self.root.after(0, _f)

    def _ui_faos_alert(self, text: str, colour: str):
        """Update the Voice alert row in the STATUS card."""
        def _f():
            self._v_faos.set(text)
            self._l_faos.configure(fg=colour)
        self.root.after(0, _f)

    def _ui_weather(self, raw: str, wdir: int, wspd: int, wgst):
        def _f():
            self._v_metar.set(raw if len(raw) <= 46 else raw[:43] + "…")
            self._v_wdir.set(f"{wdir}°")
            self._v_wspd.set(f"{wspd} kt")
            self._v_wtime.set(datetime.now().strftime("%H:%M:%S"))
            if wgst:
                self._v_wgst.set(f"{wgst} kt")
                self._l_wgst.configure(fg=C_RED if wgst > self._cfg["min_gust_kt"] else C_YELLOW)
            else:
                self._v_wgst.set("none reported")
                self._l_wgst.configure(fg=C_DIM)
        self.root.after(0, _f)

    def _ui_moved(self, wdir: int):
        def _f():
            self._v_az.set(f"{wdir}.0°")
            self._l_az.configure(fg=C_GREEN)
            self._v_moved.set(datetime.now().strftime("%H:%M:%S"))
            self._v_action.set("MOVED")
            self._l_action.configure(fg=C_GREEN)
        self.root.after(0, _f)

    def _ui_live_position(self, az: float, el: float, tracking: bool):
        """Update the ANTENNA card with the live position polled from the SAT."""
        def _f():
            self._v_az.set(f"{az:.1f}°")
            self._l_az.configure(fg=C_CYAN if tracking else C_TEXT)
            self._v_el.set(f"{el:.1f}°")
        self.root.after(0, _f)

    def _ui_skipped(self, reason: str):
        def _f():
            self._v_action.set(f"SKIPPED  ({reason})")
            self._l_action.configure(fg=C_DIM)
        self.root.after(0, _f)

    def _ui_parked(self, az: float):
        def _f():
            self._v_az.set(f"{az:.1f}°")
            self._l_az.configure(fg=C_YELLOW)
            self._v_moved.set(datetime.now().strftime("%H:%M:%S"))
            self._v_action.set(f"PARK → {az:.1f}°")
            self._l_action.configure(fg=C_YELLOW)
        self.root.after(0, _f)

    def _ask_icao(self) -> str:
        """
        Modal startup dialog — asks the user for their ICAO weather station code
        before the main UI is built.  Blocks the main thread via wait_window().
        Returns the validated (uppercased) code, or ICAO_DEFAULT if left blank.
        """
        result = [self._cfg["icao"]]

        self.root.withdraw()            # hide main window while dialog is open

        dlg = tk.Toplevel(self.root)
        dlg.title("Weather Station Setup")
        dlg.configure(bg=C_BG)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()

        tk.Label(dlg,
                 text="Enter the ICAO code for your nearest airport weather station:",
                 bg=C_BG, fg=C_TEXT,
                 font=("Segoe UI", 10),
                 justify="left").pack(padx=28, pady=(22, 6), anchor="w")

        entry = tk.Entry(dlg, bg=C_PANEL, fg=C_TEXT,
                         font=self._mono_font(14),
                         insertbackground=C_TEXT,
                         relief="flat", width=10, justify="center")
        entry.insert(0, self._cfg["icao"])
        entry.pack(padx=28, pady=6)
        entry.focus_set()
        entry.select_range(0, "end")

        tk.Label(dlg,
                 text="Not sure? Look up your airport code here:",
                 bg=C_BG, fg=C_DIM,
                 font=("Segoe UI", 9)).pack(padx=28, pady=(12, 2), anchor="w")

        link = tk.Label(dlg,
                        text="  ourairports.com  →  search by city or airport name",
                        bg=C_BG, fg=C_CYAN,
                        font=("Segoe UI", 9, "underline"),
                        cursor="hand2")
        link.pack(padx=28, pady=(0, 18), anchor="w")
        link.bind("<Button-1>",
                  lambda _: webbrowser.open("https://ourairports.com"))

        def _ok():
            val = entry.get().strip().upper()
            result[0] = val if val else self._cfg["icao"]
            dlg.destroy()

        tk.Button(dlg, text="OK — Start Tracking",
                  bg="#0f2e0f", fg=C_GREEN,
                  font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=20, pady=6,
                  command=_ok).pack(pady=(0, 22))

        entry.bind("<Return>", lambda _: _ok())
        dlg.protocol("WM_DELETE_WINDOW", _ok)   # close = accept current value

        dlg.wait_window()
        self.root.deiconify()           # restore main window after dialog closes
        return result[0]

    def _show_ip_dialog(self):
        """
        Show a modal dark-themed dialog asking the user to enter the CSN SAT IP.
        Called on the main thread via root.after().  Signals _ip_ready when done.
        """
        dlg = tk.Toplevel(self.root)
        dlg.title("CSN SAT Not Found")
        dlg.configure(bg=C_BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()

        tk.Label(dlg,
                 text="No CSN SAT found on the network.\n"
                      "Enter the IP address manually:",
                 bg=C_BG, fg=C_TEXT,
                 font=("Segoe UI", 10),
                 justify="left").pack(padx=24, pady=(20, 6))

        entry = tk.Entry(dlg, bg=C_PANEL, fg=C_TEXT,
                         font=self._mono_font(12),
                         insertbackground=C_TEXT,
                         relief="flat", width=20, justify="center")
        entry.insert(0, self._cfg["sat_host"])
        entry.pack(padx=24, pady=6)
        entry.focus_set()
        entry.select_range(0, "end")

        tk.Label(dlg, text="(Leave blank or press Cancel to use the default)",
                 bg=C_BG, fg=C_DIM,
                 font=("Segoe UI", 8)).pack(padx=24)

        def _ok():
            ip = entry.get().strip()
            self._ip_result = ip if ip else self._cfg["sat_host"]
            dlg.destroy()
            self._ip_ready.set()

        def _cancel():
            self._ip_result = self._cfg["sat_host"]
            dlg.destroy()
            self._ip_ready.set()

        tk.Button(dlg, text="Connect",
                  bg="#0f2e0f", fg=C_GREEN,
                  font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=20, pady=6,
                  command=_ok).pack(pady=(10, 20))

        entry.bind("<Return>", lambda _: _ok())
        dlg.protocol("WM_DELETE_WINDOW", _cancel)

    # ══════════════════════════════════════════════════════════════════════════
    #  BUTTON / KEY HANDLERS
    # ══════════════════════════════════════════════════════════════════════════

    def _do_pause_resume_toggle(self):
        """Single toggle used by the compact button bar."""
        with self._pause_lock:
            paused = self._paused
        if paused:
            self._do_resume()
        else:
            self._do_pause()

    def _do_pause(self):
        with self._pause_lock:
            self._paused = True
        self._log("INFO", "[control] PAUSED — automatic updates suspended.  Press R to resume.")

    def _do_resume(self):
        with self._pause_lock:
            self._paused = False
        self._log("INFO", "[control] RESUMED — automatic updates re-enabled.")
        self._wake.set()

    def _create_shortcut(self):
        """Create a desktop shortcut using PowerShell — handles OneDrive redirection."""
        import os
        script  = os.path.abspath(__file__)
        workdir = os.path.dirname(script)
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.isfile(pythonw):
            pythonw = "pythonw.exe"

        ps = (
            '$desktop = [Environment]::GetFolderPath("Desktop");'
            '$lnk = Join-Path $desktop "SAT GroundCrew.lnk";'
            f'$s = (New-Object -COM WScript.Shell).CreateShortcut($lnk);'
            f'$s.TargetPath = "{pythonw}";'
            f'$s.Arguments = \'"{script}"\';'
            f'$s.WorkingDirectory = "{workdir}";'
            f'$s.Description = "S.A.T. GroundCrew - VA3MW";'
            f'$s.Save();'
            f'Write-Output $lnk'
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                check=True, capture_output=True, text=True)
            lnk_path = result.stdout.strip()
            self._log("INFO", f"[shortcut] Desktop shortcut created → {lnk_path}")
            tk.messagebox.showinfo("Shortcut Created",
                f"Desktop shortcut created successfully.\n\n{lnk_path}")
        except subprocess.CalledProcessError as exc:
            err = exc.stderr.strip()
            self._log("ERROR", f"[shortcut] Failed: {err}")
            tk.messagebox.showerror("Shortcut Failed",
                f"Could not create shortcut:\n\n{err}")

    # ── Voice alert controls ──────────────────────────────────────────────────

    def _do_test_voice(self):
        """
        Queue a test TTS announcement that plays regardless of mute state.
        Lets the operator verify the speaker / volume before a pass begins.
        """
        self._speech_q.put((time.time(), "Voice alert test.  This is working correctly."))
        self._log("INFO", "[tts] Test voice queued — bypasses mute.")

    def _do_mute_toggle(self):
        """
        Toggle between armed and permanently muted.
        If a timed 30-minute mute is active, clicking this cancels the timer
        and either arms (if previously armed) or mutes permanently.
        """
        with self._mute_lock:
            timed_active = (self._tts_mute_until > 0
                            and time.time() < self._tts_mute_until)
            currently_muted = self._tts_muted or timed_active
            if currently_muted:
                self._tts_muted      = False
                self._tts_mute_until = 0.0
                new_muted = False
            else:
                self._tts_muted = True
                new_muted       = True

        # Cancel any pending timed re-arm callback
        if self._mute_timer_id is not None:
            self.root.after_cancel(self._mute_timer_id)
            self._mute_timer_id = None

        self._update_mute_ui(new_muted, timed=False)
        action = "MUTED (manual)" if new_muted else "UNMUTED — armed"
        self._log("INFO", f"[tts] Voice alerts {action}.")

    def _do_mute_30min(self):
        """
        Mute voice alerts for 30 minutes, then automatically re-arm.
        Cancels any existing timed mute and resets the 30-minute clock.
        """
        expire = time.time() + 1800
        with self._mute_lock:
            self._tts_muted      = False   # timed mute supersedes permanent mute
            self._tts_mute_until = expire

        # Reset the re-arm timer
        if self._mute_timer_id is not None:
            self.root.after_cancel(self._mute_timer_id)
        self._mute_timer_id = self.root.after(1800 * 1000, self._do_unmute_timed)

        self._update_mute_ui(True, timed=True, expire_epoch=expire)
        self._log("INFO", "[tts] Voice alerts muted for 30 minutes — will re-arm automatically.")

    def _do_unmute_timed(self):
        """
        Called by root.after() when the 30-minute mute window closes.
        Clears the timed mute and restores the armed state.
        """
        with self._mute_lock:
            self._tts_mute_until = 0.0
            self._tts_muted      = False   # timed expiry always returns to armed
        self._mute_timer_id = None
        self._update_mute_ui(False, timed=False)
        self._log("INFO", "[tts] 30-minute mute expired — voice alerts re-armed.")

    def _do_settings(self):
        """Open the Settings dialog. Changes take effect on Save & Apply."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Settings — S.A.T. GroundCrew")
        dlg.configure(bg=C_BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        # ── field definitions: (label, cfg_key, unit_suffix) ─────────────────
        sections = [
            ("NETWORK", [
                ("SAT IP Address",      "sat_host",       ""),
                ("SAT UDP Port",        "sat_port",       ""),
                ("Discovery Port",      "discovery_port", ""),
                ("Discovery Timeout",   "discovery_secs", "sec"),
            ]),
            ("WIND CONTROL", [
                ("Check Interval",      "interval_sec",   "sec"),
                ("Idle Timeout",        "idle_timeout",   "sec"),
                ("Min Gust",            "min_gust_kt",    "kt"),
                ("Min Wind (no gusts)", "min_wind_kt",    "kt"),
            ]),
            ("VOICE ALERTS", [
                ("Alert Window",        "announce_window_secs", "sec"),
                ("Alert Cooldown",      "cooldown_secs",        "sec"),
            ]),
            ("WEATHER", [
                ("ICAO Station",        "icao",           ""),
                ("Home Grid Square",    "operator_grid",  ""),
            ]),
        ]

        entries: dict[str, tk.Entry] = {}

        pad = dict(padx=16, pady=3)
        for sec_title, fields in sections:
            hdr = tk.Frame(dlg, bg=C_HDR)
            hdr.pack(fill="x", pady=(10, 0))
            tk.Label(hdr, text=f"  {sec_title}", bg=C_HDR, fg="#aac8df",
                     font=("Segoe UI", 9, "bold")).pack(side="left", pady=4)
            body = tk.Frame(dlg, bg=C_PANEL)
            body.pack(fill="x", padx=0)
            for label, key, unit in fields:
                row = tk.Frame(body, bg=C_PANEL)
                row.pack(fill="x", **pad)
                tk.Label(row, text=label, bg=C_PANEL, fg=C_DIM,
                         font=("Segoe UI", 9), width=22,
                         anchor="w").pack(side="left")
                e = tk.Entry(row, bg=C_BG, fg=C_TEXT,
                             insertbackground=C_TEXT,
                             relief="flat", width=18,
                             font=("Segoe UI", 10))
                e.insert(0, str(self._cfg.get(key, "")))
                e.pack(side="left", padx=(4, 4))
                if unit:
                    tk.Label(row, text=unit, bg=C_PANEL, fg=C_DIM,
                             font=("Segoe UI", 9)).pack(side="left")
                entries[key] = e

        # ── error label ───────────────────────────────────────────────────────
        err_var = tk.StringVar()
        tk.Label(dlg, textvariable=err_var, bg=C_BG, fg=C_RED,
                 font=("Segoe UI", 9)).pack(pady=(6, 0))

        def _apply():
            new_cfg = dict(self._cfg)
            int_keys = {"sat_port", "discovery_port", "discovery_secs",
                        "interval_sec", "idle_timeout",
                        "min_gust_kt", "min_wind_kt",
                        "announce_window_secs", "cooldown_secs"}
            for key, entry in entries.items():
                val = entry.get().strip()
                if key in int_keys:
                    try:
                        new_cfg[key] = int(val)
                    except ValueError:
                        err_var.set(f"'{key}' must be a whole number.")
                        return
                else:
                    if not val:
                        err_var.set(f"'{key}' cannot be blank.")
                        return
                    new_cfg[key] = val
            self._cfg = new_cfg
            _save_cfg(self._cfg)
            # Update status card display
            self._v_interval.set(f"{self._cfg['interval_sec']//60} min")
            self._v_idle.set(f"{self._cfg['idle_timeout']//60} min")
            self._v_gust_thr.set(
                f"{self._cfg['min_gust_kt']} kt  /  {self._cfg['min_wind_kt']} kt wind")
            self._wake.set()   # nudge worker to pick up new interval
            self._log("INFO", "[settings] Configuration saved.")
            dlg.destroy()

        # ── buttons ───────────────────────────────────────────────────────────
        btn_row = tk.Frame(dlg, bg=C_BG)
        btn_row.pack(fill="x", padx=16, pady=12)
        tk.Button(btn_row, text="Save & Apply",
                  command=_apply,
                  bg="#0d2a1a", fg=C_GREEN,
                  activebackground="#0d2a1a", activeforeground=C_GREEN,
                  font=("Segoe UI", 10, "bold"),
                  relief="flat", pady=7, cursor="hand2", bd=0,
                  width=14).pack(side="left")
        tk.Button(btn_row, text="Cancel",
                  command=dlg.destroy,
                  bg=C_PANEL, fg=C_DIM,
                  activebackground=C_PANEL, activeforeground=C_TEXT,
                  font=("Segoe UI", 10),
                  relief="flat", pady=7, cursor="hand2", bd=0,
                  width=10).pack(side="right")

        dlg.wait_window()

    def _do_open_sat(self):
        """Open the CSN SAT web interface in the default browser."""
        url = f"http://{self._sat_host}"
        self._log("INFO", f"[control] Opening CSN SAT web UI → {url}")
        webbrowser.open(url)

    def _update_mute_ui(self, muted: bool, timed: bool, expire_epoch: float = 0.0):
        """
        Synchronise the Mute button label/colour and the Voice alert STATUS
        card field to reflect the current mute state.  Always called on the
        main thread (directly or via root.after(0, …)).

          armed  — green  "Armed"
          muted  — red    "MUTED  (manual)"
          timed  — orange "Muted until HH:MM  (auto re-arms)"
        """
        def _f():
            if timed:
                expire_str = datetime.fromtimestamp(expire_epoch).strftime("%H:%M")
                self._btn_mute_var.set("🔔  Unmute Voice")
                self._btn_mute.configure(
                    bg="#3d2000", fg=C_ORANGE,
                    activebackground="#3d2000", activeforeground=C_ORANGE)
                self._v_faos.set(f"Muted until {expire_str}  (auto re-arms)")
                self._l_faos.configure(fg=C_ORANGE)
            elif muted:
                self._btn_mute_var.set("🔔  Unmute Voice")
                self._btn_mute.configure(
                    bg="#3a0000", fg=C_RED,
                    activebackground="#3a0000", activeforeground=C_RED)
                self._v_faos.set("MUTED  (manual)")
                self._l_faos.configure(fg=C_RED)
            else:
                self._btn_mute_var.set("🔇  Mute Voice")
                self._btn_mute.configure(
                    bg="#1a2a0a", fg=C_GREEN,
                    activebackground="#1a2a0a", activeforeground=C_GREEN)
                self._v_faos.set("Armed")
                self._l_faos.configure(fg=C_GREEN)
        self.root.after(0, _f)

    def _on_close(self):
        self._wake.set()
        self._ip_ready.set()   # unblock worker if waiting on dialog
        self.root.destroy()

    # ══════════════════════════════════════════════════════════════════════════
    #  NETWORK / WEATHER HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _ping(self, host: str) -> bool:
        r = subprocess.run(["ping", "-n", "1", "-w", "1000", host],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0

    def _send(self, sock: socket.socket, inner: str):
        payload = f"<PST>{inner}</PST>"
        sock.sendto(payload.encode("ascii"), (self._sat_host, self._cfg["sat_port"]))
        self._log("INFO", f"[rotator] TX → {payload}")

    def _fetch_metar(self) -> str:
        for tmpl in METAR_SOURCES:
            url = tmpl.format(icao=self._icao)
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                for line in r.text.splitlines():
                    if line.strip().startswith(self._icao):
                        return line.strip()
            except Exception as exc:
                self._log("WARNING", f"[weather] {url} — {exc}")
        raise RuntimeError("All METAR sources failed.")

    def _parse_wind(self, raw: str):
        m = re.search(r'\b(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b', raw)
        if not m:
            raise ValueError(f"No wind group in: {raw}")
        d, s, g = m.group(1), int(m.group(2)), m.group(3)
        gust = int(g) if g else None
        if d == "VRB" or (d == "000" and s == 0):
            # No fixed bearing — return direction=None so the worker parks the antenna.
            # Do NOT raise; this is a valid METAR, just not actionable for wind-pointing.
            return None, s, gust
        return int(d), s, gust

    # ══════════════════════════════════════════════════════════════════════════
    #  BACKGROUND THREADS
    # ══════════════════════════════════════════════════════════════════════════

    def _tts_worker(self):
        """
        Daemon — drains _speech_q one item at a time.
        Each item is a (queued_at, text) tuple.  Messages older than 5 minutes
        are stale and skipped.  Stale messages are batch-flushed with a single
        log line so a PowerShell hang that builds a long backlog doesn't flood
        the event log when the worker recovers.
        _speak() blocks until the utterance completes (or its 30 s timeout
        fires), so announcements are naturally serialised.
        """
        while True:
            queued_at, text = self._speech_q.get()
            self._speech_q.task_done()

            # Batch-drain all stale messages without logging each one.
            stale = 0
            while time.time() - queued_at > 300:
                stale += 1
                try:
                    queued_at, text = self._speech_q.get_nowait()
                    self._speech_q.task_done()
                except queue.Empty:
                    text = None   # queue exhausted — nothing fresh to speak
                    break

            if stale:
                self._log("INFO",
                    f"[tts] Flushed {stale} stale announcement(s) from queue.")

            if text is None or time.time() - queued_at > 300:
                continue   # entire batch was stale

            _speak(text)

    def _runner_9932(self):
        """
        Single daemon that owns the ONE socket on DISCOVERY_PORT for the entire
        session.  Using one socket avoids the WinError 10013 / port-conflict
        problem that occurs when separate discovery and listener threads both
        try to bind the same port.

        Phase 1 — Discovery (first DISCOVERY_SECS seconds):
          Waits for any 'SAT,' broadcast.  On the first packet received the
          source IP is stored in self._discovered_ip and _discovery_done is set
          so the worker thread can continue.  If nothing arrives before the
          deadline _discovery_done is set with _discovered_ip still None.

        Phase 2 — Ongoing event monitoring (after discovery):
          Processes CSNTracker broadcast events:
            SAT,START TRACK,name,catno  → marks antenna IN USE
            SAT,AOS,az                  → marks antenna IN USE
            SAT,LOS,az                  → clears IN USE immediately
            SAT,FAOS,name,az,timetogo   → queues a voice announcement

        If the bind fails (e.g. Windows Firewall / port already taken) the
        error is logged, _discovery_done is signalled so the worker falls
        through to the manual-IP dialog, and the thread exits cleanly.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind(("", self._cfg["discovery_port"]))
            s.settimeout(1.0)   # short poll so we can check the deadline
        except OSError as exc:
            self._log("ERROR",
                f"[discover] Cannot bind :{self._cfg['discovery_port']}: {exc}  "
                f"— check Windows Firewall or whether another app owns that port.")
            self._discovery_done.set()   # unblock the worker
            return

        self._log("INFO",
            f"[discover] Listening on :{self._cfg['discovery_port']} for CSNTracker "
            f"broadcast (timeout {self._cfg['discovery_secs']}s)…")

        deadline = time.time() + self._cfg["discovery_secs"]
        discovery_complete = False

        with s:
            while True:
                try:
                    data, addr = s.recvfrom(4096)
                    msg = data.decode("ascii", errors="replace").strip()
                    if not msg.startswith("SAT,"):
                        continue

                    # ── Discovery phase: grab the IP from the first packet ────
                    if not discovery_complete:
                        discovery_complete = True
                        self._discovered_ip = addr[0]
                        self._log("INFO",
                            f"[discover] CSNTracker found at {addr[0]}  →  {msg}")
                        self._discovery_done.set()

                    # ── Parse and act on the SAT event ───────────────────────
                    self._handle_sat_event(msg, addr[0])

                except socket.timeout:
                    # Check whether the discovery window has closed
                    if not discovery_complete and time.time() >= deadline:
                        self._log("WARNING",
                            f"[discover] No CSNTracker broadcast in {self._cfg['discovery_secs']}s "
                            f"— falling back to manual IP entry.")
                        discovery_complete = True
                        self._discovery_done.set()
                    # After discovery is done keep looping for ongoing events

                except Exception as exc:
                    self._log("ERROR", f"[discover] {exc}")

    def _handle_sat_event(self, msg: str, src_ip: str):
        """Parse a CSNTracker SAT, broadcast and update antenna-in-use state."""
        parts = [p.strip() for p in msg.split(",")]
        event = parts[1].upper() if len(parts) > 1 else ""

        if event == "START TRACK":
            name = parts[2] if len(parts) > 2 else "unknown"
            cat  = parts[3] if len(parts) > 3 else ""
            with self._cmd_lock:
                self._last_cmd_time = time.time()
            self._log("INFO", f"[sat] START TRACK  {name} ({cat}) — antenna IN USE.")
            self._ui_sat_event(f"TRACKING  {name}", C_CYAN)

        elif event == "AOS":
            az = parts[2] if len(parts) > 2 else "?"
            with self._cmd_lock:
                self._last_cmd_time = time.time()
            self._log("INFO", f"[sat] AOS at {az}° — antenna IN USE.")
            self._ui_sat_event(f"AOS  az={az}°", C_GREEN)

        elif event == "LOS":
            az = parts[2] if len(parts) > 2 else "?"
            with self._cmd_lock:
                self._last_cmd_time = 0.0   # clear immediately — pass is over
            self._log("INFO",
                f"[sat] LOS at {az}° — pass complete, antenna now FREE.")
            self._ui_sat_event(f"LOS  az={az}°", C_DIM)
            self._wake.set()   # let the worker run a wind check right away

        elif event == "FAOS":
            self._handle_faos(parts)

    def _handle_faos(self, parts: list):
        """
        Process a SAT,FAOS,<name>,<azimuth>,<timetogo> broadcast.

        Guards applied in order:
          1. Packet must have at least 5 comma-separated fields.
          2. timetogo must be <= ANNOUNCE_WINDOW_SECS (within 5 min of AOS).
          3. Voice alerts muted (manual or timed)?  → suppress silently.
             NOTE: the cooldown is NOT stamped when muted, so the first FAOS
             received after unmuting will always trigger an announcement.
          4. The same satellite must not have been announced within COOLDOWN_SECS.

        If all guards pass a spoken message is queued on _speech_q and the
        Voice alert row in the STATUS card is updated.
        """
        if len(parts) < 5:
            self._log("WARNING", f"[faos] Malformed packet — expected 5+ fields: {parts}")
            return

        name = parts[2].strip()
        try:
            az       = float(parts[3].strip())
            timetogo = int(float(parts[4].strip()))
        except ValueError as exc:
            self._log("WARNING", f"[faos] Parse error: {exc}  raw={parts}")
            return

        self._log("INFO", f"[faos] {name}  az={az:.1f}°  timetogo={timetogo}s")

        # Guard 1: outside the announcement window?
        if timetogo > self._cfg["announce_window_secs"]:
            self._log("INFO",
                f"[faos] {name} — {timetogo}s away, "
                f"outside {self._cfg['announce_window_secs']}s window, no alert.")
            return

        # Guard 2: voice alerts muted?
        now = time.time()
        with self._mute_lock:
            # Inline expiry check — clears a timed mute that lapsed between packets
            if self._tts_mute_until > 0 and now >= self._tts_mute_until:
                self._tts_mute_until = 0.0
                self._tts_muted      = False
                self.root.after(0, lambda: self._update_mute_ui(False, False))
            is_muted = self._tts_muted or (self._tts_mute_until > 0)

        if is_muted:
            self._log("INFO",
                f"[faos] {name} — voice alerts muted, announcement suppressed.")
            return

        # Guard 3: cooldown — already announced this bird recently?
        key = name.upper()
        with self._ann_lock:
            last = self._announced.get(key, 0)
            if now - last < self._cfg["cooldown_secs"]:
                self._log("INFO",
                    f"[faos] {name} — announced {int(now - last)}s ago "
                    f"(cooldown {self._cfg['cooldown_secs']}s), skipping.")
                return
            self._announced[key] = now   # stamp before releasing the lock

        # Build the spoken message and queue it
        phrase = _time_phrase(timetogo)
        spoken = f"{name} will be rising in {phrase}"
        self._log("INFO", f"[faos] QUEUING announcement: {spoken}  (az {az:.1f}°)")
        self._speech_q.put((time.time(), spoken))
        self._ui_faos_alert(f"{name}  in {phrase}", C_YELLOW)

    def _check_mode(self) -> bool:
        """
        Single HTTP GET /track immediately before a planned antenna move.
        Returns True (and marks antenna IN USE) if the SAT is tracking.
        Returns False on error — fail-open so a network hiccup never blocks a move.
        Updates the live ANTENNA card position as a side-effect.
        """
        try:
            r = requests.get(f"http://{self._sat_host}/track", timeout=6)
            r.raise_for_status()
            data    = r.json()
            mode    = int(data.get("mode", 0))
            az      = data.get("az")
            el      = data.get("el")
            satname = data.get("satname", "")
            if az is not None and el is not None:
                self._ui_live_position(float(az), float(el), mode == 1)
            if mode == 1:
                sat_info = f"  {satname}" if satname else ""
                self._log("INFO",
                    f"[main] Pre-move mode check: SAT is TRACKING{sat_info} — move aborted.")
                self._ui_sat_event(f"TRACKING{sat_info}  (mode check)", C_CYAN)
                with self._cmd_lock:
                    self._last_cmd_time = time.time()
            else:
                # Confirmed idle — clear any stale TRACKING label left by a previous check.
                self._ui_sat_event("IDLE  (mode=0)", C_DIM)
            return mode == 1
        except Exception as exc:
            self._log("WARNING",
                f"[main] Mode check failed ({type(exc).__name__}: {exc}) — proceeding.")
            return False

    def _keepalive(self):
        """
        Daemon — resends the last azimuth/elevation every 60 s so the antenna
        holds position even if it was bumped or reset between wind checks.
        Respects the same guards as the worker: won't resend while paused or
        while the antenna is marked in use by a satellite tracker / other app.
        Does nothing until the worker has successfully sent at least one command.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
            while True:
                time.sleep(60)

                with self._az_lock:
                    az       = self._last_az
                    at_park  = self._at_park
                if az is None:
                    continue                     # no position established yet
                if at_park:
                    continue                     # park position managed by CSN SAT; no keepalive

                with self._pause_lock:
                    if self._paused:
                        continue

                with self._cmd_lock:
                    lct = self._last_cmd_time
                now = time.time()
                in_use        = (lct > 0 and now - lct < self._cfg["idle_timeout"])
                just_expired  = (lct > 0 and now - lct >= self._cfg["idle_timeout"])
                if in_use:
                    continue
                if just_expired:
                    # IDLE_TIMEOUT elapsed without an explicit LOS or mode=0 poll
                    # transition — clear the timer and update the label so the GUI
                    # doesn't stay frozen at "TRACKING …".
                    with self._cmd_lock:
                        self._last_cmd_time = 0.0
                    self._ui_sat_event("IDLE  (timeout)", C_DIM)
                    self._log("INFO",
                        "[keepalive] Satellite tracking timed out — antenna now FREE.")

                try:
                    for inner in ("<ELEVATION>0.0</ELEVATION>",
                                  f"<AZIMUTH>{az}.0</AZIMUTH>"):
                        payload = f"<PST>{inner}</PST>"
                        tx.sendto(payload.encode("ascii"), (self._sat_host, self._cfg["sat_port"]))
                    self._log("INFO", f"[keepalive] Azimuth {az}° re-sent.")
                except Exception as exc:
                    self._log("ERROR", f"[keepalive] Send failed: {exc}")

    def _fetch_park_position(self) -> tuple:
        """
        GET http://{sat_host}/status and return (parkAZ, parkEL) as floats.
        Returns (None, None) on any error so the caller can fall back gracefully.
        """
        try:
            r = requests.get(f"http://{self._sat_host}/status", timeout=6)
            r.raise_for_status()
            data = r.json()
            return float(data["parkAZ"]), float(data["parkEL"])
        except Exception as exc:
            self._log("WARNING", f"[main] Could not fetch park position: {exc}")
            return None, None

    def _worker(self):
        """
        Daemon — handles startup, discovery, then the main wind-tracking loop.
        """
        self._log("INFO", "[startup] S.A.T. GroundCrew  —  Michael Walker VA3MW")
        self._log("INFO", f"[startup] Interval : {self._cfg['interval_sec']//60} min  |  "
                          f"Idle guard : {self._cfg['idle_timeout']//60} min  |  "
                          f"Gust min : {self._cfg['min_gust_kt']} kt  |  "
                          f"Wind min (no gusts) : {self._cfg['min_wind_kt']} kt")

        # ── Phase 1: wait for runner_9932 to complete the discovery phase ────
        self._discovery_done.wait()          # blocks until found or timed out
        discovered = self._discovered_ip    # None if nothing was heard

        if discovered:
            self._sat_host = discovered
            self._cfg["sat_host"] = discovered
            _save_cfg(self._cfg)
            self._log("INFO", f"[discover] IP {discovered} saved to config.")
            self._ui_sat_host_discovered(discovered)
        else:
            # Discovery timed out — ask the user on the main thread
            self._log("WARNING",
                "[discover] Showing manual IP entry dialog…")
            self._ip_ready.clear()
            self.root.after(0, self._show_ip_dialog)
            self._ip_ready.wait()          # block until user clicks Connect
            self._sat_host = self._ip_result
            self._cfg["sat_host"] = self._ip_result
            _save_cfg(self._cfg)
            self._log("INFO",
                f"[discover] Using manually entered IP: {self._sat_host} (saved to config.)")

        # ── Phase 2: ping the SAT to confirm reachability ─────────────────────
        self._log("INFO", f"[startup] Pinging {self._sat_host}…")
        if self._ping(self._sat_host):
            self._log("INFO",    f"[startup] CSN SAT {self._sat_host} — reachable  ✓")
            self._ui_sat(True)
        else:
            self._log("WARNING", f"[startup] CSN SAT {self._sat_host} — no ping response.")
            self._log("WARNING",  "[startup] Continuing — UDP commands may still work.")
            self._ui_sat(False)

        self._log("INFO", f"[startup] Sending commands to {self._sat_host}:{SAT_PORT}")

        # ── Phase 3: main wind-tracking loop ──────────────────────────────────
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
            while True:
                self._log("INFO", "─" * 56)
                self._log("INFO", "[main] Scheduled check running…")

                with self._pause_lock:
                    paused = self._paused

                # Guard 1: manually paused?
                if paused:
                    self._log("INFO", "[main] SKIPPED — paused by operator.")
                    self._ui_skipped("paused")

                # Guard 2: antenna in use by satellite tracker or other app?
                elif (self._last_cmd_time > 0 and
                      time.time() - self._last_cmd_time < self._cfg["idle_timeout"]):
                    age = int(time.time() - self._last_cmd_time)
                    rem = self._cfg["idle_timeout"] - age
                    self._log("INFO",
                        f"[main] SKIPPED — antenna in use  "
                        f"(last event {age}s ago, {rem}s until idle).")
                    self._ui_skipped("antenna in use")

                else:
                    # Fetch METAR
                    wdir = wspd = wgst = None
                    metar_ok = False
                    try:
                        raw = self._fetch_metar()
                        self._log("INFO", f"[weather] METAR : {raw}")
                        wdir, wspd, wgst = self._parse_wind(raw)
                        metar_ok = True
                        if wdir is None:
                            # Variable or calm wind — no bearing to point to; will park.
                            kind = "calm" if wspd == 0 else "variable"
                            gs = f", gusting {wgst} kt" if wgst else ""
                            self._log("INFO",
                                f"[weather] Wind  : {kind} at {wspd} kt{gs}"
                                f" — no fixed bearing, antenna will park")
                        else:
                            gs = f", gusting {wgst} kt" if wgst else ", no gusts reported"
                            self._log("INFO",
                                f"[weather] Wind  : {wdir}° at {wspd} kt{gs}")
                        self._ui_weather(raw, wdir, wspd, wgst)
                    except Exception as exc:
                        self._log("ERROR", f"[main] SKIPPED — weather error: {exc}")

                    if metar_ok:
                        # Guard 3 — determine whether to move or park.
                        # wdir=None means variable/calm: always park (no fixed bearing).
                        # Otherwise: move if above threshold, park if below.
                        if wdir is None:
                            trigger = None   # variable/calm → park
                        elif wgst is not None and wgst > self._cfg["min_gust_kt"]:
                            trigger = f"wind {wspd} kt, gusting {wgst} kt from {wdir}°"
                        elif wgst is None and wspd > self._cfg["min_wind_kt"]:
                            trigger = f"sustained wind {wspd} kt from {wdir}° (no gusts)"
                        else:
                            trigger = None   # below threshold → park

                        if trigger is None:
                            if wdir is None:
                                kind = "calm" if wspd == 0 else "variable"
                                below = f"wind {kind} — no fixed bearing"
                            elif wgst is None:
                                below = f"wind {wspd} kt ≤ {self._cfg['min_wind_kt']} kt threshold"
                            else:
                                below = f"gusts {wgst} kt ≤ {self._cfg['min_gust_kt']} kt threshold"
                            self._log("INFO",
                                f"[main] Wind below threshold ({below}) — returning to park.")
                            if self._check_mode():
                                continue   # SAT is tracking; skip park command this cycle
                            park_az, park_el = self._fetch_park_position()
                            if park_az is not None:
                                self._log("INFO",
                                    f"[main] PARK → Azimuth {park_az:.1f}°  "
                                    f"Elevation {park_el:.1f}°")
                                try:
                                    self._send(tx, f"<ELEVATION>{park_el:.1f}</ELEVATION>")
                                    self._send(tx, f"<AZIMUTH>{park_az:.1f}</AZIMUTH>")
                                    self._log("INFO", "[main] Park commands sent successfully.")
                                    with self._az_lock:
                                        self._last_az = int(round(park_az))
                                        self._at_park = True
                                    self._ui_parked(park_az)
                                except Exception as exc:
                                    self._log("ERROR", f"[main] Park command failed: {exc}")
                            else:
                                self._log("WARNING",
                                    "[main] Park position unavailable — holding current position.")
                                self._ui_skipped(below)
                        else:
                            # All guards passed — move the antenna
                            self._log("INFO",
                                f"[main] MOVING antenna  →  Azimuth {wdir}°  "
                                f"Elevation 0°  ({trigger})")
                            # Final check: confirm SAT is not tracking before touching hardware
                            if self._check_mode():
                                continue   # SAT started tracking; skip this move cycle
                            try:
                                self._send(tx, "<ELEVATION>0.0</ELEVATION>")
                                self._send(tx, f"<AZIMUTH>{wdir}.0</AZIMUTH>")
                                self._log("INFO", "[main] Commands sent successfully.")
                                with self._az_lock:
                                    self._last_az = wdir
                                    self._at_park = False
                                self._ui_moved(wdir)
                            except Exception as exc:
                                self._log("ERROR", f"[main] Send failed: {exc}")

                self._next_check_at = time.time() + self._cfg["interval_sec"]
                self._log("INFO", f"[main] Next check in {self._cfg['interval_sec']//60} minutes.")
                self._wake.clear()
                self._wake.wait(timeout=self._cfg["interval_sec"])


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # ── Single-instance guard ─────────────────────────────────────────────────
    # Bind a TCP socket to a fixed localhost port for the lifetime of main().
    # A second launch will fail to bind and warn the user instead of starting.
    _lock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _lock_sock.bind(("127.0.0.1", 19932))
    except OSError:
        _r = tk.Tk()
        _r.withdraw()
        tkinter.messagebox.showerror(
            "Already Running",
            "S.A.T. GroundCrew is already running.\n\nOnly one instance may run at a time."
        )
        sys.exit(1)

    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()