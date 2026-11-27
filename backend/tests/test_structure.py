from pathlib import Path

MAX_LINES = 200
ROOT = Path(__file__).resolve().parent.parent


def test_every_python_file_stays_small() -> None:
    files = [
        *ROOT.glob("src/**/*.py"),
        *ROOT.glob("tests/**/*.py"),
        *ROOT.glob("migrations/**/*.py"),
    ]
    too_long = {
        str(path.relative_to(ROOT)): count
        for path in files
        if (count := len(path.read_text().splitlines())) > MAX_LINES
    }
    assert not too_long, f"split these by subject: {too_long}"
