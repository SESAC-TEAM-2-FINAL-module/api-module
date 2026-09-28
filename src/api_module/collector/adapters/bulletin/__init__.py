from ._adapter import BulletinCollectorAdapter, BulletinCompletenessAdapter
from collector.main import register

register(BulletinCollectorAdapter())
register(BulletinCompletenessAdapter())
