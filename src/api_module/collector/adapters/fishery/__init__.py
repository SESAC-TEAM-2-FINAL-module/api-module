from ._adapter import FisheryBackfillAdapter, FisheryCompletenessAdapter
from collector.main import register

register(FisheryBackfillAdapter())
register(FisheryCompletenessAdapter())
