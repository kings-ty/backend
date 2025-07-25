from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
from pydantic import BaseModel
import base64
from config import NOTION_CLIENT_ID, NOTION_CLIENT_SECRET, NOTION_REDIRECT_URI
import uuid
from sqlalchemy.orm import Session
from database import get_db
import models
from typing import Optional 

router = APIRouter(
    prefix="/api/notion",
    tags=["Notion Integration"],
)

@router.get("/connect-notion")
async def connect_notion(
    app_user_id: Optional[uuid.UUID] = Query(None), # app_user_id를 선택적 쿼리 파라미터로 추가
    db_session: Session = Depends(get_db) # DB 세션 추가
):
    """
    Notion OAuth 인증 흐름을 시작하거나,
    이미 연결된 사용자의 경우 바로 대시보드로 리다이렉트합니다.
    """
    print(f"connect_notion called with app_user_id: {app_user_id}")

    if app_user_id:
        # 1. app_user_id가 제공되면 DB에서 Notion 연동 정보 조회
        notion_integration = db_session.query(models.NotionIntegration).filter_by(user_id=app_user_id).first()

        if notion_integration and notion_integration.notion_access_token and notion_integration.selected_vocabulary_db_id:
            # 2. Notion access_token이 유효한지 Notion API를 통해 확인 (옵션)
            # 이 단계는 네트워크 요청이 발생하므로, 필요에 따라 생략하거나 더 가벼운 검증으로 대체할 수 있습니다.
            notion_api_test_url = "https://api.notion.com/v1/users/me" # 간단한 API 호출로 토큰 유효성 검사
            headers = {
                "Authorization": f"Bearer {notion_integration.notion_access_token}",
                "Notion-Version": "2022-06-28"
            }
            async with httpx.AsyncClient() as client:
                try:
                    test_response = await client.get(notion_api_test_url, headers=headers)
                    test_response.raise_for_status() # 2xx 응답이 아니면 예외 발생
                    print(f"Notion token for user {app_user_id} is valid.")
                    return RedirectResponse(f"http://localhost:3000/session-restore?app_user_id={app_user_id}")
                except httpx.HTTPStatusError as e:
                    print(f"Notion token for user {app_user_id} is invalid or expired: {e.response.status_code} - {e.response.text}")
                    # 토큰이 유효하지 않으면 OAuth 흐름으로 진행
                except Exception as e:
                    print(f"Error checking Notion token validity for user {app_user_id}: {e}")
                    # 오류 발생 시에도 OAuth 흐름으로 진행

    # app_user_id가 없거나, Notion 연동 정보가 없거나, 토큰이 유효하지 않은 경우
    # Notion OAuth 인증 URL로 리다이렉트
    notion_auth_url = (
        "https://api.notion.com/v1/oauth/authorize"
        f"?client_id={NOTION_CLIENT_ID}"
        f"&redirect_uri={NOTION_REDIRECT_URI}"
        f"&response_type=code"
        f"&owner=user"
    )
    print("Proceeding to Notion OAuth flow.")
    return RedirectResponse(notion_auth_url)

