# models.py
import uuid
from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey

from database import Base

class User(Base):
    """
    애플리케이션 내부 사용자 모델.
    Notion 연동과 별개로 앱의 사용자 정보를 관리합니다.
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=True) # 사용자 이름 (예: Notion 이름, Google 이름)
    avatar_url = Column(Text, nullable=True) # 사용자 아바타 URL

    notion_integration = relationship("NotionIntegration", back_populates="user", uselist=False)

class NotionIntegration(Base):
    """
    사용자별 Notion 연동 정보를 저장하는 모델.
    """
    __tablename__ = "notion_integrations"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    notion_access_token = Column(Text, nullable=False) # Notion API 호출에 사용될 토큰
    notion_workspace_id = Column(String, nullable=True)
    notion_user_id = Column(String, nullable=True) # Notion 내부의 사용자 ID
    notion_user_name = Column(String, nullable=True)
    notion_user_avatar_url = Column(Text, nullable=True)
    selected_vocabulary_db_id = Column(String, nullable=True) # 사용자가 선택한 단어장 DB ID

    user = relationship("User", back_populates="notion_integration")

