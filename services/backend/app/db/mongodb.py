import motor.motor_asyncio
from app.core.config import settings


class MongoDB:
    client: motor.motor_asyncio.AsyncIOMotorClient | None = None
    db = None

    async def connect_to_storage(self) -> None:
        self.client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_url)
        self.db = self.client[settings.database_name]
        try:
            await self.client.admin.command("ismaster")
            print("Successfully connected to MongoDB")
        except Exception as exc:
            print(f"Could not connect to MongoDB: {exc}")

    async def close_storage(self) -> None:
        if self.client:
            self.client.close()


db_manager = MongoDB()


async def get_db():
    return db_manager.db
