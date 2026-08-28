# Remnawave Custom 2.8.1

[![Build and publish custom image](https://github.com/Ryanlyjp/remnawave-custom-deploy/actions/workflows/build-and-publish.yml/badge.svg?branch=main)](https://github.com/Ryanlyjp/remnawave-custom-deploy/actions/workflows/build-and-publish.yml)
[![GHCR](https://img.shields.io/badge/GHCR-remnawave--custom-blue?logo=github)](https://github.com/users/Ryanlyjp/packages/container/package/remnawave-custom)

这是基于官方 Remnawave `2.8.1` 维护的自研版本。部署仓库通过 Git submodule 固定前后端源码版本，并使用根目录 Dockerfile 构建单一 Remnawave 镜像。

## 仓库结构

- `backend/`：自研 Backend，基于官方 Backend `2.8.1`
- `frontend/`：自研 Frontend，基于官方 Frontend `2.8.1`
- `Dockerfile`：从固定的前后端源码构建单一镜像
- `docker-compose.build.yml`：构建本地自研镜像
- `docker-compose.production-2.8.1.yml`：生产部署参考 Compose
- `.env.custom.example`：自研兼容功能的安全默认配置

克隆时需要同时获取 submodule：

```bash
git clone --recurse-submodules https://github.com/Ryanlyjp/remnawave-custom-deploy.git
```

## Docker 镜像

预构建镜像公开发布在 GitHub Container Registry，无需登录即可拉取：

```text
ghcr.io/ryanlyjp/remnawave-custom
```

当前发布平台为 `linux/amd64`。镜像包含固定版本的自研 Backend 和 Frontend，以及运行所需的 Prisma 文件、生产依赖和前端静态资源。

### 镜像标签

| 标签 | 用途 |
| --- | --- |
| `2.8.1-policy-modules` | 当前 2.8.1 自研稳定版本，推荐生产部署使用 |
| `latest` | `main` 分支最近一次成功构建 |
| `sha-<commit>` | 与 Deploy 仓库提交一一对应，便于回滚和审计 |
| `v*` | 推送 Git 版本标签时生成的同名镜像标签 |

拉取稳定版本：

```bash
docker pull ghcr.io/ryanlyjp/remnawave-custom:2.8.1-policy-modules
```

也可以固定到某个 Deploy 提交：

```bash
docker pull ghcr.io/ryanlyjp/remnawave-custom:sha-fd99975
```

生产环境如果要求镜像内容绝对不变，可以在 Compose 中使用拉取后显示的 digest：

```text
ghcr.io/ryanlyjp/remnawave-custom@sha256:<digest>
```

### 使用 Compose

准备好 Remnawave 所需的真实 `.env` 后执行：

```bash
docker compose -f docker-compose.production-2.8.1.yml pull
docker compose -f docker-compose.production-2.8.1.yml up -d
```

更新到稳定标签的最新镜像：

```bash
docker compose -f docker-compose.production-2.8.1.yml pull remnawave
docker compose -f docker-compose.production-2.8.1.yml up -d remnawave
```

升级前请先备份数据库、`.env` 和 Compose 文件。

### 自动构建

工作流 `.github/workflows/build-and-publish.yml` 会在以下情况构建并推送镜像：

- `main` 分支更新
- 推送 `v*` Git 标签
- 在 GitHub Actions 页面手动触发

每个镜像都记录 Backend commit、Frontend commit、Deploy revision 和构建时间，并发布 OCI provenance 与 SBOM。发布过程只使用仓库自带的 `GITHUB_TOKEN`，不需要 DockerHub Token 或生产环境密钥。

## 自研功能

策略模块已适配 Remnawave 2.8.1 的 API、缓存和前端编辑器：

- Snippet 增加 `kind`、`scope`、`description`
- 支持 `outbound-set`、`routing-rule-set`、`balancer-set`
- Config Profile 可组合出站、路由规则和 balancer 模块
- 后端生成配置时展开策略模块
- 前端增加独立的“策略模块”页面和创建、编辑界面
- Monaco/Xray WASM 校验前展开模块
- 支持为单个用户设置订阅节点名称，不修改全局 Host 名称

后端数据结构见 `backend/docs/policy-modules.md`。
用户级节点别名的使用、接口和回滚说明见 [`docs/user-host-aliases.md`](docs/user-host-aliases.md)。

## 可选兼容配置

所有兼容行为默认关闭：

| 配置 | 默认值 | 用途 |
| --- | --- | --- |
| `CUSTOM_ALLOW_ADMIN_JWT_API` | `false` | 允许管理员 JWT 在缺少浏览器客户端标识时访问 API；优先使用 scoped API token |
| `CUSTOM_START_XRAY_DIAGNOSTICS` | `false` | 记录 StartXray 的错误码、HTTP 状态和响应数据，不记录 headers |
| `CUSTOM_SUBSCRIPTION_ADDRESS_OVERRIDES` | `{}` | 用 JSON 对象按用户名替换订阅节点地址 |

地址覆盖示例：

```env
CUSTOM_SUBSCRIPTION_ADDRESS_OVERRIDES={"example-user":"proxy.example.com"}
```

不要把真实 `.env`、订阅链接、节点凭据或数据库备份提交到仓库。

## 构建

```bash
BACKEND_COMMIT=$(git -C backend rev-parse HEAD) \
FRONTEND_COMMIT=$(git -C frontend rev-parse HEAD) \
BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
docker compose -f docker-compose.build.yml build
```

也可以直接构建：

```bash
docker build -t remnawave/backend:custom-2.8.1-policy-modules .
```

Frontend 官方 lockfile 使用原有 peer dependency 模式，根目录 Dockerfile 已使用 `npm ci --legacy-peer-deps`。

## 部署注意事项

升级前应备份 `.env`、Compose 和数据库，并验证数据库迁移、节点同步、策略模块展开及订阅输出。生产环境建议使用不可变镜像标签或 digest。

订阅签名 URL、Host fallback 和 IPv6 分享链接实验代码未合入本版本。

## License

Backend 和 Frontend 延续上游项目的 `AGPL-3.0-only` 许可。使用和分发时请保留上游版权及许可信息。
