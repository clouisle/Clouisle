# 安全检查清单

在向用户开放 Clouisle 前使用此清单。清单描述运维人员的责任；提供的 Compose 或 Kubernetes 文件不会自动让项目项变为已完成。

## 密钥与配置

- [ ] 替换 `SECRET_KEY`、`POSTGRES_PASSWORD`、`REDIS_PASSWORD` 和 `QDRANT_API_KEY` 的所有默认值。
- [ ] 设置唯一且非空的 `INTERNAL_API_TOKEN`；API、worker 与 sandbox-worker 共享它，用于经认证的内部上传网关。
- [ ] 不要把 `.env`、Kubernetes Secret manifest 或安装器生成文件提交到代码仓库，并限制文件权限。
- [ ] 尽量使用密钥管理器或外部管理的 Kubernetes Secret 保存生产密钥；通过有计划的维护窗口轮换密钥。
- [ ] 确认 `API_BASE_URL`/`API_INTERNAL_BASE_URL` 是内部服务地址，而 `PUBLIC_API_URL`、`FRONTEND_URL` 和 `BACKEND_CORS_ORIGINS` 使用浏览器可访问的公网 origin。

## 认证与访问控制

- [ ] 仅在部署保持私有时注册首个账户；首个注册用户会成为初始超级用户。
- [ ] 按策略在管理界面配置会话时长、注册、邮箱/SSO 等站点设置。
- [ ] 定期检查团队成员和管理权限，删除不再使用的 API key 与集成。
- [ ] 使用 MFA/SSO 时，先测试身份提供商配置和恢复路径。

## 网络与代理

- [ ] 在外部反向代理或 Kubernetes Ingress 终止 HTTPS，并使用有效证书。
- [ ] 仅公开 frontend/反向代理端口；PostgreSQL、Redis、Qdrant 和直连 API 端口保持在私有网络。
- [ ] 使用精确的 CORS origin，生产环境不要使用 `*`。
- [ ] 为流式响应配置 HTTP/1.1、`proxy_buffering off`，以及与提供的 1800 秒示例一致的读写超时。
- [ ] 通过 RBAC、NetworkPolicy 和合适的 Ingress 策略限制 `clouisle` 命名空间的 Kubernetes 访问。

## 数据保护与恢复

- [ ] 在支持的环境中对 PostgreSQL、Qdrant、上传文件和备份存储启用静态加密。
- [ ] 按明确计划备份 PostgreSQL、Qdrant 快照和上传文件；Redis 仅保存缓存/队列状态，可选备份。
- [ ] 保留加密的异地副本并定义保留策略。
- [ ] 测试包含 Qdrant 和上传文件的完整恢复，并记录 RTO/RPO 结果。
- [ ] 除非明确执行破坏性操作，不要运行 `docker compose down -v` 或删除 PVC。

## 运行时与沙箱

- [ ] 生产镜像使用固定 tag/digest，不要依赖 `latest`；部署前扫描镜像。
- [ ] 保持沙箱文件系统隔离，并保留 Worker 所需的 seccomp/能力配置。修改前请查看受保护的沙箱加固说明。
- [ ] 按威胁模型在宿主机/集群层限制沙箱出站网络和资源使用。
- [ ] 及时更新 Docker、Kubernetes、PostgreSQL、Redis、Qdrant、Bubblewrap 和宿主机内核。

## 日志与事件响应

- [ ] 收集并保护 API、worker、beat、frontend 和代理日志，排除 token 与密码。
- [ ] 轮询 `GET /api/v1/health`，并使用管理端可观测性 API/仪表盘（需要 `admin:dashboard:access`）。项目没有内置 Prometheus `/metrics` 端点。
- [ ] 对健康检查失败、异常认证、队列积压、磁盘耗尽和备份失败配置告警。
- [ ] 记录升级、密钥轮换、隔离、恢复和事后复盘流程。
