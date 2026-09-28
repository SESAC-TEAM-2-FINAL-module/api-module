from ._adapter import TideCollectorAdapter
from collector.main import register

register(TideCollectorAdapter())
