# 快速开始指南

使用 Docker Compose 快速启动 Clouisle。

## 前置要求

- Docker 和 Docker Compose
- 最低 4GB RAM
- 现代网络浏览器

## 1. 克隆仓库

```bash
git clone https://github.com/clouisle/Clouisle.git
cd clouisle
```

## 2. 配置环境变量

```bash
# 复制 Docker 部署环境变量文件
cp deploy/.env.example deploy/.env

# 编辑 deploy/.env，为以下字段设置强随机值：
#   SECRET_KEY、POSTGRES_PASSWORD、REDIS_PASSWORD、QDRANT_API_KEY、
#   SANDBOX_ARTIFACT_UPLOAD_API_KEY、INTERNAL_API_TOKEN
# INTERNAL_API_TOKEN 为必填项——缺少时 docker compose 将拒绝启动。
# 生成方式：openssl rand -hex 32
```

## 3. 启动 Clouisle

```bash
cd deploy
docker compose --env-file .env up -d
```

## 4. 访问应用

- **前端**：http://localhost:3000
- **API 文档**：http://localhost:8000/docs

## 入门步骤

1. 注册你的第一个账号——没有预置的管理员凭据；首个注册用户会自动成为超级管理员
2. 创建你的第一个团队
3. 添加 AI 模型（侧边栏中的「模型」）
4. 创建知识库并上传文档
5. 构建 AI Agent 并开始对话

## 下一步

- [基本概念](./basic-concepts_zh-CN.md)
- [开发环境搭建](./development_zh-CN.md) — 面向贡献者
- [用户指南](../user-guide/)
- [管理指南](../admin-guide/)
- [部署指南](../deployment/DEPLOYMENT_zh-CN.md)
