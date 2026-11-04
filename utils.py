import re

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_PATTERN = re.compile(r"(\d+)\s*([smhd])")


def parse_duration(raw: str) -> int:
    """Превращает '30s', '10m', '1h30m', '2d' в количество секунд."""
    text = raw.strip().lower()
    parts = _PATTERN.findall(text)
    if not parts:
        raise ValueError("Формат времени: `10m`, `1h30m`, `2d` (s/m/h/d).")
    rest = _PATTERN.sub("", text).strip()
    if rest:
        raise ValueError(f"Непонятный фрагмент: `{rest}`. Формат: `10m`, `1h30m`, `2d`.")
    total = sum(int(count) * _UNITS[unit] for count, unit in parts)
    if total <= 0:
        raise ValueError("Время должно быть больше нуля.")
    return total
