from sqlmodel import SQLModel
from app.db.session import engine
from app.core.logger import logger

# 导入所有模型确保注册到 SQLModel.metadata
from app.models.system import sys_user, sys_dept, sys_company, sys_post, sys_model
from app.models.contract import contract_model

async def init_db():
    """
    创建数据库表 + 初始化种子数据。
    应用启动时调用。
    """
    logger.info("正在创建数据库表...")
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all) # 危险：仅开发环境使用
        await conn.run_sync(SQLModel.metadata.create_all)
    
    # 初始化种子数据
    await _seed_contract_rules()
    await _seed_model_configs()

    logger.info("数据库表创建完成。")


async def _seed_contract_rules():
    """初始化合同审查规则种子数据"""
    from sqlmodel import select
    from app.models.contract.contract_model import ContractRule, RiskLevelEnum
    from app.db.session import async_session
    
    async with async_session() as session:
        statement = select(ContractRule)
        result = await session.exec(statement)
        if not result.first():
            logger.info("正在初始化合同审查规则...")
            rules = [
                ContractRule(
                    rule_name="违约金条款检查", 
                    description="检查合同是否包含违约金相关说明",
                    category="GLOBAL",
                    severity=RiskLevelEnum.WARNING,
                    rule_definition="Check for default penalty"
                ),
                ContractRule(
                    rule_name="付款账期限制", 
                    description="付款账期不得超过60天",
                    category="Purchase",
                    severity=RiskLevelEnum.CRITICAL,
                    rule_definition="Payment terms <= 60 days"
                )
            ]
            session.add_all(rules)
            await session.commit()


async def _seed_model_configs():
    """
    初始化 AI 模型配置种子数据

    如果 sys_model 表为空，则插入默认的模型配置。
    这里使用火山引擎（豆包）的端点作为示例，实际使用时需要修改为真实配置。
    """
    from sqlmodel import select
    from app.models.system.sys_model import SysModel
    from app.db.session import async_session

    async with async_session() as session:
        statement = select(SysModel)
        result = await session.exec(statement)
        if not result.first():
            logger.info("正在初始化 AI 模型配置...")
            models = [
                SysModel(
                    model_name="doubao-pro",
                    model_code="ep-20250716092812-ng6hc",
                    provider="volcengine",
                    api_key="8fd7cc00-8433-4843-8231-6d96853861bc",
                    base_url="https://ark.cn-beijing.volces.com/api/v3",
                    model_level=2,
                    model_type="chat",
                    capability="general",
                    max_tokens=4096,
                    default_temperature=0.0,
                    priority=10,
                    is_enabled=True,
                    comment="火山引擎豆包大模型 Pro 版",
                ),
            ]
            session.add_all(models)
            await session.commit()
            logger.info(f"已初始化 {len(models)} 个模型配置")