@router.get("/auth/notion/callback")
async def notion_callback(request: Request):
    code = request.query_params.get("code")
    token_url = "https://api.notion.com/v1/oauth/token"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": NOTION_REDIRECT_URI,
            },
            auth=(NOTION_CLIENT_ID, NOTION_CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    token_data = response.json()
    access_token = token_data.get("access_token")
    # TODO: PostgreSQL에 access_token 저장
    # 이 부분은 /exchange-token 엔드포인트에서 더 상세하게 처리되므로,
    # 여기서는 프론트엔드로 code를 전달하여 /exchange-token을 호출하도록 유도하는 것이 좋습니다.
    # 예: return RedirectResponse(f"http://localhost:3000/auth-success?code={code}")
    # 현재는 간단히 access_token을 반환하지만, 실제 앱에서는 프론트엔드 리다이렉션이 필요합니다.
    print(f"Notion access token received: {access_token}")
    return {"access_token": access_token}

class CodePayload(BaseModel):
    code: str

@router.post("/exchange-token")
async def exchange_notion_token(payload: CodePayload, db_session: Session = Depends(get_db)):
    """
    Notion OAuth 코드를 Notion access_token으로 교환하고,
    접근 가능한 데이터베이스 목록을 조회하며, 사용자 Notion 정보를 DB에 저장/업데이트합니다.
    """
    code = payload.code

    token_url = "https://api.notion.com/v1/oauth/token"

    auth_header = base64.b64encode(f'{NOTION_CLIENT_ID}:{NOTION_CLIENT_SECRET}'.encode()).decode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_header}"
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": NOTION_REDIRECT_URI
    }

    async with httpx.AsyncClient() as client:
        try:
            # 1. Notion OAuth 토큰 교환
            response = await client.post(token_url, headers=headers, json=data)
            response.raise_for_status()
            notion_data = response.json()

            access_token = notion_data.get("access_token")
            workspace_id = notion_data.get("workspace_id")
            owner_info = notion_data.get("owner", {})
            notion_user_id = owner_info.get("user", {}).get("id")
            notion_user_name = owner_info.get("user", {}).get("name", "Unknown User")
            notion_user_avatar_url = owner_info.get("user", {}).get("avatar_url", "")

            print("Notion Token Exchange Response:", notion_data)

            # 2. 앱 내부 사용자 생성 또는 조회 및 Notion 연동 정보 저장/업데이트
            # Notion user ID를 기준으로 사용자 조회
            notion_integration_exists = db_session.query(models.NotionIntegration).filter(
                models.NotionIntegration.notion_user_id == notion_user_id
            ).first()

            user_obj = None
            if notion_integration_exists:
                user_obj = db_session.query(models.User).filter_by(id=notion_integration_exists.user_id).first()
                # 기존 NotionIntegration 업데이트
                notion_integration_exists.notion_access_token = access_token
                notion_integration_exists.notion_workspace_id = workspace_id
                notion_integration_exists.notion_user_name = notion_user_name
                notion_integration_exists.notion_user_avatar_url = notion_user_avatar_url
                db_session.add(notion_integration_exists)
                notion_integration = notion_integration_exists
            else:
                # 새로운 사용자 생성
                user_obj = models.User(name=notion_user_name, avatar_url=notion_user_avatar_url)
                db_session.add(user_obj)
                db_session.flush() # ID를 얻기 위해 flush

                notion_integration = models.NotionIntegration(
                    user_id=user_obj.id,
                    notion_access_token=access_token,
                    notion_workspace_id=workspace_id,
                    notion_user_id=notion_user_id,
                    notion_user_name=notion_user_name,
                    notion_user_avatar_url=notion_user_avatar_url
                )
                db_session.add(notion_integration)
            
            db_session.commit()
            db_session.refresh(user_obj)

            # 3. 획득한 access_token으로 Notion 워크스페이스 내 데이터베이스 검색
            search_url = "https://api.notion.com/v1/search"
            search_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            search_payload = {
                "filter": {
                    "property": "object",
                    "value": "database"
                },
                "page_size": 100
            }

            search_response = await client.post(search_url, headers=search_headers, json=search_payload)
            search_response.raise_for_status()
            search_results = search_response.json()

            accessible_databases = []
            for result in search_results.get("results", []):
                if result.get("object") == "database":
                    title_property = result.get("title", [])
                    database_title = ""
                    if title_property and isinstance(title_property, list):
                        database_title = "".join([text_obj.get("plain_text", "") for text_obj in title_property])
                    
                    accessible_databases.append({
                        "id": result.get("id"),
                        "title": database_title if database_title else "Untitled Database"
                    })

            return JSONResponse(content={
                "message": "Notion token exchanged successfully and databases fetched",
                "app_user_id": str(user_obj.id),
                "user_name": user_obj.name,
                "user_avatar": user_obj.avatar_url,
                "accessible_databases": accessible_databases
            })

        except httpx.HTTPStatusError as e:
            db_session.rollback()
            print(f"Error during Notion token exchange or database search: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to exchange Notion token or search databases: {e.response.text}"
            )
        except Exception as e:
            db_session.rollback()
            print(f"An unexpected error occurred: {e}")
            raise HTTPException(status_code=500, detail="Internal server error during Notion process")

