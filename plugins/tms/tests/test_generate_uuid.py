"""UUID 생성 CLI는 도구 입력에 바로 사용할 한 줄만 출력한다."""
import subprocess
import sys
from pathlib import Path
from uuid import UUID


SCRIPT = Path(__file__).resolve().parents[1] / "skills/incidents/scripts/generate_uuid.py"


def test_uuid_cli_output():
    values = []
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=True
        )
        value = result.stdout.strip()
        parsed = UUID(value)
        assert parsed.version == 4
        assert str(parsed) == value
        assert result.stdout == value + "\n"
        assert result.stderr == ""
        values.append(value)
    assert values[0] != values[1]
