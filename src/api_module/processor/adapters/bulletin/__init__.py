from ._adapter import BulletinProcessorAdapter
from processor.main import register

register(BulletinProcessorAdapter())