class SetDatabasePayload(BaseModel):
    database_id: str
    app_user_id: uuid.UUID

class SavePayload(BaseModel):
    word: str
    definition: str
    synonyms: str
    app_user_id: uuid.UUID 

@router.post("/set-vocabulary-db")
async def set_vocabulary_db(payload: SetDatabasePayload, db_session: Session = Depends(get_db)):
    """
    사용자가 선택한 Notion 데이터베이스 ID를 백엔드 DB에 저장합니다.
    """
    notion_integration = db_session.query(models.NotionIntegration).filter_by(user_id=payload.app_user_id).first()

    if not notion_integration:
        raise HTTPException(status_code=404, detail="Notion integration not found for this user.")

    notion_integration.selected_vocabulary_db_id = payload.database_id
    db_session.commit()
    db_session.refresh(notion_integration)

    print(f"User {payload.app_user_id} selected vocabulary DB: {payload.database_id}")
    return JSONResponse(content={"message": "Vocabulary database set successfully!"})


@router.post("/createNotionDB")
async def create_notion_db(request: Request, db_session: Session = Depends(get_db)):
    """
    Creates a new Notion database for the authenticated user and returns its ID and title.
    Requires an active Notion access token for the user.
    """
    
    try:
        print("Creating Notion database...")
        request_data = await request.json()
        print(f"Request data for Notion DB creation: {request_data}")
        app_user_id = request_data.get("app_user_id")
        if not app_user_id:
            raise HTTPException(status_code=400, detail="app_user_id is required to create a Notion database.")
        print(f"Creating Notion database for app_user_id: {app_user_id}")
        
        # Retrieve the Notion access token for the given app_user_id
        notion_integration = db_session.query(models.NotionIntegration).filter_by(user_id=app_user_id).first()

        if not notion_integration or not notion_integration.notion_access_token:
            raise HTTPException(status_code=401, detail="Notion access token not found for this user. Please connect Notion.")

        access_token = notion_integration.notion_access_token

        notion_api_url = "https://api.notion.com/v1/databases"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        async with httpx.AsyncClient() as client:
            # 1. Search for an existing page to use as a parent
            search_pages_payload = {
                "filter": {
                    "property": "object",
                    "value": "page"
                },
                "page_size": 1 # Just need one to act as a parent
            }
            
            print(f"Attempting Notion search for pages with headers: {headers} and payload: {search_pages_payload}")
            search_pages_response = await client.post("https://api.notion.com/v1/search", headers=headers, json=search_pages_payload)
            
            print(f"Notion search for pages response status: {search_pages_response.status_code}")
            print(f"Notion search for pages response headers: {search_pages_response.headers}")
            print(f"Notion search for pages response text: {search_pages_response.text}")
            
            search_pages_response.raise_for_status()
            search_pages_results = search_pages_response.json()

            print(f"Notion search results JSON: {search_pages_results}")
            
            parent_page_id = None
            if search_pages_results.get("results"):
                for result in search_pages_results["results"]:
                    if result.get("object") == "page":
                        parent_page_id = result["id"]
                        break # Found a parent page

            if not parent_page_id:
                raise HTTPException(
                    status_code=400,
                    detail="No accessible Notion pages found to create a new database under. Please ensure your Notion integration has access to at least one page."
                )

            # 2. Create the new Notion database as a child of the found parent page
            new_db_data = {
                "parent": {"page_id": parent_page_id},
                "title": [
                    {
                        "type": "text",
                        "text": {
                            "content": "My New Vocabulary List" # Default name for the new database
                        }
                    }
                ],
                "properties": {
                    "Word": {
                        "title": {}
                    },
                    "Definition": {
                        "rich_text": {}
                    },
                    "Synonyms": {
                        "rich_text": {}
                    }
                }
            }

            create_db_response = await client.post(notion_api_url, headers=headers, json=new_db_data)
            create_db_response.raise_for_status()
            new_notion_db = create_db_response.json()

            db_id = new_notion_db.get("id")
            db_title_raw = new_notion_db.get("title", [])
            db_title = "".join([text_obj.get("plain_text", "") for text_obj in db_title_raw]) if db_title_raw else "Untitled Database"

            print(f"New Notion database created: ID={db_id}, Title={db_title}")

            return JSONResponse(content={
                "message": "New Notion vocabulary database created successfully!",
                "notion_db": {
                    "id": db_id,
                    "title": db_title
                }
            })

    except httpx.HTTPStatusError as e:
        print(f"Error creating Notion database: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Failed to create Notion database: {e.response.text}"
        )
    except Exception as e:
        print(f"An unexpected error occurred during Notion DB creation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during Notion DB creation")


