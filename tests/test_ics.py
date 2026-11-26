from datetime import date

import yaml

from planner.cli import main
from planner.models import Constraints

ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1
DTSTART;VALUE=DATE:20270113
DTEND;VALUE=DATE:20270115
SUMMARY:Logopeda
DESCRIPTION:#PL #Basia
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART;VALUE=DATE:20270120
SUMMARY:Okulista
END:VEVENT
END:VCALENDAR
"""


def test_import_ics(tmp_path):
    (tmp_path / "f.ics").write_text(ICS)
    c = tmp_path / "c.yaml"
    a = tmp_path / "a.yaml"
    c.write_text(open("examples/constraints.yaml").read())
    a.write_text(open("examples/accommodation.yaml").read())
    rc = main(
        [
            "import-ics",
            "--ics",
            f"Family={tmp_path / 'f.ics'}",
            "--constraints",
            str(c),
            "--accommodation",
            str(a),
        ]
    )
    assert rc == 0
    data = Constraints.model_validate(yaml.safe_load(c.read_text()))
    assert data.presence[0].end == date(2027, 1, 14)
    assert data.presence[0].who == ["Basia"]
    assert len(data.presence) == 1  # untagged one is listed for Martin, not guessed


def test_build(tmp_path):
    rc = main(
        [
            "build",
            "--constraints",
            "examples/constraints.yaml",
            "--accommodation",
            "examples/accommodation.yaml",
            "--transport",
            "examples/options.yaml",
            "--site",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert (tmp_path / "index.html").exists()
