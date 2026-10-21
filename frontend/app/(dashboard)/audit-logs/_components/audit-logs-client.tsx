"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Activity, AlertCircle, CheckCircle, Users } from "lucide-react";
import { StatCard } from "@/components/dashboard/stat-card";
import { AuditLogsTable } from "./audit-logs-table";
import { auditLogsApi, AuditLogStats } from "@/lib/api/admin/audit-logs";

export function AuditLogsClient() {
  const t = useTranslations("auditLogs");
  const [stats, setStats] = useState<AuditLogStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const data = await auditLogsApi.getStats();
      setStats(data);
    } catch (error) {
      console.error("Failed to load audit log stats:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">{t("title")}</h1>
        <p className="text-muted-foreground mt-2">{t("description")}</p>
      </div>

      {/* Statistics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title={t("totalLogs")}
          value={stats?.total_logs ?? 0}
          icon={Activity}
          tone="blue"
          hint={t("allTimeRecords")}
          isLoading={loading}
        />
        <StatCard
          title={t("todayLogs")}
          value={stats?.today_logs ?? 0}
          icon={CheckCircle}
          tone="green"
          hint={t("recordsToday")}
          isLoading={loading}
        />
        <StatCard
          title={t("failedLogs")}
          value={stats?.failed_logs ?? 0}
          icon={AlertCircle}
          tone="red"
          hint={t("failedOperations")}
          isLoading={loading}
        />
        <StatCard
          title={t("activeUsers")}
          value={stats?.active_users ?? 0}
          icon={Users}
          tone="purple"
          hint={t("last7Days")}
          isLoading={loading}
        />
      </div>

      {/* Audit Logs Table */}
      <AuditLogsTable />
    </div>
  );
}
