import dramatiq
from dramatiq.brokers.rabbitmq import RabbitmqBroker
from config import settings

# Configure the RabbitMQ broker
rabbitmq_broker = RabbitmqBroker(url=settings.RABBITMQ_URL)
dramatiq.set_broker(rabbitmq_broker)