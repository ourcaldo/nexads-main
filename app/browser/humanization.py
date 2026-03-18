"""
nexads/browser/humanization.py
Shared helpers for timing and human-like pointer behavior.
"""

from __future__ import annotations

import math
import random
from typing import MutableMapping


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp value to [minimum, maximum]."""
    return max(minimum, min(value, maximum))


def gaussian_ms(mean: float, std_dev: float, minimum: int, maximum: int) -> int:
    """Generate bounded gaussian delay in milliseconds."""
    value = int(round(random.gauss(mean, std_dev)))
    return int(clamp(value, minimum, maximum))


def lognormal_seconds(median_seconds: float, sigma: float,
                      minimum: float, maximum: float) -> float:
    """Generate bounded log-normal delay in seconds."""
    median = max(0.001, median_seconds)
    value = random.lognormvariate(math.log(median), sigma)
    return float(clamp(value, minimum, maximum))


def get_cursor_start(page, interaction_state: MutableMapping | None = None) -> tuple[float, float]:
    """Return persisted cursor position or viewport center."""
    if interaction_state:
        stored = interaction_state.get("cursor_position")
        if (
            isinstance(stored, (tuple, list))
            and len(stored) == 2
            and all(isinstance(v, (int, float)) for v in stored)
        ):
            return float(stored[0]), float(stored[1])

    viewport = page.viewport_size or {"width": 1280, "height": 720}
    return float(viewport["width"] / 2), float(viewport["height"] / 2)


def set_cursor_position(interaction_state: MutableMapping | None,
                        x: float, y: float) -> None:
    """Persist cursor position for the next action."""
    if interaction_state is not None:
        interaction_state["cursor_position"] = (float(x), float(y))


def _ease_in_out_cubic(progress: float) -> float:
    if progress < 0.5:
        return 4 * progress * progress * progress
    return 1 - pow(-2 * progress + 2, 3) / 2


def _bezier_point(p0: tuple[float, float], p1: tuple[float, float],
                  p2: tuple[float, float], p3: tuple[float, float],
                  t: float) -> tuple[float, float]:
    one_minus_t = 1 - t
    x = (
        (one_minus_t ** 3) * p0[0]
        + 3 * (one_minus_t ** 2) * t * p1[0]
        + 3 * one_minus_t * (t ** 2) * p2[0]
        + (t ** 3) * p3[0]
    )
    y = (
        (one_minus_t ** 3) * p0[1]
        + 3 * (one_minus_t ** 2) * t * p1[1]
        + 3 * one_minus_t * (t ** 2) * p2[1]
        + (t ** 3) * p3[1]
    )
    return x, y


def _curve_control_points(start: tuple[float, float],
                          target: tuple[float, float]) -> tuple[tuple[float, float], tuple[float, float]]:
    dx = target[0] - start[0]
    dy = target[1] - start[1]
    distance = math.hypot(dx, dy)
    if distance <= 1:
        return start, target

    normal_x = -dy / distance
    normal_y = dx / distance
    curve_strength = clamp(distance * random.uniform(0.12, 0.24), 10, 90)

    c1_t = random.uniform(0.2, 0.4)
    c2_t = random.uniform(0.6, 0.85)

    c1 = (
        start[0] + dx * c1_t + normal_x * random.uniform(-curve_strength, curve_strength),
        start[1] + dy * c1_t + normal_y * random.uniform(-curve_strength, curve_strength),
    )
    c2 = (
        start[0] + dx * c2_t + normal_x * random.uniform(-curve_strength, curve_strength),
        start[1] + dy * c2_t + normal_y * random.uniform(-curve_strength, curve_strength),
    )
    return c1, c2


def _overshoot_target(start: tuple[float, float],
                      target: tuple[float, float]) -> tuple[float, float]:
    dx = target[0] - start[0]
    dy = target[1] - start[1]
    distance = math.hypot(dx, dy)
    if distance <= 1:
        return target

    overshoot_ratio = clamp(random.uniform(0.03, 0.08), 0.03, 0.08)
    return (
        target[0] + dx * overshoot_ratio + random.uniform(-4, 4),
        target[1] + dy * overshoot_ratio + random.uniform(-4, 4),
    )


def _build_curve_points(start: tuple[float, float], target: tuple[float, float],
                        steps: int, jitter_px: float = 2.0) -> list[tuple[float, float]]:
    c1, c2 = _curve_control_points(start, target)
    points: list[tuple[float, float]] = []
    for i in range(1, steps + 1):
        raw_t = i / steps
        eased_t = _ease_in_out_cubic(raw_t)
        x, y = _bezier_point(start, c1, c2, target, eased_t)
        if i < steps:
            x += random.gauss(0, jitter_px * 0.5)
            y += random.gauss(0, jitter_px * 0.5)
        points.append((x, y))

    if points:
        points[-1] = target
    return points


def generate_mouse_path(start: tuple[float, float],
                        target: tuple[float, float]) -> list[tuple[float, float]]:
    """Generate a curved, slightly noisy mouse path with occasional overshoot."""
    distance = math.hypot(target[0] - start[0], target[1] - start[1])
    steps = int(clamp(distance / random.uniform(20, 35), 8, 30))
    should_overshoot = distance > 140 and random.random() < 0.22

    if should_overshoot:
        overshoot = _overshoot_target(start, target)
        first_leg = _build_curve_points(start, overshoot, steps, jitter_px=2.5)
        correction_steps = int(clamp(steps * 0.4, 4, 12))
        second_leg = _build_curve_points(overshoot, target, correction_steps, jitter_px=1.0)
        return first_leg + second_leg

    return _build_curve_points(start, target, steps, jitter_px=2.0)


async def move_mouse_humanly(page, start: tuple[float, float],
                             target: tuple[float, float]) -> None:
    """Move mouse along a curved path with bounded per-step delays."""
    path = generate_mouse_path(start, target)
    distance = math.hypot(target[0] - start[0], target[1] - start[1])
    total_ms = gaussian_ms(320 + distance * 0.65, 120, 180, 1600)
    step_delay = max(8, int(total_ms / max(1, len(path))))

    for index, (x, y) in enumerate(path):
        await page.mouse.move(x, y)
        if index < len(path) - 1:
            await page.wait_for_timeout(
                gaussian_ms(step_delay, max(4, step_delay * 0.35), 6, 65)
            )


def choose_click_point(box: dict, tag_name: str = "") -> tuple[float, float]:
    """Pick a realistic click point inside the element box."""
    width = max(1.0, float(box["width"]))
    height = max(1.0, float(box["height"]))

    center_x = float(box["x"]) + width / 2
    center_y = float(box["y"]) + height / 2

    # Slightly bias text-like elements toward left-third.
    lower_tag = (tag_name or "").lower()
    left_bias = -0.16 * width if lower_tag in {"a", "span", "p"} else 0.0

    click_x = random.gauss(center_x + left_bias, width * 0.15)
    click_y = random.gauss(center_y, height * 0.17)

    min_x = float(box["x"]) + 1
    max_x = float(box["x"]) + width - 1
    min_y = float(box["y"]) + 1
    max_y = float(box["y"]) + height - 1

    return (
        clamp(click_x, min_x, max_x),
        clamp(click_y, min_y, max_y),
    )
