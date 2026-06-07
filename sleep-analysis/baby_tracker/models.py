from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SleepRecord:
    start_time: datetime
    end_time: datetime
    note: str = ""
    record_id: str = ""

    @property
    def duration_minutes(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 60

    @property
    def duration_hours(self) -> float:
        return self.duration_minutes / 60

    @property
    def wake_time(self) -> datetime:
        return self.end_time

    @property
    def sleep_time(self) -> datetime:
        return self.start_time

    @property
    def is_night_sleep(self) -> bool:
        # Night sleep: starts between 6pm and midnight, or before 6am
        hour = self.start_time.hour
        return hour >= 18 or hour < 6

    @property
    def is_nap(self) -> bool:
        return not self.is_night_sleep

    def __repr__(self):
        return (
            f"SleepRecord({self.start_time.strftime('%Y-%m-%d %H:%M')} -> "
            f"{self.end_time.strftime('%H:%M')}, {self.duration_hours:.1f}h)"
        )


@dataclass
class Baby:
    name: str
    birth_date: datetime
    baby_id: str = ""

    @property
    def age_in_weeks(self) -> int:
        now = datetime.now(tz=self.birth_date.tzinfo) if self.birth_date.tzinfo else datetime.now()
        delta = now - self.birth_date
        return int(delta.days / 7)

    @property
    def age_in_months(self) -> int:
        now = datetime.now(tz=self.birth_date.tzinfo) if self.birth_date.tzinfo else datetime.now()
        delta = now - self.birth_date
        return int(delta.days / 30.44)

    @property
    def age_label(self) -> str:
        months = self.age_in_months
        if months < 1:
            return f"{self.age_in_weeks} weeks"
        elif months < 24:
            return f"{months} months"
        else:
            return f"{months // 12} years {months % 12} months"
