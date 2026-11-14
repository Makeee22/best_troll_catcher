import json
import subprocess
import sys
from swarm.synthetic import write


def cli(*args):
    return subprocess.run([sys.executable, "-m", "swarm", *args], capture_output=True, text=True)


def test_run_writes_the_result_and_prints_a_summary(tmp_path):
    comments, profiles = write(str(tmp_path))
    out = tmp_path / "result.json"
    done = cli(comments, "--profiles", profiles, "--out", str(out))
    assert done.returncode == 0, done.stderr
    assert len(json.loads(out.read_text(encoding="utf-8"))["clusters"]) == 3
    assert "synthetic" in done.stdout.lower() and "3 clusters" in done.stdout and "0.8125" in done.stdout


def test_warnings_go_to_standard_error(tmp_path, make_csv):
    path = make_csv(tmp_path, "c.csv", [{"username": f"u{i}", "text": f"a text of five words number {i}"} for i in range(5)])
    done = cli(path)
    assert done.returncode == 0 and "warning: " in done.stderr and "timestamp" in done.stderr


def test_bad_input_is_one_line_and_exit_code_2(tmp_path, make_csv):
    done = cli(make_csv(tmp_path, "c.csv", [{"text": "no username column here at all"}]))
    assert done.returncode == 2 and done.stderr.startswith("error: ") and "username" in done.stderr
    assert "Traceback" not in done.stderr
    assert cli(str(tmp_path / "nope.csv")).returncode == 2
