# -*- coding: utf-8 -*-
"""
Amazing RP — помощник для мини-игры мусорщика.
F6 — старт/стоп; F7 — экстренная остановка; F8 — пауза/продолжить; ESC — выход.
"""
import time
import os
import re
import threading
import ctypes
from ctypes import wintypes
import sys

import cv2
import mss
import numpy as np
import pytesseract
import keyboard
import pydirectinput

# Если Tesseract установлен не в стандартную папку, укажите путь:
if getattr(sys, "frozen", False):
    TESSERACT_EXE = os.path.join(sys._MEIPASS, "tesseract", "tesseract.exe")
else:
    TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Область поиска подсказки относительно размеров экрана.
# При необходимости включите SHOW_DEBUG и подстройте доли под свой интерфейс.
ROI_X, ROI_Y, ROI_W, ROI_H = 0.405, 0.535, 0.19, 0.23
SHOW_DEBUG = False
POLL_SECONDS = 0.12
LOST_KEY_TIMEOUT = 0.65
OCR_CONFIDENCE = 20

pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
if getattr(sys, "frozen", False):
    os.environ["TESSDATA_PREFIX"] = os.path.join(sys._MEIPASS, "tesseract", "tessdata")
pydirectinput.PAUSE = 0
pydirectinput.FAILSAFE = False

# OCR-варианты символов стрелок и их клавиши.
KEY_MAP = {
    "↑": "up", "▲": "up", "UP": "up",
    "↓": "down", "▼": "down", "DOWN": "down",
    "←": "left", "◀": "left", "LEFT": "left",
    "→": "right", "▶": "right", "RIGHT": "right",
    "SPACE": "space", "SPC": "space",
    "ENTER": "enter", "RETURN": "enter",
    "SHIFT": "shift", "CTRL": "ctrl", "ALT": "alt",
    "TAB": "tab", "ESC": "esc",
}
for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
    KEY_MAP[c] = c.lower()

state = {"running": False, "paused": False, "exit": False}
current_key = None
last_seen = 0.0
lock = threading.Lock()


def release_current():
    global current_key
    if current_key:
        try:
            pydirectinput.keyUp(current_key)
        except Exception:
            pass
        print(f"[Бот] Отпустил: {current_key}")
        current_key = None


def parse_key(img):
    """Ищет крупную букву/название клавиши в центральной области подсказки."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Убираем полупрозрачный фон, усиливаем контраст символа.
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(gray, 145, 255, cv2.THRESH_BINARY)

    config = r'--oem 3 --psm 11 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789↑↓←→▲▼◀▶'
    try:
        data = pytesseract.image_to_data(
            th, config=config, output_type=pytesseract.Output.DICT
        )
        candidates = []
        for i, raw in enumerate(data["text"]):
            token = raw.strip().upper()
            if not token:
                continue
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = 0
            token = re.sub(r"[^A-Z0-9↑↓←→▲▼◀▶]", "", token)
            if token in KEY_MAP and conf >= OCR_CONFIDENCE:
                candidates.append((conf, token))
        if candidates:
            candidates.sort(reverse=True)
            return KEY_MAP[candidates[0][1]]
    except Exception as e:
        print("[OCR] Ошибка:", e)
    return None


def get_roi(sct):
    monitor = sct.monitors[1]
    sw, sh = monitor["width"], monitor["height"]
    left = monitor["left"] + int(sw * ROI_X)
    top = monitor["top"] + int(sh * ROI_Y)
    width = max(80, int(sw * ROI_W))
    height = max(80, int(sh * ROI_H))
    shot = np.array(sct.grab({
        "left": left, "top": top, "width": width, "height": height
    }))
    return cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)


def worker():
    global current_key, last_seen
    print("[Бот] Готов. Подойди к кучке мусора и нажми F6.")
    with mss.mss() as sct:
        while not state["exit"]:
            if not state["running"] or state["paused"]:
                release_current()
                time.sleep(0.1)
                continue

            frame = get_roi(sct)
            key = parse_key(frame)
            now = time.time()

            if SHOW_DEBUG:
                cv2.imshow("Область распознавания — Q для закрытия", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    state["running"] = False

            if key:
                last_seen = now
                if key != current_key:
                    release_current()
                    current_key = key
                    pydirectinput.keyDown(current_key)
                    print(f"[Бот] Зажал: {current_key}")
            elif current_key and now - last_seen > LOST_KEY_TIMEOUT:
                release_current()

            time.sleep(POLL_SECONDS)

    release_current()
    if SHOW_DEBUG:
        cv2.destroyAllWindows()


def toggle_run():
    state["running"] = not state["running"]
    if not state["running"]:
        release_current()
    print("[Бот] " + ("РАБОТАЕТ" if state["running"] else "ОСТАНОВЛЕН"))


def emergency_stop():
    state["running"] = False
    state["paused"] = False
    release_current()
    print("[Бот] ЭКСТРЕННАЯ ОСТАНОВКА")


def toggle_pause():
    if state["running"]:
        state["paused"] = not state["paused"]
        if state["paused"]:
            release_current()
        print("[Бот] " + ("ПАУЗА" if state["paused"] else "ПРОДОЛЖАЮ"))


def main():
    print("=" * 54)
    print(" AMAZING RP — АВТОУДЕРЖАНИЕ КЛАВИШ МУСОРЩИКА")
    print(" F6 — старт/стоп | F7 — экстренная остановка")
    print(" F8 — пауза | ESC — выход")
    print("=" * 54)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    keyboard.add_hotkey("F6", toggle_run)
    keyboard.add_hotkey("F7", emergency_stop)
    keyboard.add_hotkey("F8", toggle_pause)

    try:
        keyboard.wait("esc")
    finally:
        state["exit"] = True
        state["running"] = False
        release_current()
        time.sleep(0.25)
        print("[Бот] Завершён.")


if __name__ == "__main__":
    main()
