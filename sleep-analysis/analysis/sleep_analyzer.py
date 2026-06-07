"""
Core sleep analysis engine.

Computes daily and weekly metrics from SleepRecord lists:
  - Total sleep per day (night + naps)
  - Night sleep duration & quality
  - Wake-up time trends
  - Bedtime consistency
  - Wake windows (time awake between sleeps)
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import mean, stdev
from typing import Optional

from baby_tracker.models import Baby, SleepRecord

# Age-based sleep targets (hours per 24h)
SLEEP_TARGETS = {
    # (min_months, max_months): (min_hours, max_hours)
    (0, 1): (14, 17),
    (1, 3): (14, 17),
    (3, 6): (12, 16),
    (6, 12): (12, 16),
    (12, 18): (11, 14),
    (18, 36): (11, 14),
    (36, 60): (10, 13),
}

# Typical wake window targets by age (minutes)
WAKE_WINDOWS = {
    (0, 1): (45, 60),
    (1, 3): (60, 90),
    (3, 6): (90, 120),
    (6, 9): (120, 180),
    (9, 12): (150, 210),
    (12, 18): (180, 270),
    (18, 36): (240, 360),
    (36, 60): (360, 480),
}


@dataclass
class DailySummary:
    date: date
    total_sleep_hours: float
    night_sleep_hours: float
    nap_sleep_hours: float
    nap_count: int
    bedtime: Optional[datetime]
    wake_time: Optional[datetime]
    first_morning_wake: Optional[datetime]
    records: list[SleepRecord] = field(default_factory=list)

    @property
    def wake_hour(self) -> Optional[float]:
        if self.first_morning_wake:
            return self.first_morning_wake.hour + self.first_morning_wake.minute / 60
        return None


@dataclass
class SleepStats:
    avg_total_sleep: float
    avg_night_sleep: float
    avg_nap_count: float
    avg_bedtime_hour: float
    avg_wake_hour: float
    wake_hour_trend: list[float]   # chronological wake hours for trend detection
    bedtime_trend: list[float]
    total_sleep_trend: list[float]
    target_min: float
    target_max: float
    age_months: int


class SleepAnalyzer:
    def __init__(self, baby: Baby, records: list[SleepRecord]):
        self.baby = baby
        self.records = sorted(records, key=lambda r: r.start_time)

    def daily_summaries(self, days: int = 14) -> list[DailySummary]:
        today = date.today()
        summaries = []
        for i in range(days - 1, -1, -1):
            day = today - timedelta(days=i)
            summaries.append(self._summarize_day(day))
        return summaries

    def stats(self, days: int = 14) -> SleepStats:
        summaries = self.daily_summaries(days)
        nonempty = [s for s in summaries if s.total_sleep_hours > 0]

        avg_total = mean(s.total_sleep_hours for s in nonempty) if nonempty else 0
        avg_night = mean(s.night_sleep_hours for s in nonempty) if nonempty else 0
        avg_naps = mean(s.nap_count for s in nonempty) if nonempty else 0

        wake_hours = [s.wake_hour for s in summaries if s.wake_hour is not None]
        bedtimes = []
        for s in summaries:
            if s.bedtime:
                h = s.bedtime.hour + s.bedtime.minute / 60
                # Normalize: bedtime after midnight treated as 24+
                if h < 12:
                    h += 24
                bedtimes.append(h)

        target = self._sleep_target()
        return SleepStats(
            avg_total_sleep=round(avg_total, 2),
            avg_night_sleep=round(avg_night, 2),
            avg_nap_count=round(avg_naps, 1),
            avg_bedtime_hour=round(mean(bedtimes), 2) if bedtimes else 0,
            avg_wake_hour=round(mean(wake_hours), 2) if wake_hours else 0,
            wake_hour_trend=wake_hours,
            bedtime_trend=bedtimes,
            total_sleep_trend=[s.total_sleep_hours for s in summaries],
            target_min=target[0],
            target_max=target[1],
            age_months=self.baby.age_in_months,
        )

    def wake_windows(self) -> list[float]:
        """Return list of wake windows in minutes between consecutive sleep records."""
        windows = []
        for i in range(1, len(self.records)):
            gap = (
                self.records[i].start_time - self.records[i - 1].end_time
            ).total_seconds() / 60
            if 0 < gap < 600:  # ignore gaps > 10h (likely overnight)
                windows.append(round(gap, 1))
        return windows

    def early_wake_streak(self, early_hour: float = 6.0) -> int:
        """Count consecutive recent days where morning wake < early_hour."""
        summaries = self.daily_summaries(14)
        streak = 0
        for s in reversed(summaries):
            if s.wake_hour is not None and s.wake_hour < early_hour:
                streak += 1
            else:
                break
        return streak

    def bedtime_drift(self, days: int = 7) -> float:
        """Return minutes bedtime has shifted over the last N days (+ = later, - = earlier)."""
        summaries = self.daily_summaries(days)
        bedtimes = []
        for s in summaries:
            if s.bedtime:
                h = s.bedtime.hour + s.bedtime.minute / 60
                if h < 12:
                    h += 24
                bedtimes.append(h)
        if len(bedtimes) < 2:
            return 0.0
        return round((bedtimes[-1] - bedtimes[0]) * 60, 1)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _records_for_day(self, day: date) -> list[SleepRecord]:
        """
        Records "belonging" to a calendar day.
        Night sleep that starts on eve (>=18:00) and ends next morning
        is attributed to the start date.
        """
        result = []
        for r in self.records:
            if r.start_time.date() == day:
                result.append(r)
            elif r.end_time.date() == day and r.is_night_sleep:
                # Spans midnight — include the whole record in the start day
                pass
        return result

    def _summarize_day(self, day: date) -> DailySummary:
        records = self._records_for_day(day)
        night_records = [r for r in records if r.is_night_sleep]
        nap_records = [r for r in records if r.is_nap]

        night_hours = sum(r.duration_hours for r in night_records)
        nap_hours = sum(r.duration_hours for r in nap_records)
        total_hours = night_hours + nap_hours

        # Bedtime = last sleep start before midnight
        night_starts = sorted(
            [r.start_time for r in night_records if r.start_time.hour >= 18],
            reverse=True,
        )
        bedtime = night_starts[0] if night_starts else None

        # Morning wake = earliest end_time on this date after 4am
        # Also check cross-midnight records that END on this day
        morning_wakes = sorted(
            [r.end_time for r in self.records
             if r.end_time.date() == day and r.end_time.hour >= 4 and r.is_night_sleep]
        )
        first_wake = morning_wakes[0] if morning_wakes else None

        # Last wake of the day
        all_ends = sorted([r.end_time for r in records])
        last_wake = all_ends[-1] if all_ends else None

        return DailySummary(
            date=day,
            total_sleep_hours=round(total_hours, 2),
            night_sleep_hours=round(night_hours, 2),
            nap_sleep_hours=round(nap_hours, 2),
            nap_count=len(nap_records),
            bedtime=bedtime,
            wake_time=last_wake,
            first_morning_wake=first_wake,
            records=records,
        )

    def _sleep_target(self) -> tuple[float, float]:
        months = self.baby.age_in_months
        for (lo, hi), target in SLEEP_TARGETS.items():
            if lo <= months < hi:
                return target
        return (10, 14)
