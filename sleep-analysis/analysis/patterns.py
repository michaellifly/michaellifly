"""
Trend and pattern detection on top of DailySummary data.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, stdev
from typing import Optional

from .sleep_analyzer import DailySummary, SleepStats


@dataclass
class Pattern:
    name: str
    severity: str          # "info" | "warning" | "concern"
    description: str
    data_points: dict      # raw numbers that triggered this pattern


class PatternDetector:
    def __init__(self, summaries: list[DailySummary], stats: SleepStats):
        self.summaries = summaries
        self.stats = stats

    def detect_all(self) -> list[Pattern]:
        patterns = []
        patterns.extend(self._early_waking_patterns())
        patterns.extend(self._sleep_debt_patterns())
        patterns.extend(self._bedtime_patterns())
        patterns.extend(self._nap_patterns())
        patterns.extend(self._wake_window_patterns())
        return patterns

    def _early_waking_patterns(self) -> list[Pattern]:
        patterns = []
        recent = [s for s in self.summaries[-7:] if s.wake_hour is not None]
        if not recent:
            return patterns

        early_days = [s for s in recent if s.wake_hour < 6.0]
        very_early_days = [s for s in recent if s.wake_hour < 5.0]

        # Check for streak
        streak = 0
        for s in reversed(self.summaries):
            if s.wake_hour is not None and s.wake_hour < 6.0:
                streak += 1
            else:
                break

        if streak >= 3:
            wake_times = [
                f"{s.first_morning_wake.strftime('%H:%M')} ({s.date})"
                for s in self.summaries[-streak:]
                if s.first_morning_wake
            ]
            patterns.append(Pattern(
                name="Early Wake Streak",
                severity="concern",
                description=(
                    f"Baby has woken before 6:00 AM for {streak} consecutive days. "
                    "This is likely a pattern, not a fluke."
                ),
                data_points={"streak_days": streak, "wake_times": wake_times},
            ))
        elif len(early_days) >= 2:
            patterns.append(Pattern(
                name="Frequent Early Waking",
                severity="warning",
                description=f"Baby woke before 6:00 AM on {len(early_days)} of the last 7 days.",
                data_points={"early_wake_days": len(early_days)},
            ))

        if very_early_days:
            patterns.append(Pattern(
                name="Very Early Waking (<5 AM)",
                severity="concern",
                description=f"Baby woke before 5:00 AM on {len(very_early_days)} day(s) recently.",
                data_points={"count": len(very_early_days)},
            ))

        # Drifting earlier over time
        wake_hours = [s.wake_hour for s in self.summaries if s.wake_hour is not None]
        if len(wake_hours) >= 5:
            first_half = mean(wake_hours[: len(wake_hours) // 2])
            second_half = mean(wake_hours[len(wake_hours) // 2 :])
            drift = (second_half - first_half) * 60
            if drift < -20:
                patterns.append(Pattern(
                    name="Wake Time Drifting Earlier",
                    severity="warning",
                    description=(
                        f"Average wake time has shifted {abs(drift):.0f} minutes earlier "
                        "over the analysis window."
                    ),
                    data_points={"drift_minutes": round(drift, 1)},
                ))
        return patterns

    def _sleep_debt_patterns(self) -> list[Pattern]:
        patterns = []
        recent = [s for s in self.summaries[-7:] if s.total_sleep_hours > 0]
        if not recent:
            return patterns

        avg = mean(s.total_sleep_hours for s in recent)
        shortfall = self.stats.target_min - avg

        if shortfall > 1.5:
            patterns.append(Pattern(
                name="Significant Sleep Debt",
                severity="concern",
                description=(
                    f"Baby averages {avg:.1f}h/day but needs {self.stats.target_min}–"
                    f"{self.stats.target_max}h. That's a {shortfall:.1f}h daily shortfall."
                ),
                data_points={"avg_sleep": round(avg, 2), "target_min": self.stats.target_min},
            ))
        elif shortfall > 0.5:
            patterns.append(Pattern(
                name="Mild Sleep Deficit",
                severity="warning",
                description=(
                    f"Baby is getting {avg:.1f}h/day vs the {self.stats.target_min}h minimum "
                    "recommended for this age."
                ),
                data_points={"avg_sleep": round(avg, 2)},
            ))

        # Increasing deficit trend
        if len(recent) >= 4:
            early = mean(s.total_sleep_hours for s in recent[:2])
            late = mean(s.total_sleep_hours for s in recent[-2:])
            if early - late > 1.0:
                patterns.append(Pattern(
                    name="Declining Sleep Trend",
                    severity="warning",
                    description=f"Total sleep has dropped ~{early - late:.1f}h over the past week.",
                    data_points={"early_avg": round(early, 2), "late_avg": round(late, 2)},
                ))
        return patterns

    def _bedtime_patterns(self) -> list[Pattern]:
        patterns = []
        bedtimes = [
            s.bedtime.hour + s.bedtime.minute / 60
            for s in self.summaries
            if s.bedtime and s.bedtime.hour >= 18
        ]
        if len(bedtimes) < 3:
            return patterns

        # Late bedtime
        avg_bt = mean(bedtimes)
        if avg_bt > 21.5:
            patterns.append(Pattern(
                name="Late Bedtime",
                severity="warning",
                description=(
                    f"Average bedtime is {self._fmt_hour(avg_bt)}, which may cause "
                    "overtiredness and early morning waking."
                ),
                data_points={"avg_bedtime": self._fmt_hour(avg_bt)},
            ))

        # Inconsistent bedtime
        if len(bedtimes) >= 4 and stdev(bedtimes) > 0.75:
            patterns.append(Pattern(
                name="Inconsistent Bedtime",
                severity="warning",
                description=(
                    f"Bedtime varies by >{stdev(bedtimes)*60:.0f} minutes. "
                    "Consistency helps regulate the circadian rhythm."
                ),
                data_points={"stdev_minutes": round(stdev(bedtimes) * 60, 1)},
            ))

        # Bedtime creep (getting later)
        if len(bedtimes) >= 5:
            first = mean(bedtimes[: len(bedtimes) // 2])
            last = mean(bedtimes[len(bedtimes) // 2 :])
            if last - first > 0.5:
                patterns.append(Pattern(
                    name="Bedtime Creeping Later",
                    severity="info",
                    description=(
                        f"Bedtime has shifted ~{(last - first)*60:.0f} minutes later "
                        "over the analysis period."
                    ),
                    data_points={"drift_minutes": round((last - first) * 60, 1)},
                ))
        return patterns

    def _nap_patterns(self) -> list[Pattern]:
        patterns = []
        recent = [s for s in self.summaries[-7:] if s.total_sleep_hours > 0]
        if not recent:
            return patterns

        avg_naps = mean(s.nap_count for s in recent)
        age_months = self.stats.age_months

        # Expected nap count by age
        if 6 <= age_months < 9 and avg_naps < 2:
            patterns.append(Pattern(
                name="Too Few Naps",
                severity="warning",
                description=f"At {age_months} months, 2-3 naps/day are typical. Baby is averaging {avg_naps:.1f}.",
                data_points={"avg_naps": round(avg_naps, 1)},
            ))
        elif 9 <= age_months < 15 and avg_naps < 1:
            patterns.append(Pattern(
                name="Missing Nap",
                severity="warning",
                description=f"At {age_months} months, 1-2 naps/day is typical. Baby is averaging {avg_naps:.1f}.",
                data_points={"avg_naps": round(avg_naps, 1)},
            ))

        # Short nap days correlate with early waking
        short_nap_days = [s for s in recent if 0 < s.nap_sleep_hours < 1.5 and s.nap_count > 0]
        short_then_early = [
            s for s in short_nap_days
            if s.wake_hour is not None and s.wake_hour < 6.0
        ]
        if len(short_then_early) >= 2:
            patterns.append(Pattern(
                name="Short Naps Linked to Early Waking",
                severity="info",
                description=(
                    f"On {len(short_then_early)} days with short naps (<1.5h total), "
                    "baby also woke early. Insufficient daytime sleep can cause early rising."
                ),
                data_points={"occurrences": len(short_then_early)},
            ))
        return patterns

    def _wake_window_patterns(self) -> list[Pattern]:
        patterns = []
        age_months = self.stats.age_months

        # Expected window from table
        expected = None
        from analysis.sleep_analyzer import WAKE_WINDOWS
        for (lo, hi), (wmin, wmax) in WAKE_WINDOWS.items():
            if lo <= age_months < hi:
                expected = (wmin, wmax)
                break
        if not expected:
            return patterns

        # Look at last-window-before-bed (tends to cause early waking if too long)
        last_windows = []
        for i, s in enumerate(self.summaries[-7:]):
            if s.records:
                sorted_recs = sorted(s.records, key=lambda r: r.start_time)
                for j in range(len(sorted_recs) - 1):
                    if sorted_recs[j + 1].is_night_sleep:
                        gap = (
                            sorted_recs[j + 1].start_time - sorted_recs[j].end_time
                        ).total_seconds() / 60
                        if gap > 0:
                            last_windows.append(gap)

        if last_windows:
            avg_last = mean(last_windows)
            if avg_last > expected[1] * 1.3:
                patterns.append(Pattern(
                    name="Last Wake Window Too Long",
                    severity="warning",
                    description=(
                        f"The average last wake window before bed is {avg_last:.0f} min "
                        f"vs the recommended {expected[0]}–{expected[1]} min. "
                        "Overtiredness at bedtime is a common cause of early morning waking."
                    ),
                    data_points={
                        "avg_last_window": round(avg_last, 1),
                        "target_max": expected[1],
                    },
                ))
        return patterns

    @staticmethod
    def _fmt_hour(h: float) -> str:
        hh = int(h) % 24
        mm = int((h % 1) * 60)
        suffix = "AM" if hh < 12 else "PM"
        hh12 = hh if hh <= 12 else hh - 12
        return f"{hh12}:{mm:02d} {suffix}"
