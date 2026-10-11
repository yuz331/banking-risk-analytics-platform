"""Run named SQL exploration queries against a synthetic SQLite snapshot."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "analysis.sql"


def read_queries():
    queries = {}
    name = None
    lines = []
    for line in SQL_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("-- name: "):
            if name:
                queries[name] = "\n".join(lines)
            name = line.removeprefix("-- name: ").strip()
            lines = []
        elif name:
            lines.append(line)
    if name:
        queries[name] = "\n".join(lines)
    return queries


def run_analysis(db_path, query="all"):
    queries = read_queries()
    if query != "all":
        queries = {query: queries[query]}
    # mode=ro refuses a missing file and prevents accidental database creation.
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        return {name: [dict(row) for row in connection.execute(sql)]
                for name, sql in queries.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/banking.db"))
    parser.add_argument("--query", choices=("all", *read_queries()), default="overview")
    args = parser.parse_args()
    try:
        result = run_analysis(args.db, args.query)
    except (OSError, sqlite3.Error) as error:
        parser.exit(1, f"Analysis failed: {error}\nRun src/load_database.py first.\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
