from fastapi import APIRouter
from app.api.v1.endpoints.system import login, users, roles, depts, models
from app.api.v1.endpoints.agent.contract import contracts
from app.api.v1.endpoints.agent import agents
from app.api.v1.endpoints.agent.external import data_extract, image_extract
from app.api.v1.endpoints.agent import fr_report

api_router = APIRouter()
api_router.include_router(login.router, tags=["login"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])
api_router.include_router(depts.router, prefix="/depts", tags=["depts"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(data_extract.router, prefix="/external", tags=["external_api"])
api_router.include_router(image_extract.router, prefix="/external", tags=["external_api"])
api_router.include_router(fr_report.router, prefix="/fr/ai-reports", tags=["fr_ai_reports"])