@router.post("/save-to-notion")
async def save_to_notion(payload: SavePayload, db_session: Session = Depends(get_db)):
    """
    클라이언트로부터 받은 단어 정보를 Notion 데이터베이스에 저장합니다.
    앱 내부 사용자 ID를 통해 DB에서 Notion access_token과 database_id를 조회합니다.
    """
    notion_integration = db_session.query(models.NotionIntegration).filter_by(user_id=payload.app_user_id).first()

    if not notion_integration:
        raise HTTPException(status_code=401, detail="Notion integration not found for this user. Please connect Notion.")

    notion_access_token = notion_integration.notion_access_token
    notion_vocabulary_db_id = notion_integration.selected_vocabulary_db_id
    print(f"Notion access token: {notion_access_token}, Vocabulary DB ID: {notion_vocabulary_db_id}")
    if not notion_access_token or not notion_vocabulary_db_id:
        raise HTTPException(status_code=400, detail="Notion access token or vocabulary database ID not set for this user. Please complete Notion setup.")

    notion_api_url = "https://api.notion.com/v1/pages"

    headers = {
        "Authorization": f"Bearer {notion_access_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    page_data = {
        "parent": {"database_id": notion_vocabulary_db_id},
        "properties": {
            "Word": {
                "title": [
                    {
                        "text": {
                            "content": payload.word
                        }
                    }
                ]
            },
            "Definition": {
                "rich_text": [
                    {
                        "text": {
                            "content": payload.definition
                        }
                    }
                ]
            },
            "Synonyms": {
                "rich_text": [
                    {
                        "text": {
                            "content": payload.synonyms
                        }
                    }
                ]
            }
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            print (f"Saving to Notion with data: {page_data}")
            response = await client.post(notion_api_url, headers=headers, json=page_data)
            response.raise_for_status()

            print("Notion page created successfully:", response.json())

            return JSONResponse(content={"message": "Word saved to Notion successfully!"})

        except httpx.HTTPStatusError as e:
            print(f"Error saving to Notion: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to save to Notion: {e.response.text}"
            )
        except Exception as e:
            print(f"An unexpected error occurred during Notion save: {e}")
            raise HTTPException(
                status_code=500,
                detail="Internal server error during Notion save"
            )
        

# 새 엔드포인트 추가: 사용자 Notion 연동 상태 및 데이터베이스 ID 조회
@router.get("/user-notion-status/{app_user_id}")
async def get_user_notion_status(app_user_id: uuid.UUID, db_session: Session = Depends(get_db)):
    """
    주어진 app_user_id에 대한 Notion 연동 상태 및 선택된 데이터베이스 ID를 반환합니다.
    """
    notion_integration = db_session.query(models.NotionIntegration).filter_by(user_id=app_user_id).first()
    user_obj = db_session.query(models.User).filter_by(id=app_user_id).first()

    if not user_obj:
        raise HTTPException(status_code=404, detail="User not found.")

    if not notion_integration:
        return JSONResponse(content={
            "app_user_id": str(app_user_id),
            "user_name": user_obj.name,
            "user_avatar": user_obj.avatar_url,
            "notion_connected": False,
            "notion_vocabulary_db_id": None
        })
    
    return JSONResponse(content={
        "app_user_id": str(app_user_id),
        "user_name": user_obj.name,
        "user_avatar": user_obj.avatar_url,
        "notion_connected": True,
        "notion_workspace_id": notion_integration.notion_workspace_id,
        "notion_user_id": notion_integration.notion_user_id,
        "notion_user_name": notion_integration.notion_user_name,
        "notion_user_avatar_url": notion_integration.notion_user_avatar_url,
        "notion_vocabulary_db_id": notion_integration.selected_vocabulary_db_id
    })
