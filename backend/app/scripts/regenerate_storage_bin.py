import asyncio
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402
from app.db.session import async_session  # noqa: E402


def generate_storage_bin() -> str:
    """生成仓位编码，格式: X楼X排X组X层X格"""
    floor = random.randint(1, 2)
    row = random.randint(1, 6)
    group = random.randint(1, 6)
    level = random.randint(1, 4)
    cell = random.randint(1, 9)
    return f"{floor}楼{row}排{group}组{level}层{cell}格"


async def regenerate_storage_bin():
    """重新生成所有物料库存记录的 storage_bin"""
    async with async_session() as session:
        result = await session.execute(text("SELECT id FROM material_inventory"))
        rows = result.fetchall()

        if not rows:
            print("表中没有数据")
            return

        count = 0
        for row in rows:
            storage_bin = generate_storage_bin()
            await session.execute(
                text("UPDATE material_inventory SET storage_bin = :bin WHERE id = :id"),
                {"bin": storage_bin, "id": row[0]},
            )
            count += 1

        await session.commit()
        print(f"成功更新 {count} 条记录的 storage_bin")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(regenerate_storage_bin())
