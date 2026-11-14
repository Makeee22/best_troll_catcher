import csv

import pytest


def _make_csv(tmp_path, name, rows, delimiter=","):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    path = tmp_path / name
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=delimiter, restval="")
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


@pytest.fixture
def make_csv():
    return _make_csv
