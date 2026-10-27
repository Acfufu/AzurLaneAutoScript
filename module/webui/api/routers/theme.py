from fastapi import APIRouter, HTTPException

from module.webui.api.models import ThemeRequest, ThemeResponse
from module.webui.setting import State

router = APIRouter(tags=["theme"])

# Same list as webapp/src/api/themes.ts — the blocks that exist in
# styles/theme.css. Any string used to persist, and came back from
# deploy.yaml with no stylesheet behind it (audit L1).
VALID_THEMES = {"default", "dark", "minty", "yeti", "sketchy"}


@router.post("/theme", response_model=ThemeResponse)
def set_theme_api(request: ThemeRequest):
    if request.theme not in VALID_THEMES:
        raise HTTPException(status_code=400, detail=f"Unknown theme: {request.theme}")
    State.theme = request.theme
    State.deploy_config.Theme = request.theme
    return {"theme": request.theme}
