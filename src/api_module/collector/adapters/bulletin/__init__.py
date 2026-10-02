from ._adapter import BulletinCollectorAdapter
from collector.main import register

register(BulletinCollectorAdapter())
