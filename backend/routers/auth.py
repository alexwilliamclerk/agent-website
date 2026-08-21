"""
用户模块 - 注册、登录、JWT鉴权
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models.user import User

router = APIRouter()

# 密码加密
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ===== 请求/响应模型 =====

class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("用户名至少需要 2 个有效字符")
        if any(character.isspace() for character in normalized):
            raise ValueError("用户名不能包含空格")
        return normalized


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("用户名不能为空")
        return normalized


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    username: str
    latest_assessment_id: str | None = None
    active_assessment_id: str | None = None
    created_at: datetime


class ActiveAssessmentRequest(BaseModel):
    assessment_id: str


# ===== 工具函数 =====

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """获取当前登录用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


# ===== 接口 =====

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    # 检查用户名是否已存在
    if db.query(User).filter(User.username == request.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 创建用户
    user = User(
        username=request.username,
        password_hash=get_password_hash(request.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}



class UpdatePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取当前用户信息"""
    from models.assessment import Assessment

    learner = db.query(User).filter(User.id == current_user.id).first()
    if not learner:
        raise HTTPException(status_code=404, detail="用户不存在")
    completed = db.query(Assessment).filter(
        Assessment.user_id == learner.id,
        Assessment.overall_mastery.isnot(None),
    )
    latest = (
        completed
        .order_by(Assessment.created_at.desc())
        .first()
    )
    active = None
    if learner.active_assessment_id:
        active = completed.filter(Assessment.id == learner.active_assessment_id).first()
    active_id = active.id if active else (latest.id if latest else None)

    return {
        "id": learner.id,
        "username": learner.username,
        "latest_assessment_id": latest.id if latest else None,
        "active_assessment_id": active_id,
        "created_at": learner.created_at,
    }


@router.put("/active-assessment", response_model=UserResponse)
def set_active_assessment(
    request: ActiveAssessmentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist the diagnosis selected from history for all result pages."""
    from models.assessment import Assessment

    selected = db.query(Assessment).filter(
        Assessment.id == request.assessment_id,
        Assessment.user_id == current_user.id,
        Assessment.overall_mastery.isnot(None),
    ).first()
    if not selected:
        raise HTTPException(status_code=404, detail="诊断结果不存在或尚未完成")

    learner = db.query(User).filter(User.id == current_user.id).first()
    if not learner:
        raise HTTPException(status_code=404, detail="用户不存在")
    learner.active_assessment_id = selected.id
    db.commit()
    db.refresh(learner)
    return get_me(current_user=learner, db=db)



@router.put("/password")
def update_password(
    request: UpdatePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改密码"""
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")

    current_user.password_hash = get_password_hash(request.new_password)
    db.commit()

    return {"message": "密码修改成功"}
