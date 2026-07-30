from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import ConfigDict, BaseModel


class TeamMemberRole:
    """团队成员角色常量"""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


# Team Schemas
class TeamBase(BaseModel):
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None


class TeamCreate(TeamBase):
    """创建团队"""

    pass


class TeamUpdate(BaseModel):
    """更新团队"""

    name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None


# Team Member Schemas
class TeamMemberBase(BaseModel):
    role: str = TeamMemberRole.MEMBER


class TeamMemberAdd(TeamMemberBase):
    """添加团队成员"""

    user_id: UUID


class TeamMemberUpdate(BaseModel):
    """更新成员角色"""

    role: str


class TeamMemberInfo(BaseModel):
    """团队成员信息（包含用户详情）"""

    id: UUID
    user_id: UUID
    username: str
    email: str
    avatar_url: Optional[str] = None
    role: str
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeamOwnerInfo(BaseModel):
    """团队拥有者信息"""

    id: UUID
    username: str
    email: str
    avatar_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class Team(TeamBase):
    """团队响应 Schema"""

    id: UUID
    is_default: bool
    owner: Optional[TeamOwnerInfo] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeamWithMembers(Team):
    """团队响应（包含成员列表）"""

    members: List[TeamMemberInfo] = []


class UserTeamInfo(BaseModel):
    """用户所属团队信息"""

    id: UUID
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str  # 用户在该团队的角色
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)
