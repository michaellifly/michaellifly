#!/usr/bin/env python3
"""
Inspect the EasyLog.db schema and show sample rows.
Run this first to verify the database structure before using main.py.

Usage:
  python explore_db.py EasyLog.db
  python explore_db.py           (uses BT_DB_FILE from .env)
"""

import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def explore(db_path: str):
    print(f"\nDatabase: {db_path}\n{'='*60}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()

    print(f"Tables ({len(tables)}):")
    for t in tables:
        name = t["name"]
        count = conn.execute(f"SELECT COUNT(*) FROM \"{name}\"").fetchone()[0]
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info('{name}')")]
        print(f"  {name:30s}  {count:6d} rows   cols: {', '.join(cols)}")

    print()

    # Show sample rows from sleep-related tables
    sleep_tables = [
        t["name"] for t in tables
        if any(k in t["name"].lower() for k in ("sleep", "activity", "log", "record"))
    ]

    for name in sleep_tables:
        print(f"\nSample rows from [{name}]:")
        rows = conn.execute(f"SELECT * FROM \"{name}\" LIMIT 3").fetchall()
        for row in rows:
            print("  ", dict(row))

    conn.close()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.getenv("BT_DB_FILE")
    if not path or not Path(path).exists():
        print("Usage: python explore_db.py path/to/EasyLog.db")
        print("Or set BT_DB_FILE in .env")
        sys.exit(1)
    explore(path)
