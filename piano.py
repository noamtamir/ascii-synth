#!/usr/bin/env python3
"""A tiny terminal piano powered by pygame-ce."""

import array
import math
import os
import select
import shutil
import sys
import termios
import time
import tty

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

SAMPLE_RATE = 22_050
NOTE_SECONDS = 0.5
ATTACK_MS = 100
RELEASE_MS = 100
INITIAL_KEY_REPEAT_GRACE = 0.8
KEY_REPEAT_TIMEOUT = 0.4
KEYS = ("a", "w", "s", "e", "d", "f", "t", "g", "y", "h", "u", "j", "k")
KEYBOARD_ART = (
    "    ┌───────┬───────┐       ┌───────┬───────┬───────┐",
    "    │   W   │   E   │       │   T   │   Y   │   U   │",
    "┌───┴───┬───┴───┬───┴───┬───┴───┬───┴───┬───┴───┬───┴───┬───────┐",
    "│   A   │   S   │   D   │   F   │   G   │   H   │   J   │   K   │",
    "└───────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┘",
)
KEY_LABEL_POSITIONS = {
    "w": (1, 5),
    "e": (1, 13),
    "t": (1, 29),
    "y": (1, 37),
    "u": (1, 45),
    "a": (3, 1),
    "s": (3, 9),
    "d": (3, 17),
    "f": (3, 25),
    "g": (3, 33),
    "h": (3, 41),
    "j": (3, 49),
    "k": (3, 57),
}


def make_note(frequency: float) -> pygame.mixer.Sound:
    sample_count = int(SAMPLE_RATE * NOTE_SECONDS)
    attack_samples = int(SAMPLE_RATE * ATTACK_MS / 1000)
    release_samples = int(SAMPLE_RATE * RELEASE_MS / 1000)
    samples = array.array(
        "h",
        (
            int(
                12_000
                * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)
                * min(
                    1,
                    index / attack_samples,
                    (sample_count - 1 - index) / release_samples,
                )
            )
            for index in range(sample_count)
        ),
    )
    return pygame.mixer.Sound(buffer=samples.tobytes())


def is_key_repeat(key: str, now: float, recent_keys: dict[str, tuple[float, bool]]) -> bool:
    for recent_key, (last_seen, repeated) in list(recent_keys.items()):
        timeout = KEY_REPEAT_TIMEOUT if repeated else INITIAL_KEY_REPEAT_GRACE
        if now - last_seen >= timeout:
            del recent_keys[recent_key]

    if key in recent_keys:
        recent_keys[key] = (now, True)
        return True

    recent_keys[key] = (now, False)
    return False


def draw_keyboard() -> int:
    display = ["ASCII PIANO  |  Esc / Ctrl+C to quit", "", *KEYBOARD_ART]
    screen_rows = shutil.get_terminal_size(fallback=(80, 24)).lines
    first_row = max(1, screen_rows - len(display) + 1)
    output = ["\x1b[s\x1b[?25l\x1b[2J"]
    for offset, line in enumerate(display):
        output.append(f"\x1b[{first_row + offset};1H\x1b[2K{line}")
    sys.stdout.write("".join(output))
    sys.stdout.flush()
    return first_row


def set_key_highlight(
    previous_key: str | None,
    pressed_key: str | None,
    first_row: int,
) -> None:
    if previous_key == pressed_key:
        return

    for key, invert in ((previous_key, False), (pressed_key, True)):
        if key is None:
            continue
        row, start = KEY_LABEL_POSITIONS[key]
        label = KEYBOARD_ART[row][start : start + 7]
        style = "\x1b[7m" if invert else ""
        reset = "\x1b[27m" if invert else ""
        sys.stdout.write(
            f"\x1b[{first_row + row + 2};{start + 1}H{style}{label}{reset}"
        )

    sys.stdout.flush()


def main() -> None:
    frequencies = {
        key: 220.0 * 2 ** (index / 12)
        for index, key in enumerate(KEYS)
    }
    if not sys.stdin.isatty():
        raise SystemExit("Run this program in a terminal so it can read key presses.")

    pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=512)
    pygame.mixer.set_num_channels(32)
    sounds = {key: make_note(frequency) for key, frequency in frequencies.items()}
    recent_keys: dict[str, tuple[float, bool]] = {}
    file_descriptor = sys.stdin.fileno()
    old_terminal = termios.tcgetattr(file_descriptor)

    try:
        tty.setraw(file_descriptor)
        first_row = draw_keyboard()
        pressed_key: str | None = None
        highlight_until = 0.0
        while True:
            timeout = max(0.0, highlight_until - time.monotonic()) if pressed_key else None
            readable, _, _ = select.select([file_descriptor], [], [], timeout)
            if not readable:
                set_key_highlight(pressed_key, None, first_row)
                pressed_key = None
                continue

            key = os.read(file_descriptor, 1).decode("utf-8", errors="ignore").lower()
            if key in ("\x1b", "\x03"):
                break
            if key in sounds:
                if not is_key_repeat(key, time.monotonic(), recent_keys):
                    sounds[key].play()
                    set_key_highlight(pressed_key, key, first_row)
                    pressed_key = key
                    highlight_until = time.monotonic() + NOTE_SECONDS
    finally:
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, old_terminal)
        pygame.mixer.quit()
        sys.stdout.write("\x1b[u\x1b[?25h")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
