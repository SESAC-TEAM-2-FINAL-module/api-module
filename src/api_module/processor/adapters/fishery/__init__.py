from ._adapter import FisheryProcessorAdapter, FisheryWatchProcessorAdapter
from processor.main import register

register(FisheryProcessorAdapter())
register(FisheryWatchProcessorAdapter())
