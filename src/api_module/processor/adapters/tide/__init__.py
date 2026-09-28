from ._adapter import TideProcessorAdapter
from processor.main import register

register(TideProcessorAdapter())
