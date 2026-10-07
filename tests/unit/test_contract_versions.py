"""큐 계약 버전 한 곳 (개정 22 — 7.11 V1 "5종 이미지의 기대 계약 버전이 같다")"""
import json
import re
from pathlib import Path

import yaml

from common.contract_check import QUEUE_CONTRACT

_ROOT = Path(__file__).parents[2]


def test_queue_contract_matches_definitions_gate_and_notice():
    defs = yaml.safe_load((_ROOT / "config" / "definitions.yaml").read_text("utf-8"))
    expected = yaml.safe_load((_ROOT / "ci" / "gate" / "expected.yaml").read_text("utf-8"))
    notice = json.loads((_ROOT / "contracts" / "release" / "image_notice.json").read_text("utf-8"))
    assert defs["contracts"]["queue"] == QUEUE_CONTRACT
    assert expected["settings"]["contracts"]["queue"] == QUEUE_CONTRACT
    assert QUEUE_CONTRACT in notice["contracts_version"].split(" / ")
    assert (_ROOT / "contracts" / "queue" / f"{QUEUE_CONTRACT}.json").is_file()


def test_no_stage_hardcodes_queue_version():
    """단계 코드는 상수만 쓴다 — 버전 문자열은 common/contract_check/_message.py 한 곳"""
    allowed = _ROOT / "src" / "api_module" / "common" / "contract_check" / "_message.py"
    pat = re.compile(r"""['"]queue-v\d+['"]""")
    hits = [str(p.relative_to(_ROOT)) for p in (_ROOT / "src").rglob("*.py")
            if p != allowed and pat.search(p.read_text("utf-8"))]
    assert hits == []
