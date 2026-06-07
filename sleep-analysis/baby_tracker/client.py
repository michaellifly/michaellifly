"""
Baby Tracker data client.

Supports two data sources:
  1. JSON/CSV file export  (set DATA_SOURCE=file in .env)
  2. Baby Tracker API      (set DATA_SOURCE=api, API_EMAIL, API_PASSWORD in .env)

The Baby Tracker app by Nighp Software syncs data via a REST API.
We attempt login at their sync endpoint and pull sleep records.
If the API changes or credentials are wrong the client falls back
to any local export file found at DATA_FILE_PATH.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from dateutil import parser as dateparser

from .models import Baby, SleepRecord

API_BASE = "https://www.nighp.com/babytracker"
LOGIN_URL = f"{API_BASE}/login"
RECORDS_URL = f"{API_BASE}/records"


class BabyTrackerClient:
    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        data_file: Optional[str] = None,
        timezone: str = "America/New_York",
    ):
        self.email = email or os.getenv("BT_EMAIL")
        self.password = password or os.getenv("BT_PASSWORD")
        self.data_file = data_file or os.getenv("BT_DATA_FILE")
        self.tz = ZoneInfo(timezone)
        self._session = requests.Session()
        self._token: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_babies(self) -> list[Baby]:
        if self._use_file():
            return self._babies_from_file()
        return self._babies_from_api()

    def get_sleep_records(
        self,
        baby_id: str,
        days_back: int = 30,
    ) -> list[SleepRecord]:
        if self._use_file():
            records = self._records_from_file(baby_id)
        else:
            records = self._records_from_api(baby_id, days_back)

        cutoff = datetime.now(tz=self.tz) - timedelta(days=days_back)
        records = [r for r in records if r.end_time >= cutoff]
        return sorted(records, key=lambda r: r.start_time)

    # ------------------------------------------------------------------
    # API source
    # ------------------------------------------------------------------

    def _authenticate(self) -> bool:
        if not self.email or not self.password:
            return False
        try:
            resp = self._session.post(
                LOGIN_URL,
                json={"email": self.email, "password": self.password},
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                self._token = data.get("token") or data.get("access_token")
                if self._token:
                    self._session.headers["Authorization"] = f"Bearer {self._token}"
                    return True
        except requests.RequestException:
            pass
        return False

    def _babies_from_api(self) -> list[Baby]:
        if not self._token and not self._authenticate():
            raise ConnectionError(
                "Cannot authenticate with Baby Tracker API. "
                "Check BT_EMAIL and BT_PASSWORD in your .env file."
            )
        try:
            resp = self._session.get(f"{API_BASE}/babies", timeout=10)
            resp.raise_for_status()
            return [self._parse_baby(b) for b in resp.json()]
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to fetch babies from API: {e}") from e

    def _records_from_api(self, baby_id: str, days_back: int) -> list[SleepRecord]:
        if not self._token and not self._authenticate():
            raise ConnectionError("Not authenticated.")
        since = (datetime.now(tz=self.tz) - timedelta(days=days_back)).isoformat()
        try:
            resp = self._session.get(
                RECORDS_URL,
                params={"baby_id": baby_id, "type": "sleep", "since": since},
                timeout=10,
            )
            resp.raise_for_status()
            return [self._parse_record(r) for r in resp.json()]
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to fetch records from API: {e}") from e

    # ------------------------------------------------------------------
    # File source
    # ------------------------------------------------------------------

    def _use_file(self) -> bool:
        return bool(self.data_file and os.path.exists(self.data_file))

    def _load_file(self) -> dict:
        with open(self.data_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _babies_from_file(self) -> list[Baby]:
        data = self._load_file()
        babies_raw = data.get("babies") or data.get("children") or []
        if not babies_raw and "name" in data:
            babies_raw = [data]
        return [self._parse_baby(b) for b in babies_raw]

    def _records_from_file(self, baby_id: str) -> list[SleepRecord]:
        data = self._load_file()
        # Handle both flat list and nested structure
        if isinstance(data, list):
            all_records = data
        elif "records" in data:
            all_records = data["records"]
        elif "sleepRecords" in data:
            all_records = data["sleepRecords"]
        else:
            # Try to find records under each baby
            all_records = []
            for baby in data.get("babies", data.get("children", [])):
                if baby.get("id") == baby_id or not baby_id:
                    all_records.extend(baby.get("records", baby.get("sleep", [])))

        sleep_records = []
        for r in all_records:
            rec_type = (r.get("type") or r.get("recordType") or "").lower()
            if rec_type in ("sleep", "nap", "") :
                try:
                    sleep_records.append(self._parse_record(r))
                except (KeyError, ValueError):
                    continue
        return sleep_records

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_baby(self, raw: dict) -> Baby:
        birth_raw = (
            raw.get("birthday")
            or raw.get("birthDate")
            or raw.get("dob")
            or "2024-01-01"
        )
        birth = dateparser.parse(str(birth_raw))
        if birth.tzinfo is None:
            birth = birth.replace(tzinfo=self.tz)
        return Baby(
            name=raw.get("name", "Baby"),
            birth_date=birth,
            baby_id=str(raw.get("id", raw.get("_id", ""))),
        )

    def _parse_record(self, raw: dict) -> SleepRecord:
        start_raw = (
            raw.get("start")
            or raw.get("startTime")
            or raw.get("start_time")
            or raw.get("time")
        )
        end_raw = (
            raw.get("end")
            or raw.get("endTime")
            or raw.get("end_time")
            or raw.get("wakeTime")
        )
        start = dateparser.parse(str(start_raw))
        end = dateparser.parse(str(end_raw))
        if start.tzinfo is None:
            start = start.replace(tzinfo=self.tz)
        if end.tzinfo is None:
            end = end.replace(tzinfo=self.tz)
        return SleepRecord(
            start_time=start,
            end_time=end,
            note=raw.get("note", raw.get("comment", "")),
            record_id=str(raw.get("id", raw.get("_id", ""))),
        )
