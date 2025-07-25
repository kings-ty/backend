# user_routes.py
import uuid
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from database import get_db
import models

router = APIRouter(
    prefix="/api/user",
    tags=["User Management"],
)

@router.get("/get-notion-info/{app_user_id}")
async def get_notion_info(app_user_id: uuid.UUID, db_session: Session = Depends(get_db)):
    """
    앱 사용자 ID를 통해 Notion 연동 정보를 조회하여 클라이언트에 반환합니다.
    """
    user_obj = db_session.query(models.User).filter_by(id=app_user_id).first()

    if not user_obj:
        raise HTTPException(status_code=404, detail="User not found.")

    notion_integration = db_session.query(models.NotionIntegration).filter_by(user_id=app_user_id).first()

    if not notion_integration:
        # Notion 연동 정보가 없어도 사용자 기본 정보는 반환
        return JSONResponse(content={
            "app_user_id": str(user_obj.id),
            "name": user_obj.name,
            "avatar_url": user_obj.avatar_url,
            "notion_connected": False
        })

    return JSONResponse(content={
        "app_user_id": str(user_obj.id),
        "name": user_obj.name,
        "avatar_url": user_obj.avatar_url,
        "notion_connected": True,
        "notion_workspace_id": notion_integration.notion_workspace_id,
        "notion_user_id": notion_integration.notion_user_id,
        "notion_user_name": notion_integration.notion_user_name,
        "notion_user_avatar_url": notion_integration.notion_user_avatar_url,
        "notion_vocabulary_db_id": notion_integration.selected_vocabulary_db_id,
        # access_token은 클라이언트에 직접 노출하지 않습니다.
    })

