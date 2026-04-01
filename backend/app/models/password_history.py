from tortoise import fields, models


class PasswordHistory(models.Model):
    """Password history model for tracking previous passwords"""

    id = fields.UUIDField(pk=True)
    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User", related_name="password_history", on_delete=fields.CASCADE
    )
    hashed_password = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "password_history"
        ordering = ["-created_at"]

    def __str__(self):
        return f"PasswordHistory for {self.user} at {self.created_at}"
