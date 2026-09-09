"""Shubh diva calendar loader.

Loads the aggregated Hindu auspicious-day calendar from
configs/shubh_calendar.json and exposes lookups the alert scripts use
at runtime. The workflow calls is_shubh_day(today) each morning, so a
refreshed JSON file flows through immediately with no code change.

Time-window support:
  Some shubh divas run for only part of the day (Pushya Nakshatra is the
  main example — usually a 4-8 hour window). An event JSON entry can
  optionally carry `start_ist` and `end_ist` fields (HH:MM strings, 24h).
  When absent, the event is treated as full-day auspicious (Ekadashi,
  Amavasya, Purnima and most festivals traditionally are full-day).

  All windows are stored in IST because that is how Panchang is authored.
  For display, muhurta_window_for() converts to EST/EDT (with correct
  DST handling) so the user sees both India-time and market-time.

To refresh the calendar (e.g. yearly, or when panchang for the next
year becomes available), overwrite configs/shubh_calendar.json with a
new payload of the same shape. The
scripts/refresh_shubh_calendar.py helper can regenerate it via
research agents.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_CACHE: dict | None = None
_CALENDAR_PATH = Path(__file__).resolve().parent.parent / "configs" / "shubh_calendar.json"

# Which types are considered "gold-relevant" shubh divas. Gold-specific
# festivals (Dhanteras, Akshaya Tritiya, Dhanatrayodashi) always count.
# Regular observances (ekadashi/amavasya/purnima/pushya) also count —
# people buy gold on all of them.
_GOLD_RELEVANT_TYPES = {"festival", "ekadashi", "amavasya", "purnima", "pushya"}


def _load() -> dict:
    global _CACHE
    if _CACHE is None:
        if not _CALENDAR_PATH.exists():
            _CACHE = {"events": [], "coverage": {"start": None, "end": None}}
        else:
            _CACHE = json.loads(_CALENDAR_PATH.read_text())
    return _CACHE


def _to_iso(d: str | date | datetime) -> str:
    if isinstance(d, str):
        return d[:10]
    if isinstance(d, datetime):
        return d.date().isoformat()
    return d.isoformat()


def calendar_coverage() -> tuple[str | None, str | None]:
    """Return (start, end) ISO dates the calendar covers."""
    cov = _load().get("coverage", {})
    return cov.get("start"), cov.get("end")


def is_shubh_day(d: str | date | datetime) -> bool:
    """True if the given date is a gold-relevant shubh diva."""
    iso = _to_iso(d)
    for ev in _load().get("events", []):
        if ev["date"] == iso and ev.get("type") in _GOLD_RELEVANT_TYPES:
            return True
    return False


def shubh_types_for(d: str | date | datetime) -> list[str]:
    """Return every shubh type recorded for that date (may overlap)."""
    iso = _to_iso(d)
    return sorted({ev["type"] for ev in _load().get("events", [])
                   if ev["date"] == iso and ev.get("type") in _GOLD_RELEVANT_TYPES})


def describe_shubh_day(d: str | date | datetime) -> str | None:
    """Plain-English label for today's shubh types, or None if not shubh.

    Example return values:
      'Ekadashi'
      'Purnima and Pushya Nakshatra'
      'Festival (Dhanteras / Akshaya Tritiya window) and Ekadashi'
    """
    types = shubh_types_for(d)
    if not types:
        return None
    labels = {
        "festival": "festival",
        "ekadashi": "Ekadashi",
        "amavasya": "Amavasya",
        "purnima": "Purnima",
        "pushya": "Pushya Nakshatra",
    }
    pretty = [labels.get(t, t) for t in types]
    if len(pretty) == 1:
        return pretty[0]
    if len(pretty) == 2:
        return f"{pretty[0]} and {pretty[1]}"
    return ", ".join(pretty[:-1]) + f", and {pretty[-1]}"


IST = ZoneInfo("Asia/Kolkata")
ET = ZoneInfo("America/New_York")   # auto-handles EST/EDT


def _ist_to_et(day_iso: str, hhmm: str) -> tuple[str, str]:
    """Convert an IST wall-clock (YYYY-MM-DD, HH:MM) to (HH:MM, tz_label) in
    New-York time (EST winter, EDT summer, auto-switched by zoneinfo).
    Returns the New-York clock time plus a same-day / previous-day / next-day
    marker relative to the original IST date.
    """
    h, m = [int(x) for x in hhmm.split(":")]
    ist_dt = datetime.combine(date.fromisoformat(day_iso), time(h, m), tzinfo=IST)
    et_dt = ist_dt.astimezone(ET)
    tz_label = "EDT" if et_dt.dst() else "EST"
    marker = ""
    if et_dt.date() < ist_dt.date():
        marker = " prev day"
    elif et_dt.date() > ist_dt.date():
        marker = " next day"
    return f"{et_dt.strftime('%H:%M')} {tz_label}{marker}", tz_label


def muhurta_window_for(d: str | date | datetime) -> list[dict]:
    """Return every timed muhurta window recorded for the date.

    Each entry: {type, start_ist, end_ist, start_et, end_et, duration_min}.
    Events without start/end times are omitted here (they are full-day; use
    is_shubh_day() for the boolean).
    """
    iso = _to_iso(d)
    out = []
    for ev in _load().get("events", []):
        if ev["date"] != iso:
            continue
        if ev.get("type") not in _GOLD_RELEVANT_TYPES:
            continue
        s = ev.get("start_ist")
        e = ev.get("end_ist")
        if not s or not e:
            continue
        start_et, _ = _ist_to_et(iso, s)
        end_et, _ = _ist_to_et(iso, e)
        # duration
        sh, sm = [int(x) for x in s.split(":")]
        eh, em = [int(x) for x in e.split(":")]
        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        if end_min < start_min:  # crosses midnight
            end_min += 24 * 60
        out.append({
            "type": ev["type"],
            "name": ev.get("name", ev["type"].title()),
            "start_ist": s,
            "end_ist": e,
            "start_et": start_et,
            "end_et": end_et,
            "duration_min": end_min - start_min,
        })
    return out


def format_muhurta_line(d: str | date | datetime) -> str | None:
    """One-line summary of today's muhurta windows, or None if all events
    are full-day. Example:
      'Pushya Nakshatra window: 10:20-16:45 IST (00:50-07:15 EDT) · 6h 25m'
    """
    wins = muhurta_window_for(d)
    if not wins:
        return None
    parts = []
    for w in wins:
        h, m = divmod(w["duration_min"], 60)
        dur = f"{h}h {m}m" if h else f"{m}m"
        parts.append(
            f"{w['name']}: {w['start_ist']}–{w['end_ist']} IST "
            f"[{w['start_et']} → {w['end_et']}] · {dur}"
        )
    return " | ".join(parts)


def upcoming_shubh_days(from_date: str | date | datetime, days: int = 30) -> list[dict]:
    """Return shubh divas in the next `days` days (inclusive of from_date)."""
    from datetime import timedelta
    start_iso = _to_iso(from_date)
    start = date.fromisoformat(start_iso)
    end = start + timedelta(days=days)
    out = []
    for ev in _load().get("events", []):
        if ev.get("type") not in _GOLD_RELEVANT_TYPES:
            continue
        try:
            ev_d = date.fromisoformat(ev["date"])
        except ValueError:
            continue
        if start <= ev_d <= end:
            out.append(ev)
    out.sort(key=lambda e: e["date"])
    return out


if __name__ == "__main__":
    import sys
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.utcnow().date().isoformat()
    start, end = calendar_coverage()
    print(f"Calendar coverage: {start} to {end}")
    print(f"{day}: shubh={is_shubh_day(day)} — {describe_shubh_day(day) or 'no shubh diva'}")
    upcoming = upcoming_shubh_days(day, 45)
    print(f"Next 45 days: {len(upcoming)} shubh divas")
    for ev in upcoming[:15]:
        print(f"  {ev['date']}  {ev['type']}")
