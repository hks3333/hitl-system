# event_broker.py
import dramatiq
# from dramatiq.brokers.redis import RedisBroker  <- REMOVE THIS
from dramatiq.brokers.rabbitmq import RabbitmqBroker # <- ADD THIS
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    RABBITMQ_URL: str # <- CHANGE THIS
    class Config:
        env_file = ".env"

settings = Settings()

# Configure the RabbitMQ broker
# rabbitmq_broker = RabbitmqBroker(url=settings.RABBITMQ_URL) # <- CHANGE THIS
dramatiq.set_broker(rabbitmq_broker)