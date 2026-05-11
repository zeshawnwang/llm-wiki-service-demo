from fastapi import APIRouter

from .documents import router as documents_router
from .wiki import router as wiki_router
from .ai import router as ai_router
from .search import router as search_router
from .pipeline import router as pipeline_router

api_router = APIRouter(prefix="/api")

api_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_router.include_router(wiki_router, prefix="/wiki", tags=["wiki"])
api_router.include_router(ai_router, prefix="/ai", tags=["ai"])
api_router.include_router(search_router, prefix="/search", tags=["search"])
api_router.include_router(pipeline_router, prefix="/pipeline", tags=["pipeline"])