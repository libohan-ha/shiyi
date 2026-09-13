from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class SPAFiles(StaticFiles):
    """Serve React routes while keeping missing API routes and assets as real 404s."""

    async def get_response(self, path, scope):
        path = path.replace("\\", "/")
        if path == "api" or path.startswith("api/") or any(part.startswith(".") for part in PurePosixPath(path).parts):
            raise HTTPException(404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or PurePosixPath(path).suffix:
                raise
            return await super().get_response("index.html", scope)
