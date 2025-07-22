from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
from pydantic import BaseModel
import base64 # base64 임포트 필요 (Notion 클라이언트 시크릿 인코딩용)
from config import NOTION_CLIENT_ID, NOTION_CLIENT_SECRET, NOTION_REDIRECT_URI

router = APIRouter()

@router.get("/connect-notion")
async def connect_notion():
    notion_auth_url = (
        "https://api.notion.com/v1/oauth/authorize"
        f"?client_id={NOTION_CLIENT_ID}"
        f"&redirect_uri={NOTION_REDIRECT_URI}"
        f"&response_type=code"
        f"&owner=user"
    )
    print("여기 찍히나")
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
    return {"access_token": access_token}

class CodePayload(BaseModel):
    code: str

@router.post("/api/notion/exchange-token") # prefix가 있으므로 실제 경로는 /api/notion/exchange-token 이 됩니다.
async def exchange_notion_token(payload: CodePayload):
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
            response = await client.post(token_url, headers=headers, json=data)
            response.raise_for_status()
            notion_data = response.json()

            access_token = notion_data.get("access_token")
            workspace_id = notion_data.get("workspace_id")
            owner_info = notion_data.get("owner", {})
            user_id = owner_info.get("user", {}).get("id") 
            user_name = owner_info.get("user", {}).get("name", "Unknown User")
            user_avatar = owner_info.get("user", {}).get("avatar_url", "") 
            
            if user_id:
                user_notion_db_map[user_id] = {"access_token": access_token, "workspace_id": workspace_id}
                print("Check", user_notion_db_map[user_id])
            else:
                print("Warning: Notion user ID not found in owner info.")

            search_url = "https://api.notion.com/v1/search"
            print("Skip2")
            search_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            search_payload = {
                "filter": {
                    "property": "object",
                    "value": "database" # 데이터베이스만 필터링
                },
                "page_size": 20 # 한 번에 가져올 최대 결과 수
            }

            search_response = await client.post(search_url, headers=search_headers, json=search_payload)
            search_response.raise_for_status()
            search_results = search_response.json()
            accessible_databases = []
            print("Check3")
            for result in search_results.get("results", []):
                if result.get("object") == "database":
                    # 데이터베이스 제목을 추출합니다. Notion API 응답 구조에 따라 달라질 수 있습니다.
                    # 보통 title 속성은 리치 텍스트 배열입니다.
                    title_property = result.get("title", [])
                    database_title = ""
                    if title_property and isinstance(title_property, list):
                        database_title = "".join([text_obj.get("plain_text", "") for text_obj in title_property])
                    
                    accessible_databases.append({
                        "id": result.get("id"),
                        "title": database_title if database_title else "Untitled Database"
                    })

            print("Notion Token Exchange Response:", notion_data)
            return JSONResponse(content={
                "message": "Notion token exchanged successfully",
                "access_token": access_token, # 클라이언트에게 토큰을 전달 (보안 주의!)
                "workspace_id": workspace_id,
                "user_id": user_id, # Notion user ID
                "user_name": user_name,
                "user_avatar": user_avatar
            })
            # return JSONResponse(content={"message": "Notion token exchanged successfully", "workspace_id": workspace_id})

        except httpx.HTTPStatusError as e:
            print(f"Error exchanging Notion token: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Failed to exchange Notion token: {e.response.text}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            raise HTTPException(status_code=500, detail="Internal server error during token exchange")
        

class SavePayload(BaseModel):
    word: str
    definition: str
    synonyms: str
    access_token: str # 클라이언트로부터 받은 Notion access_token

@router.post("/save-to-notion")
async def save_to_notion(payload: SavePayload):
    # 이 엔드포인트에서는 클라이언트가 전달한 access_token을 사용하여 Notion API를 호출합니다.
    # 실제 앱에서는 access_token을 클라이언트에서 직접 받기보다,
    # 백엔드에 저장된 토큰을 사용자 인증 정보를 기반으로 조회하여 사용하는 것이 안전합니다.
    notion_access_token = payload.access_token

    # Notion API 호출 로직 (예: 데이터베이스에 새 항목 추가)
    # 아래는 Notion API 문서에 따라 적절히 수정해야 합니다.
    # https://developers.notion.com/reference/post-page
    notion_api_url = "https://api.notion.com/v1/pages"
    
    # Notion API 요청 헤더
    headers = {
        "Authorization": f"Bearer {notion_access_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28" # Notion API 버전
    }
    
    # Notion 데이터베이스 ID (사용자가 연동 시 선택한 데이터베이스의 ID)
    # 이 부분은 실제 워크스페이스에서 사용자가 선택한 데이터베이스 ID를 가져오거나,
    # 앱 설정에 미리 정의되어 있어야 합니다.
    # 예를 들어, 사용자별로 저장된 `workspace_id`를 활용하여 해당 워크스페이스 내의
    # 특정 데이터베이스를 찾거나, 앱에서 미리 정해둔 템플릿 데이터베이스를 복사하여 사용할 수 있습니다.
    # 여기서는 임시로 하드코딩된 데이터베이스 ID를 사용합니다.
    # !!! 이 부분을 실제 Notion DB ID로 변경하세요 !!!
    NOTION_DATABASE_ID = "YOUR_NOTION_VOCABULARY_DATABASE_ID" 

    # Notion 페이지 생성 요청 본문 (Notion API 문서 참조)
    # 워드, 정의, 유의어를 저장할 데이터베이스 속성(properties)에 맞게 구성해야 합니다.
    # 예를 들어, "Word" (Title), "Definition" (Rich Text), "Synonyms" (Rich Text) 속성이 있다고 가정합니다.
    page_data = {
        "parent": {"database_id": NOTION_DATABASE_ID},
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
            # 데이터베이스에 있는 다른 속성들도 여기에 추가해야 할 수 있습니다.
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(notion_api_url, headers=headers, json=page_data)
            response.raise_for_status()
            print("Notion page created successfully:", response.json())
            return JSONResponse(content={"message": "Word saved to Notion successfully!"})
        except httpx.HTTPStatusError as e:
            print(f"Error saving to Notion: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Failed to save to Notion: {e.response.text}")
        except Exception as e:
            print(f"An unexpected error occurred during Notion save: {e}")
            raise HTTPException(status_code=500, detail="Internal server error during Notion save")
        

class SavePayload(BaseModel):
    word: str
    definition: str
    synonyms: str
    access_token: str 

@router.post("/save-to-notion")
async def save_to_notion(payload: SavePayload):
    """
    클라이언트로부터 받은 단어 정보를 Notion 데이터베이스에 저장합니다.
    """
    # 클라이언트가 전달한 Notion access_token을 사용합니다.
    # 다시 한번 강조하지만, 실제 서비스에서는 백엔드에서 사용자별로 저장된 토큰을 사용해야 합니다.
    notion_access_token = payload.access_token

    # Notion API의 페이지 생성 엔드포인트 URL
    # Notion API 문서: https://developers.notion.com/reference/post-page
    notion_api_url = "https://api.notion.com/v1/pages"

    # Notion API 요청에 필요한 헤더
    # Bearer 토큰 인증 방식 사용
    headers = {
        "Authorization": f"Bearer {notion_access_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28" # Notion API 버전 (Notion 개발자 문서에서 최신 버전 확인)
    }
    NOTION_DATABASE_ID = "YOUR_NOTION_VOCABULARY_DATABASE_ID" 
    # Notion 페이지 생성 요청 본문 (데이터베이스의 속성(properties)에 맞게 구성)
    # ⭐ 중요: 이 'properties' 구조는 Notion 데이터베이스의 실제 컬럼 이름 및 타입과 일치해야 합니다. ⭐
    # 예를 들어, Notion 데이터베이스에 'Word' (제목), 'Definition' (리치 텍스트), 'Synonyms' (리치 텍스트)
    # 컬럼이 있다고 가정합니다.
    page_data = {
        "parent": {"database_id": NOTION_DATABASE_ID}, # ⭐ 위에서 설정한 DB ID 사용 ⭐
        "properties": {
            "Word": { # Notion 데이터베이스의 'Word'라는 제목(Title) 속성
                "title": [
                    {
                        "text": {
                            "content": payload.word
                        }
                    }
                ]
            },
            "Definition": { # Notion 데이터베이스의 'Definition'이라는 리치 텍스트(Rich Text) 속성
                "rich_text": [
                    {
                        "text": {
                            "content": payload.definition
                        }
                    }
                ]
            },
            "Synonyms": { # Notion 데이터베이스의 'Synonyms'이라는 리치 텍스트(Rich Text) 속성
                "rich_text": [
                    {
                        "text": {
                            "content": payload.synonyms
                        }
                    }
                ]
            }
            # 만약 Notion 데이터베이스에 다른 속성(예: 'Created Date', 'Tags' 등)이 있다면
            # 여기에 추가하여 값을 설정할 수 있습니다.
            # 예: "Tags": {"multi_select": [{"name": "Vocabulary"}]}
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            # Notion API에 POST 요청 보내기
            response = await client.post(notion_api_url, headers=headers, json=page_data)
            response.raise_for_status() # 2xx 외의 응답은 HTTPStatusError 예외 발생

            # Notion API 응답 로깅
            print("Notion page created successfully:", response.json())

            # 성공 응답 반환
            return JSONResponse(content={"message": "Word saved to Notion successfully!"})

        except httpx.HTTPStatusError as e:
            # HTTP 오류 (예: 400 Bad Request, 401 Unauthorized, 404 Not Found 등) 처리
            print(f"Error saving to Notion: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to save to Notion: {e.response.text}"
            )
        except Exception as e:
            # 기타 예상치 못한 오류 처리
            print(f"An unexpected error occurred during Notion save: {e}")
            raise HTTPException(
                status_code=500,
                detail="Internal server error during Notion save"
            )
user_notion_db_map = {}
class SetDatabasePayload(BaseModel):
    database_id: str
    user_id: str
@router.post("/set-vocabulary-db")
async def set_vocabulary_db(payload: SetDatabasePayload):
    """
    사용자가 선택한 Notion 데이터베이스 ID를 백엔드에 저장합니다.
    """
    if payload.user_id:
        if payload.user_id in user_notion_db_map:
            user_notion_db_map[payload.user_id]["vocabulary_db_id"] = payload.database_id
            print(f"User {payload.user_id} selected vocabulary DB: {payload.database_id}")
            return JSONResponse(content={"message": "Vocabulary database set successfully!"})
        else:
            raise HTTPException(status_code=400, detail="User not authenticated or token not found.")
    else:
        raise HTTPException(status_code=400, detail="User ID is required.")