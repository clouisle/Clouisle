import json
import logging
from datetime import timedelta
from pathlib import Path

from app.core.celery import celery_app
from app.core.timezone import now_utc
from app.models.audit_log import AuditLog
from app.models.site_setting import SiteSetting

logger = logging.getLogger(__name__)


async def archive_old_audit_logs():
    """归档超过保留期限的审计日志（同步执行）"""
    try:
        # 从站点设置获取保留天数
        retention_days = await SiteSetting.get_value("audit_log_retention_days", 365)
        cutoff_date = now_utc() - timedelta(days=retention_days)

        # 查询需要归档的日志
        old_logs = await AuditLog.filter(created_at__lt=cutoff_date).all()
        if not old_logs:
            logger.info("No audit logs to archive")
            return {
                "status": "success",
                "archived_count": 0,
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
            }

        # 获取归档路径
        archive_path = await SiteSetting.get_value(
            "audit_log_archive_path", "/var/log/clouisle/audit_archives"
        )
        archive_dir = Path(archive_path)
        archive_dir.mkdir(parents=True, exist_ok=True)

        # 按月份分组归档
        logs_by_month = {}
        for log in old_logs:
            month_key = log.created_at.strftime("%Y%m")
            if month_key not in logs_by_month:
                logs_by_month[month_key] = []
            logs_by_month[month_key].append(log.to_dict())

        # 导出为JSON文件
        archived_count = 0
        for month_key, logs in logs_by_month.items():
            archive_file = archive_dir / f"audit_logs_{month_key}.json"

            # 如果文件已存在，追加到现有数据
            existing_logs = []
            if archive_file.exists():
                with open(archive_file, "r", encoding="utf-8") as f:
                    try:
                        existing_logs = json.load(f)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to read existing archive {archive_file}")

            # 合并并写入
            all_logs = existing_logs + logs
            with open(archive_file, "w", encoding="utf-8") as f:
                json.dump(all_logs, f, indent=2, ensure_ascii=False)

            archived_count += len(logs)
            logger.info(f"Archived {len(logs)} logs to {archive_file}")

        # 删除已归档的日志
        await AuditLog.filter(created_at__lt=cutoff_date).delete()
        logger.info(f"Successfully archived and deleted {archived_count} audit logs")

        return {
            "status": "success",
            "archived_count": archived_count,
            "retention_days": retention_days,
            "cutoff_date": cutoff_date.isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to archive audit logs: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@celery_app.task
async def create_audit_log_task(log_data: dict):
    """异步创建审计日志"""
    try:
        await AuditLog.create(**log_data)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
