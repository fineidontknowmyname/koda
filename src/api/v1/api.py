from fastapi import APIRouter
from api.v1.endpoints import plans, users, vision

api_router = APIRouter()

api_router.include_router(plans.router, prefix="/plans", tags=["Plans"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(vision.router, prefix="/vision", tags=["Vision"])
