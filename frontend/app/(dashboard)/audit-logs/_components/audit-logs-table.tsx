"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { format } from "date-fns";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Download,
  Eye,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  X,
  FileText,
  FileJson,
} from "lucide-react";
import { auditLogsApi, AuditLog, AuditLogListParams } from "@/lib/api/audit-logs";
import { toast } from "sonner";
import { DataTableFacetedFilter } from "@/components/ui/data-table-faceted-filter";
import { AuditLogDrawer } from "./audit-log-drawer";

export function AuditLogsTable() {
  const t = useTranslations("auditLogs");
  const commonT = useTranslations("common");
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(0);
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Filters
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string[]>([]);
  const [actionFilter, setActionFilter] = useState<string[]>([]);

  const loadLogs = async () => {
    try {
      setLoading(true);
      const params = {
        page,
        page_size: pageSize,
        search: search || undefined,
        status: statusFilter.length === 1 ? statusFilter[0] : undefined,
        action: actionFilter.length === 1 ? actionFilter[0] : undefined,
      };
      const data = await auditLogsApi.list(params);
      setLogs(data.items);
      setTotalPages(data.total_pages);
    } catch (error) {
      console.error("Failed to load audit logs:", error);
      toast.error(t("failedToLoadLogs"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, search, statusFilter, actionFilter]);

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
  };

  const handlePageSizeChange = (newPageSize: number) => {
    setPageSize(newPageSize);
    setPage(1);
  };

  const handleExport = async (format: "csv" | "json") => {
    try {
      const params = {
        search: search || undefined,
        status: statusFilter.length === 1 ? statusFilter[0] : undefined,
        action: actionFilter.length === 1 ? actionFilter[0] : undefined,
      };
      const blob = await auditLogsApi.export(params, format);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-logs-${format}-${Date.now()}.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      toast.success(t("exportSuccess"));
    } catch (error) {
      console.error("Failed to export audit logs:", error);
      toast.error(t("exportFailed"));
    }
  };

  const resetFilters = () => {
    setSearch("");
    setStatusFilter([]);
    setActionFilter([]);
    setPage(1);
  };

  const hasFilters = search || statusFilter.length > 0 || actionFilter.length > 0;

  const handleViewDetails = (log: AuditLog) => {
    setSelectedLog(log);
    setDrawerOpen(true);
  };

  const getStatusBadge = (status: string) => {
    if (status === "success") {
      return <Badge className="bg-green-500">{t("statusSuccess")}</Badge>;
    }
    return <Badge variant="destructive">{t("statusFailed")}</Badge>;
  };

  const getOperationBadge = (operation: string) => {
    const colors: Record<string, string> = {
      create: "bg-blue-500",
      read: "bg-gray-500",
      update: "bg-yellow-500",
      delete: "bg-red-500",
    };
    return (
      <Badge className={colors[operation] || "bg-gray-500"}>
        {t(`operation${operation.charAt(0).toUpperCase() + operation.slice(1)}`)}
      </Badge>
    );
  };

  const statusOptions = [
    { label: t("statusSuccess"), value: "success" },
    { label: t("statusFailed"), value: "failed" },
  ];

  const actionOptions = [
    { label: t("actionLoginSuccess"), value: "login_success" },
    { label: t("actionLoginFailed"), value: "login_failed" },
    { label: t("actionLogout"), value: "logout" },
    { label: t("actionRegister"), value: "register" },
    { label: t("actionCreateUser"), value: "create_user" },
    { label: t("actionUpdateUser"), value: "update_user" },
    { label: t("actionDeleteUser"), value: "delete_user" },
  ];

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>{t("auditLogs")}</CardTitle>
        </CardHeader>
        <CardContent>
          {/* Filters */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-4">
            <div className="flex flex-1 items-center gap-2 flex-wrap">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder={t("searchPlaceholder")}
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setPage(1);
                  }}
                  className="pl-8"
                />
              </div>

              <DataTableFacetedFilter
                title={t("filterByStatus")}
                options={statusOptions}
                selectedValues={new Set(statusFilter)}
                onSelectionChange={(values) => {
                  setStatusFilter(Array.from(values));
                  setPage(1);
                }}
              />

              <DataTableFacetedFilter
                title={t("filterByAction")}
                options={actionOptions}
                selectedValues={new Set(actionFilter)}
                onSelectionChange={(values) => {
                  setActionFilter(Array.from(values));
                  setPage(1);
                }}
              />

              {hasFilters && (
                <Button variant="ghost" onClick={resetFilters} className="h-8 px-2 lg:px-3">
                  {commonT("reset")}
                  <X className="ml-2 h-4 w-4" />
                </Button>
              )}
            </div>

            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button variant="outline">
                    <Download className="h-4 w-4 mr-2" />
                    {t("export")}
                  </Button>
                }
              />
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => handleExport("csv")}>
                  <FileText className="h-4 w-4 mr-2" />
                  {t("exportCSV")}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleExport("json")}>
                  <FileJson className="h-4 w-4 mr-2" />
                  {t("exportJSON")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {/* Table */}
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("time")}</TableHead>
                  <TableHead>{t("user")}</TableHead>
                  <TableHead>{t("action")}</TableHead>
                  <TableHead>{t("resourceType")}</TableHead>
                  <TableHead>{t("resourceName")}</TableHead>
                  <TableHead>{t("operation")}</TableHead>
                  <TableHead>{t("status")}</TableHead>
                  <TableHead>{t("ipAddress")}</TableHead>
                  <TableHead className="text-right">{t("actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center">
                      {t("loading")}
                    </TableCell>
                  </TableRow>
                ) : logs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center">
                      {t("noLogs")}
                    </TableCell>
                  </TableRow>
                ) : (
                  logs.map((log) => (
                    <TableRow key={log.id}>
                      <TableCell className="whitespace-nowrap">
                        {format(new Date(log.created_at), "yyyy-MM-dd HH:mm:ss")}
                      </TableCell>
                      <TableCell>{log.username || t("system")}</TableCell>
                      <TableCell>{t(`action${log.action}`) || log.action}</TableCell>
                      <TableCell>{log.resource_type}</TableCell>
                      <TableCell>{log.resource_name || "-"}</TableCell>
                      <TableCell>{getOperationBadge(log.operation)}</TableCell>
                      <TableCell>{getStatusBadge(log.status)}</TableCell>
                      <TableCell className="font-mono text-xs">
                        {log.ip_address || "-"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleViewDetails(log)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Select
                value={pageSize.toString()}
                onValueChange={(value) => handlePageSizeChange(Number(value))}
              >
                <SelectTrigger size="sm" className="w-18">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent side="top" alignItemWithTrigger={false}>
                  <SelectItem value="10">10</SelectItem>
                  <SelectItem value="20">20</SelectItem>
                  <SelectItem value="50">50</SelectItem>
                  <SelectItem value="100">100</SelectItem>
                </SelectContent>
              </Select>
              <span>{t("rowsPerPage")}</span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">
                {t("pageInfo", { page, total: totalPages || 1 })}
              </span>

              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => handlePageChange(1)}
                  disabled={page === 1}
                >
                  <ChevronsLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => handlePageChange(page - 1)}
                  disabled={page === 1}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => handlePageChange(page + 1)}
                  disabled={page >= totalPages}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => handlePageChange(totalPages)}
                  disabled={page >= totalPages}
                >
                  <ChevronsRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Details Drawer */}
      <AuditLogDrawer
        log={selectedLog}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
      />
    </>
  );
}
