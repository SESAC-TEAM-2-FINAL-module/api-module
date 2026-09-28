import sys
from pathlib import Path

# src/api_module을 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parents[1] / "src" / "api_module"))
