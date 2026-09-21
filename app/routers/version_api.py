from fastapi import APIRouter

from app.version import APP_VERSION

router = APIRouter()


@router.get('/api/version')
def api_version():
    return {'version': APP_VERSION}
