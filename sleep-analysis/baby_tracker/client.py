"""
Baby Tracker - Newborn Log (Nighp Software) data client.

The app has NO public REST API. Data is stored in a SQLite database
called EasyLog.db that syncs to iCloud.

Supported sources (in priority order):
  1. EasyLog.db  — SQLite file from iCloud or a Data Clone export
  2. JSON file   — any JSON export or the sample_data file

How to get EasyLog.db on a Mac:
  1. Open Baby Tracker on your iPhone → Settings → Link to Cloud → iCloud (turn on)
  2. Wait for sync to complete
  3. On your Mac, open Finder → Go → Go to Folder → paste:
       ~/Library/Mobile Documents/iCloud~com~nighp~babytracker/Documents/
  4. Copy EasyLog.db to this project folder
  5. Set BT_DB_FILE=EasyLog.db in your .env

Alternative (no Mac needed):
  iPhone → Baby Tracker → Settings → Export Data Clone → Email to yourself
  Unzip the attachment — it contains EasyLog.db (or a .db file).
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from dateutil import parser as dateparser

from .models import Baby, SleepRecord

# Core Data stores dates as seconds since 2001-01-01 (not Unix epoch 1970-01-01)
CORE_DATA_EPOCH_OFFSET = 978307200  # seconds between 1970-01-01 and 2001-01-01

# Activity type codes observed in Baby Tracker's database
SLEEP_TYPE_CODES = {0, 5, 8, 10}  # 0=sleep/nap generics; app-specific codes vary


class BabyTrackerClient:
    def __init__(
        self,
        db_file: Optional[str] = None,
        json_file: Optional[str] = None,
        timezone: str = "America/New_York",
    ):
        self.db_file = db_file or os.getenv("BT_DB_FILE")
        self.json_file = json_file or os.getenv("BT_DATA_FILE")
        self.tz = ZoneInfo(timezone)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_babies(self) -> list[Baby]:
        if self._has_db():
            return self._babies_from_db()
        if self._has_json():
            return self._babies_from_json()
        return self._sample_baby()

    def get_sleep_records(self, baby_id: str, days_back: int = 30) -> list[SleepRecord]:
        if self._has_db():
            records = self._records_from_db(baby_id, days_back)
        elif self._has_json():
            records = self._records_from_json(baby_id)
        else:
            records = self._records_from_json(baby_id)  # will use sample fallback

        cutoff = datetime.now(tz=self.tz) - timedelta(days=days_back)
        records = [r for r in records if r.end_time.astimezone(self.tz) >= cutoff]
        return sorted(records, key=lambda r: r.start_time)

    # ------------------------------------------------------------------
    # SQLite / EasyLog.db source
    # ------------------------------------------------------------------

    def _has_db(self) -> bool:
        return bool(self.db_file and Path(self.db_file).exists())

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def _schema(self) -> dict[str, list[str]]:
        """Return {table_name: [column_names]} for the whole database."""
        with self._connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            return {
                t["name"]: [
                    row[1]
                    for row in conn.execute(f"PRAGMA table_info('{t['name']}')")
                ]
                for t in tables
            }

    def _find_sleep_table(self, schema: dict) -> Optional[str]:
        """Heuristically find the table that holds sleep records."""
        # Prefer tables whose name contains 'sleep' or 'activity'
        for name in schema:
            nl = name.lower()
            if "sleep" in nl:
                return name
        for name in schema:
            nl = name.lower()
            if "activity" in nl or "record" in nl or "log" in nl:
                cols = [c.lower() for c in schema[name]]
                if any(k in cols for k in ("start", "zstart", "starttime", "begin")):
                    return name
        return None

    def _find_baby_table(self, schema: dict) -> Optional[str]:
        for name in schema:
            nl = name.lower()
            if "baby" in nl or "child" in nl or "infant" in nl:
                return name
        return None

    def _babies_from_db(self) -> list[Baby]:
        schema = self._schema()
        table = self._find_baby_table(schema)
        if not table:
            return self._sample_baby()

        cols = [c.lower() for c in schema[table]]
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM \"{table}\"").fetchall()

        babies = []
        for row in rows:
            row = dict(row)
            name = self._pick(row, ["name", "zname", "nickname", "zfirstname"], "Baby")
            bday_raw = self._pick(row, ["birthday", "zbirthday", "birthdate", "zdob", "dob"], None)
            birth = self._parse_dt(bday_raw) if bday_raw else datetime(2024, 1, 1, tzinfo=self.tz)
            bid = str(self._pick(row, ["z_pk", "_id", "id", "uuid", "zuuid"], ""))
            babies.append(Baby(name=str(name), birth_date=birth, baby_id=bid))
        return babies or self._sample_baby()

    def _records_from_db(self, baby_id: str, days_back: int) -> list[SleepRecord]:
        schema = self._schema()
        table = self._find_sleep_table(schema)
        if not table:
            raise ValueError(
                f"Could not find a sleep/activity table in {self.db_file}.\n"
                f"Tables found: {list(schema.keys())}\n"
                "Run: python explore_db.py to inspect the schema."
            )

        cols = [c.lower() for c in schema[table]]
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM \"{table}\"").fetchall()

        records = []
        for row in rows:
            row = dict(row)
            try:
                start_raw = self._pick(row, ["start", "zstart", "starttime", "zstarttime", "begin", "time"], None)
                end_raw = self._pick(row, ["end", "zend", "endtime", "zendtime", "stop", "waketime", "zwaketime"], None)
                if start_raw is None or end_raw is None:
                    continue
                start = self._parse_dt(start_raw)
                end = self._parse_dt(end_raw)
                if start >= end:
                    continue
                duration_h = (end - start).total_seconds() / 3600
                if duration_h > 16 or duration_h < 0.05:
                    continue
                note = str(self._pick(row, ["note", "znote", "comment", "zcomment", "memo"], "") or "")
                rid = str(self._pick(row, ["z_pk", "_id", "id", "uuid", "zuuid"], ""))
                records.append(SleepRecord(start_time=start, end_time=end, note=note, record_id=rid))
            except (TypeError, ValueError, OSError):
                continue
        return records

    # ------------------------------------------------------------------
    # JSON file source  (sample data or manual export)
    # ------------------------------------------------------------------

    def _has_json(self) -> bool:
        path = self.json_file
        if not path:
            path = str(Path(__file__).parent.parent / "sample_data" / "sample_sleep.json")
        return Path(path).exists()

    def _load_json(self) -> dict:
        path = self.json_file
        if not path:
            path = str(Path(__file__).parent.parent / "sample_data" / "sample_sleep.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _babies_from_json(self) -> list[Baby]:
        data = self._load_json()
        raw_list = data.get("babies") or data.get("children") or []
        if not raw_list and "name" in data:
            raw_list = [data]
        return [self._parse_baby_json(b) for b in raw_list] or self._sample_baby()

    def _records_from_json(self, baby_id: str) -> list[SleepRecord]:
        data = self._load_json()
        if isinstance(data, list):
            all_records = data
        elif "records" in data:
            all_records = data["records"]
        elif "sleepRecords" in data:
            all_records = data["sleepRecords"]
        else:
            all_records = []
            for baby in data.get("babies", data.get("children", [])):
                if not baby_id or str(baby.get("id", baby.get("_id", ""))) == baby_id:
                    all_records.extend(baby.get("records", baby.get("sleep", [])))

        records = []
        for r in all_records:
            rec_type = (r.get("type") or r.get("recordType") or "sleep").lower()
            if rec_type not in ("sleep", "nap", ""):
                continue
            try:
                start = dateparser.parse(str(r.get("start") or r.get("startTime") or r.get("time")))
                end = dateparser.parse(str(r.get("end") or r.get("endTime") or r.get("wakeTime")))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=self.tz)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=self.tz)
                records.append(SleepRecord(
                    start_time=start,
                    end_time=end,
                    note=str(r.get("note", r.get("comment", "")) or ""),
                    record_id=str(r.get("id", r.get("_id", "")) or ""),
                ))
            except (TypeError, ValueError):
                continue
        return records

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_dt(self, value) -> datetime:
        """Parse a timestamp that may be:
        - A float/int: Unix epoch seconds, OR Core Data epoch (since 2001-01-01)
        - A string: ISO 8601 or any dateutil-parseable format
        """
        if isinstance(value, (int, float)):
            ts = float(value)
            # Core Data timestamps are ~700M–800M range (years 2022–2026)
            # Unix timestamps for same range are ~1.6B–1.8B
            # Heuristic: if < 1_000_000_000 it's likely Core Data epoch
            if ts < 1_000_000_000:
                ts += CORE_DATA_EPOCH_OFFSET
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(self.tz)
            return dt
        # String parsing
        dt = dateparser.parse(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.tz)
        return dt

    @staticmethod
    def _pick(row: dict, keys: list[str], default):
        """Return first matching key from row (case-insensitive)."""
        row_lower = {k.lower(): v for k, v in row.items()}
        for k in keys:
            if k.lower() in row_lower:
                return row_lower[k.lower()]
        return default

    def _parse_baby_json(self, raw: dict) -> Baby:
        bday_raw = raw.get("birthday") or raw.get("birthDate") or raw.get("dob") or "2024-01-01"
        birth = dateparser.parse(str(bday_raw))
        if birth.tzinfo is None:
            birth = birth.replace(tzinfo=self.tz)
        return Baby(
            name=raw.get("name", "Baby"),
            birth_date=birth,
            baby_id=str(raw.get("id", raw.get("_id", "")) or ""),
        )

    def _sample_baby(self) -> list[Baby]:
        return [Baby(
            name="Baby",
            birth_date=datetime(2024, 6, 1, tzinfo=self.tz),
            baby_id="",
        )]
