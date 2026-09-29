from ._adapter import LineCollectorAdapter, LineCompletenessAdapter
from collector.main import register

register(LineCollectorAdapter())
register(LineCompletenessAdapter())
