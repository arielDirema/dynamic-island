"""Interpolation helpers used by the island animation."""
import math


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def spring(x, v, target, k, dt, zeta=0.86):
    c = 2 * zeta * math.sqrt(k)
    n = max(1, int(dt / 0.004) + 1)
    h = dt / n
    for _ in range(n):
        a = k * (target - x) - c * v
        v += a * h
        x += v * h
    return x, v
