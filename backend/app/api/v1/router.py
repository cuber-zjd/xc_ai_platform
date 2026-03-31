from fastapi import APIRouter
from app.api.v1.endpoints import login, users, contracts, agents, roles, depts

api_router = APIRouter()
api_router.include_router(login.router, tags=["login"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])
api_router.include_router(depts.router, prefix="/depts", tags=["depts"])
