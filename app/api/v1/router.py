"""v1 API router. Phase routers are mounted here as they land."""

from fastapi import APIRouter

from app.api.v1 import auth, bakes, health, media, profiles, proofing, recipes, starters

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(profiles.router)
api_router.include_router(starters.router)
api_router.include_router(proofing.router)
api_router.include_router(recipes.router)
api_router.include_router(bakes.router)
api_router.include_router(media.router)
