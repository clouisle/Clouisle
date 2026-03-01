"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Activity, AlertCircle, CheckCircle, Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t("totalLogs")}
            </CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? "..." : stats?.total_logs.toLocaleString() || 0}
            </div>
            <p className="text-xs text-muted-foreground">
              {t("allTimeRecords")}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t("todayLogs")}
            </CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? "..." : stats?.today_logs.toLocaleString() || 0}
            </div>
            <p className="text-xs text-muted-foreground">
              {t("recordsToday")}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t("failedLogs")}
            </CardTitle>
            <AlertCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? "..." : stats?.failed_logs.toLocaleString() || 0}
            </div>
            <p className="text-xs text-muted-foreground">
              {t("failedOperations")}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t("activeUsers")}
            </CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? "..." : stats?.active_users.toLocaleString() || 0}
            </div>
            <p className="text-xs text-muted-foreground">
              {t("last7Days")}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Audit Logs Table */}
      <AuditLogsTable />
    </div>
  );
}
