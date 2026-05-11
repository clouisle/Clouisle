"""Skill service for Agent-callable sandboxed capabilities."""

from __future__ import annotations

import fnmatch
import re
from typing import Any
from uuid import UUID

from tortoise.expressions import Q

from app.llm.tools.registry import ToolInfo
from app.llm.types import FunctionDefinition, ToolDefinition
from app.models.agent import Agent
from app.models.skill import Skill
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.skill import SkillCreate, SkillOut, SkillUpdate

_SKILL_TOOL_PREFIX = "skill_"
_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_]")


class SkillService:
    """Business logic for Skill resources and Agent function mapping."""

    @staticmethod
    async def check_team_access(
        team_id: UUID, user: User, require_admin: bool = False
    ) -> Team:
        team = await Team.filter(id=team_id).first()
        if not team:
            raise BusinessError(
                code=ResponseCode.TEAM_NOT_FOUND,
                msg_key="team_not_found",
                status_code=404,
            )

        if user.is_superuser:
            return team

        membership = await TeamMember.filter(team=team, user=user).first()
        if not membership:
            raise BusinessError(
                code=ResponseCode.NOT_TEAM_MEMBER,
                msg_key="not_team_member",
                status_code=403,
            )

        if require_admin and membership.role not in ["owner", "admin"]:
            raise BusinessError(
                code=ResponseCode.TEAM_ADMIN_REQUIRED,
                msg_key="team_admin_required",
                status_code=403,
            )

        return team

    @staticmethod
    async def list_available_skills(
        *,
        team_id: UUID,
        user: User,
        include_system: bool = True,
        enabled: bool | None = None,
        search: str | None = None,
        category: str | None = None,
    ) -> list[Skill]:
        await SkillService.check_team_access(team_id, user)

        query = Q(team_id=team_id)
        if include_system:
            query |= Q(team_id=None)

        filters: dict[str, Any] = {}
        if enabled is not None:
            filters["is_enabled"] = enabled
        if category:
            filters["category"] = category

        skills_query = Skill.filter(query, **filters).prefetch_related("created_by")

        if search:
            skills_query = skills_query.filter(
                Q(name__icontains=search)
                | Q(display_name__icontains=search)
                | Q(description__icontains=search)
            )

        return await skills_query.all()

    @staticmethod
    async def get_skill_for_team(
        skill_id: UUID | str,
        team_id: UUID | str | None,
        *,
        enabled_only: bool = False,
    ) -> Skill:
        filters: dict[str, Any] = {"id": skill_id}
        if enabled_only:
            filters["is_enabled"] = True

        skill = await Skill.filter(**filters).first()
        if not skill:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="skill_not_found",
                status_code=404,
            )

        if skill.team_id is not None and str(skill.team_id) != str(team_id):
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="skill_access_denied",
                status_code=403,
            )

        return skill

    @staticmethod
    async def create_skill(payload: SkillCreate, user: User) -> Skill:
        team = None
        if payload.team_id is not None:
            team = await SkillService.check_team_access(
                payload.team_id, user, require_admin=True
            )
        elif not user.is_superuser:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="skill_system_admin_required",
                status_code=403,
            )

        existing = await Skill.filter(
            team_id=payload.team_id, name=payload.name
        ).first()
        if existing:
            raise BusinessError(
                code=ResponseCode.DUPLICATE_NAME,
                msg_key="skill_name_exists",
            )

        return await Skill.create(
            team=team,
            name=payload.name,
            display_name=payload.display_name,
            description=payload.description,
            icon=payload.icon,
            category=payload.category,
            version=payload.version,
            input_schema=payload.input_schema,
            skill_spec=payload.skill_spec,
            config_schema=payload.config_schema,
            default_config=payload.default_config,
            is_enabled=payload.is_enabled,
            created_by=user,
        )

    @staticmethod
    async def update_skill(skill: Skill, payload: SkillUpdate, user: User) -> Skill:
        if skill.team_id is None:
            if not user.is_superuser:
                raise BusinessError(
                    code=ResponseCode.PERMISSION_DENIED,
                    msg_key="skill_system_admin_required",
                    status_code=403,
                )
        else:
            await SkillService.check_team_access(
                skill.team_id, user, require_admin=True
            )

        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(skill, field, value)

        await skill.save()
        return skill

    @staticmethod
    def build_tool_name(skill: Skill) -> str:
        safe_name = _SAFE_NAME_PATTERN.sub("_", skill.name).strip("_").lower()
        short_id = str(skill.id).replace("-", "")[:8]
        return f"{_SKILL_TOOL_PREFIX}{safe_name}_{short_id}"

    @staticmethod
    def get_parameters_schema(skill: Skill) -> dict[str, Any]:
        parameters = skill.input_schema or {"type": "object", "properties": {}}
        if parameters.get("type") != "object":
            return {"type": "object", "properties": {}}
        return parameters

    @staticmethod
    def to_tool_info(
        skill: Skill,
        *,
        config: dict[str, Any] | None = None,
    ) -> ToolInfo:
        async def execute_skill(
            agent: Agent | None = None,
            session_id: str | None = None,
            **arguments: Any,
        ) -> Any:
            from app.services.skill_executor import SkillExecutor

            skill_result = await SkillExecutor.execute(
                skill=skill,
                arguments=arguments,
                config=config,
                tenant_id=str(agent.team_id)
                if agent is not None and agent.team_id
                else None,
                session_id=session_id,
            )
            return skill_result.to_chat_payload()

        return ToolInfo(
            name=SkillService.build_tool_name(skill),
            description=skill.description or skill.display_name,
            parameters_schema=SkillService.get_parameters_schema(skill),
            handler=execute_skill,
        )

    @staticmethod
    def to_tool_definition(skill: Skill) -> ToolDefinition:
        tool_info = SkillService.to_tool_info(skill)
        schema = tool_info.to_openai_schema()["function"]
        return ToolDefinition(
            type="function",
            function=FunctionDefinition(
                name=schema["name"],
                description=schema["description"],
                parameters=schema["parameters"],
            ),
        )

    @staticmethod
    async def get_agent_skill_definitions(agent: Agent) -> list[ToolDefinition]:
        definitions = []
        for skill, _config in await SkillService.get_agent_skills(
            agent, enabled_only=True
        ):
            definitions.append(SkillService.to_tool_definition(skill))
        return definitions

    @staticmethod
    async def get_agent_skills(
        agent: Agent,
        *,
        enabled_only: bool = False,
    ) -> list[tuple[Skill, dict[str, Any]]]:
        skills: list[tuple[Skill, dict[str, Any]]] = []
        for tool_config in agent.tools_config or []:
            if tool_config.get("type") != "skill":
                continue
            skill_id = tool_config.get("skill_id")
            if not skill_id:
                continue
            skill = await SkillService.get_skill_for_team(
                skill_id,
                agent.team_id,
                enabled_only=enabled_only,
            )
            config = dict(skill.default_config or {})
            config.update(tool_config.get("config") or {})
            skills.append((skill, config))
        return skills

    @staticmethod
    async def resolve_agent_skill_tool(
        agent: Agent,
        tool_name: str,
    ) -> tuple[Skill, dict[str, Any]]:
        if not tool_name.startswith(_SKILL_TOOL_PREFIX):
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="skill_not_found",
                status_code=404,
            )

        for skill, config in await SkillService.get_agent_skills(
            agent, enabled_only=True
        ):
            if SkillService.build_tool_name(skill) == tool_name:
                return skill, config

        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="skill_not_configured_for_agent",
            status_code=403,
        )

    @staticmethod
    async def validate_agent_skill_configs(
        agent: Agent | None, tools_config: list[dict[str, Any]], team_id: UUID | str
    ) -> None:
        for tool_config in tools_config:
            if tool_config.get("type") != "skill":
                continue
            skill_id = tool_config.get("skill_id")
            if not skill_id:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_id_required",
                )
            await SkillService.get_skill_for_team(skill_id, team_id, enabled_only=True)

    @staticmethod
    def to_out(skill: Skill) -> SkillOut:
        return SkillOut(
            id=skill.id,
            team_id=skill.team_id,
            name=skill.name,
            display_name=skill.display_name,
            description=skill.description,
            icon=skill.icon,
            category=skill.category,
            version=skill.version,
            source_type=skill.source_type,
            source_uri=skill.source_uri,
            source_ref=skill.source_ref,
            source_subdir=skill.source_subdir,
            package_path=skill.package_path,
            package_hash=skill.package_hash,
            input_schema=skill.input_schema,
            default_config=skill.default_config,
            is_enabled=skill.is_enabled,
            is_system=skill.team_id is None,
            import_warnings=skill.import_warnings or [],
            created_by_id=skill.created_by.id if skill.created_by else None,
            created_by_name=skill.created_by.username if skill.created_by else None,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
        )

    @staticmethod
    def parse_allowed_tools(skill: Skill) -> list[str] | None:
        """从 skill.frontmatter 或 skill_md 解析 allowed-tools"""
        # 优先从 frontmatter 获取
        frontmatter = skill.frontmatter or {}
        allowed = frontmatter.get("allowed-tools")
        if allowed and isinstance(allowed, list):
            return [str(a) for a in allowed]

        # 尝试从 skill_md 解析 (Markdown 格式)
        skill_md = skill.skill_md or ""
        match = re.search(
            r"^allowed-tools:\s*$((?:\s*-\s*.+\n?)+)", skill_md, re.MULTILINE
        )
        if match:
            tools = []
            for line in match.group(1).strip().split("\n"):
                line = line.strip()
                if line.startswith("-"):
                    tools.append(line[1:].strip())
            if tools:
                return tools

        return None

    @staticmethod
    def is_tool_allowed(tool_name: str, allowed_tools: list[str]) -> bool:
        """检查工具是否在白名单内

        支持格式:
        - 精确匹配: "Bash", "Read"
        - 带参数: "Bash(npx impeccable *)"
        - 通配符: "Read*", "*"
        """
        if not allowed_tools:
            return True

        for pattern in allowed_tools:
            # 提取工具名（去掉参数部分）
            tool_pattern = pattern.split("(")[0].strip()

            # 支持 * 通配符
            if "*" in tool_pattern:
                if fnmatch.fnmatch(tool_name, tool_pattern):
                    return True
            elif tool_pattern == tool_name:
                return True

        return False
