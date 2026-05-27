"use client";

import { useTranslations } from "next-intl";
import { format } from "date-fns";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { AuditLog } from "@/lib/api/admin/audit-logs";

interface AuditLogDrawerProps {
  log: AuditLog | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AuditLogDrawer({ log, open, onOpenChange }: AuditLogDrawerProps) {
  const t = useTranslations("auditLogs");

  if (!log) return null;

  const getStatusBadge = (status: string) => {
    if (status === "success") {
      return <Badge className="bg-green-500">{t("statusSuccess")}</Badge>;
    }
    return <Badge variant="destructive">{t("statusFailed")}</Badge>;
  };

  const getOperationLabel = (operation: string) => {
    if (!operation) return "";
    const key = `operation${operation.charAt(0).toUpperCase() + operation.slice(1)}`;
    return t.has(key) ? t(key) : operation;
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-2xl overflow-y-auto">
        <SheetHeader className="px-6">
          <SheetTitle>{t("logDetails")}</SheetTitle>
          <SheetDescription>
            {format(new Date(log.created_at), "yyyy-MM-dd HH:mm:ss")}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-6 px-6 pb-6">{/* 添加 px-6 和 pb-6 */}
          {/* Basic Information */}
          <div>
            <h3 className="text-sm font-semibold mb-3">{t("basicInfo")}</h3>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">{t("status")}</span>
                {getStatusBadge(log.status)}
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">{t("action")}</span>
                <span className="text-sm font-medium">
                  {t.has(`action${log.action}`) ? t(`action${log.action}`) : log.action}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">{t("operation")}</span>
                <span className="text-sm font-medium">{getOperationLabel(log.operation)}</span>
              </div>
            </div>
          </div>

          <Separator />

          {/* User Information */}
          <div>
            <h3 className="text-sm font-semibold mb-3">{t("userInfo")}</h3>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">{t("username")}</span>
                <span className="text-sm font-medium">{log.username || t("system")}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">{t("userId")}</span>
                <span className="text-sm font-mono">{log.user_id || "-"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">{t("authMethod")}</span>
                <span className="text-sm font-medium">{log.auth_method || "-"}</span>
              </div>
            </div>
          </div>

          <Separator />

          {/* Resource Information */}
          <div>
            <h3 className="text-sm font-semibold mb-3">{t("resourceInfo")}</h3>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">{t("resourceType")}</span>
                <span className="text-sm font-medium">{log.resource_type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">{t("resourceName")}</span>
                <span className="text-sm font-medium">{log.resource_name || "-"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">{t("resourceId")}</span>
                <span className="text-sm font-mono">{log.resource_id || "-"}</span>
              </div>
            </div>
          </div>

          <Separator />

          {/* Request Information */}
          <div>
            <h3 className="text-sm font-semibold mb-3">{t("requestInfo")}</h3>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">{t("ipAddress")}</span>
                <span className="text-sm font-mono">{log.ip_address || "-"}</span>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-sm text-muted-foreground">{t("userAgent")}</span>
                <span className="text-xs font-mono break-all text-muted-foreground">
                  {log.user_agent || "-"}
                </span>
              </div>
            </div>
          </div>

          {/* Error Message */}
          {log.error_message && (
            <>
              <Separator />
              <div>
                <h3 className="text-sm font-semibold mb-3 text-red-500">
                  {t("errorMessage")}
                </h3>
                <div className="bg-red-50 dark:bg-red-950 p-3 rounded-md">
                  <p className="text-sm text-red-700 dark:text-red-300">
                    {log.error_message}
                  </p>
                </div>
              </div>
            </>
          )}

          {/* Changes */}
          {log.changes && (
            <>
              <Separator />
              <div>
                <h3 className="text-sm font-semibold mb-3">{t("changes")}</h3>
                <div className="space-y-4">
                  {log.changes.before && (
                    <div>
                      <h4 className="text-xs font-medium text-muted-foreground mb-2">
                        {t("before")}
                      </h4>
                      <pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto">
                        {JSON.stringify(log.changes.before, null, 2)}
                      </pre>
                    </div>
                  )}
                  {log.changes.after && (
                    <div>
                      <h4 className="text-xs font-medium text-muted-foreground mb-2">
                        {t("after")}
                      </h4>
                      <pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto">
                        {JSON.stringify(log.changes.after, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}

          {/* Metadata */}
          {log.metadata && Object.keys(log.metadata).length > 0 && (
            <>
              <Separator />
              <div>
                <h3 className="text-sm font-semibold mb-3">{t("metadata")}</h3>
                <pre className="bg-muted p-3 rounded-md text-xs overflow-x-auto">
                  {JSON.stringify(log.metadata, null, 2)}
                </pre>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
