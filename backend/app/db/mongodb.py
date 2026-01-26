import motor.motor_asyncio
from app.core.config import settings

class MongoDB:
    client: motor.motor_asyncio.AsyncIOMotorClient = None
    db = None

    async def connect_to_storage(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.DATABASE_NAME]
        try:
            await self.client.admin.command('ismaster')
            print("Successfully connected to MongoDB")
        except Exception as e:
            print(f"Could not connect to MongoDB: {e}")

    async def close_storage(self):
        if self.client:
            self.client.close()

db_manager = MongoDB()

async def get_db():
    return db_manager.db
