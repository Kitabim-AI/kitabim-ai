import os
import json
import asyncio
import sys
import argparse
from sqlalchemy.dialects.postgresql import insert

# Ensure app imports resolve correctly
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../packages/backend-core")
    ),
)

from app.db import session as db_session
from app.db.models import Quran
from app.utils import circuit_breaker


async def import_quran(data_dir: str):
    if not os.path.exists(data_dir):
        print(f"Error: Directory {data_dir} does not exist.")
        return

    print(f"Reading files from: {data_dir}")

    json_files = []
    for filename in os.listdir(data_dir):
        if filename.endswith(".json") and filename[:-5].isdigit():
            json_files.append(filename)

    json_files.sort(key=lambda x: int(x[:-5]))

    if not json_files:
        print("No numeric JSON files found in directory.")
        return

    all_ayahs = []
    for filename in json_files:
        filepath = os.path.join(data_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                ayahs = json.load(f)
                all_ayahs.extend(ayahs)
            except Exception as e:
                print(f"Failed to parse {filename}: {e}")

    print(f"Loaded {len(all_ayahs)} total ayahs to import.")

    print("Initializing database connection...", flush=True)
    await db_session.init_db()

    batch_size = 500
    try:
        async with db_session.async_session_factory() as session:
            for i in range(0, len(all_ayahs), batch_size):
                batch = all_ayahs[i : i + batch_size]

                insert_data = [
                    {
                        "surah": entry["surah"],
                        "surah_name_en": entry["surah_name_en"],
                        "surah_name_ar": entry["surah_name_ar"],
                        "surah_name_ug": entry["surah_name_ug"],
                        "ayah": entry["ayah"],
                        "text_ar": entry["text_ar"],
                        "text_en": entry["text_en"],
                        "text_ug": entry["text_ug"],
                    }
                    for entry in batch
                ]

                stmt = insert(Quran).values(insert_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["surah", "ayah"],
                    set_={
                        "surah_name_en": stmt.excluded.surah_name_en,
                        "surah_name_ar": stmt.excluded.surah_name_ar,
                        "surah_name_ug": stmt.excluded.surah_name_ug,
                        "text_ar": stmt.excluded.text_ar,
                        "text_en": stmt.excluded.text_en,
                        "text_ug": stmt.excluded.text_ug,
                    },
                )

                await session.execute(stmt)
                await session.commit()
                print(
                    f"Processed batch {i // batch_size + 1}/{(len(all_ayahs) + batch_size - 1) // batch_size}",
                    flush=True,
                )

        print("Quran import completed successfully!", flush=True)
    except Exception as e:
        print(f"Error during import: {e}", flush=True)
    finally:
        await db_session.close_db()
        if (
            hasattr(circuit_breaker, "_redis_client")
            and circuit_breaker._redis_client is not None
        ):
            await circuit_breaker._redis_client.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Quran JSON data to DB")
    parser.add_argument(
        "--dir",
        type=str,
        default="/Users/Omarjan/Projects/uyghur-language/uyghur-language.github.io/quran/data/surah",
        help="Path to the directory containing Quran JSON files",
    )
    args = parser.parse_args()
    asyncio.run(import_quran(args.dir))
