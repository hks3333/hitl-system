from langgraph.checkpoint.postgres import PostgresSaver
from config import settings

# Open the context to get the actual saver
with PostgresSaver.from_conn_string(settings.DATABASE_URL) as checkpointer:
    checkpointer.setup()  # create tables once
