# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import declarative_base 
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD  
# SQLAlchemy 데이터베이스 URL 생성
# f-string을 사용하여 변수를 URL에 삽입합니다.
SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# SQLAlchemy 엔진 생성
# pool_pre_ping=True는 데이터베이스 연결이 유효한지 주기적으로 확인하여
# 유휴 연결이 끊어지는 문제를 방지하는 데 도움이 됩니다.
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)

# 세션 로컬 클래스 생성
# autocommit=False: 트랜잭션이 자동으로 커밋되지 않음 (수동 커밋 필요)
# autoflush=False: 변경사항이 자동으로 플러시되지 않음 (수동 플러시 또는 커밋 시 플러시)
# bind=engine: 생성된 엔진과 연결
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# SQLAlchemy ORM의 기본 선언적 베이스 클래스 생성
# 이 클래스를 상속받아 데이터베이스 테이블과 매핑되는 모델을 정의합니다.
Base = declarative_base()

# 데이터베이스 세션을 제공하는 의존성 함수
# FastAPI의 Depends와 함께 사용하여 요청마다 새로운 DB 세션을 제공합니다.
from fastapi import HTTPException
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        # 오류가 발생했음을 명확히 알리고, FastAPI가 응답을 생성할 수 있도록
        # HTTPException을 다시 발생시킵니다.
        print(f"Database session error: {e}") # 디버깅을 위한 로그
        raise HTTPException(status_code=500, detail="Database operation failed")
    finally:
        db.close()