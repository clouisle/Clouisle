from tortoise import fields, models


class Permission(models.Model):
    id = fields.UUIDField(pk=True)
    scope = fields.CharField(
        max_length=50, description="Permission scope (e.g., user, kb)"
    )
    code = fields.CharField(
        max_length=100,
        unique=True,
        description="Unique permission code (e.g., user:create)",
    )
    description = fields.CharField(max_length=255, null=True)
    is_system = fields.BooleanField(
        default=True,
        description="System permission (defined in code, cannot be deleted)",
    )

    class Meta:
        table = "permissions"

    def __str__(self):
        return self.code


class Role(models.Model):
    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=50, unique=True)
    description = fields.CharField(max_length=255, null=True)
    is_system_role = fields.BooleanField(
        default=False, description="If True, cannot be deleted/modified"
    )
    permissions = fields.ManyToManyField(
        "models.Permission", related_name="roles", through="role_permissions"
    )

    class Meta:
        table = "roles"

    def __str__(self):
        return self.name


class Team(models.Model):
    """团队模型 - 用于资源隔离和协作"""

    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=100, unique=True)
    description = fields.CharField(max_length=500, null=True)
    avatar_url = fields.CharField(max_length=512, null=True)
    is_default = fields.BooleanField(
        default=False, description="Default team for new users"
    )

    # Statistics (累计统计，不会因删除而减少)
    total_conversations = fields.IntField(
        default=0, description="Total conversations created"
    )
    total_messages = fields.IntField(default=0, description="Total messages created")
    total_tokens = fields.BigIntField(
        default=0, description="Total tokens consumed (累计)"
    )

    # Soft delete support
    is_deleted = fields.BooleanField(default=False, description="Soft delete flag")
    deleted_at = fields.DatetimeField(
        null=True, description="When the team was deleted"
    )
    deleted_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="deleted_teams",
        null=True,
        on_delete=fields.SET_NULL,
        description="User who deleted the team",
    )

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # Team owner (creator)
    owner: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User", related_name="owned_teams", null=True, on_delete=fields.SET_NULL
    )

    class Meta:
        table = "teams"

    def __str__(self):
        return self.name


class TeamMember(models.Model):
    """团队成员关联表 - 包含成员角色"""

    id = fields.UUIDField(pk=True)
    team: fields.ForeignKeyRelation[Team] = fields.ForeignKeyField(
        "models.Team", related_name="memberships", on_delete=fields.CASCADE
    )
    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User", related_name="team_memberships", on_delete=fields.CASCADE
    )
    role = fields.CharField(
        max_length=20, default="member", description="owner, admin, member, viewer"
    )
    joined_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "team_members"
        unique_together = (("team", "user"),)

    def __str__(self):
        return f"{self.user} in {self.team} ({self.role})"


class ScopedRoleAssignment(models.Model):
    """Role assignment scoped to a team or future resource scope."""

    id = fields.UUIDField(pk=True)
    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User", related_name="scoped_role_assignments", on_delete=fields.CASCADE
    )
    role: fields.ForeignKeyRelation[Role] = fields.ForeignKeyField(
        "models.Role", related_name="scoped_assignments", on_delete=fields.CASCADE
    )
    scope_type = fields.CharField(max_length=20, description="Scope type, e.g. team")
    scope_id = fields.UUIDField(description="Scoped resource ID")
    source = fields.CharField(
        max_length=20,
        default="manual",
        description="Assignment source: manual, default, migration, system",
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "scoped_role_assignments"
        unique_together = (("user", "role", "scope_type", "scope_id"),)

    def __str__(self):
        return f"{self.user} -> {self.role} ({self.scope_type}:{self.scope_id})"


class User(models.Model):
    id = fields.UUIDField(pk=True)
    username = fields.CharField(max_length=50, unique=True)
    email = fields.CharField(max_length=255, unique=True)
    hashed_password = fields.CharField(max_length=255)
    is_active = fields.BooleanField(default=True)
    approval_status = fields.CharField(
        max_length=20,
        default="approved",
        description="Approval status: approved, pending",
    )
    is_superuser = fields.BooleanField(default=False)
    email_verified = fields.BooleanField(
        default=False, description="Email verification status"
    )
    locale = fields.CharField(
        max_length=10,
        default="en",
        description="User preferred locale (e.g., en, zh)",
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    last_login = fields.DatetimeField(null=True)
    failed_login_attempts = fields.IntField(
        default=0, description="Failed login attempts count"
    )
    locked_until = fields.DatetimeField(
        null=True, description="Account locked until this time"
    )

    # Extended fields
    auth_source = fields.CharField(
        max_length=20,
        default="local",
        description="Auth source: local, ldap, github, etc.",
    )
    external_id = fields.CharField(
        max_length=255, null=True, description="ID from external auth provider"
    )
    avatar_url = fields.CharField(max_length=512, null=True)

    # Password expiration fields
    password_changed_at = fields.DatetimeField(
        null=True, description="When password was last changed"
    )
    password_expires_at = fields.DatetimeField(
        null=True, description="Calculated expiration date"
    )
    force_password_change = fields.BooleanField(
        default=False, description="Force change on next login"
    )
    password_expiration_exempt = fields.BooleanField(
        default=False, description="Exempt from password expiration policy"
    )
    password_expiration_notified_at = fields.DatetimeField(
        null=True, description="Last notification timestamp"
    )

    # TOTP (Two-Factor Authentication) fields
    totp_secret = fields.CharField(
        max_length=255, null=True, description="Encrypted TOTP secret"
    )
    totp_enabled = fields.BooleanField(default=False, description="TOTP 2FA enabled")
    totp_enabled_at = fields.DatetimeField(
        null=True, description="When TOTP was enabled"
    )
    totp_backup_codes_hash = fields.TextField(
        null=True, description="Hashed backup codes (JSON array)"
    )

    roles = fields.ManyToManyField(
        "models.Role", related_name="users", through="user_roles"
    )
    # Teams relation is through TeamMember model (user.team_memberships)

    class Meta:
        table = "users"

    def __str__(self):
        return self.username
