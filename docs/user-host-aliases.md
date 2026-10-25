# 用户级订阅节点别名

该功能允许管理员为单个用户自定义订阅中的 Host 和受管 TUIC 节点显示名称，不修改地址、端口、协议参数、路由配置或全局名称。

## 名称优先级

订阅生成时按以下顺序确定节点名称：

1. 当前用户和 Host 对应的自定义别名
2. 当前全局 `hosts.remark`
3. 订阅生成器原有的重名去重逻辑

数据库使用 `user_host_aliases` 保存 `user_id + host_uuid -> remark`。用户或 Host 被删除时，对应别名会通过外键级联删除。

受管 TUIC 使用 `user_singbox_profile_aliases` 保存 `user_id + config_profile_uuid -> remark`，默认名称来自目标的无凭据 `subscriptionUrl`。用户或 Sing-box Profile 被删除时，对应别名同样级联删除。

## 管理界面

打开任意用户的编辑界面后，底部的“订阅节点名称”区域会列出该用户当前可见的 Host 和受管 TUIC。TUIC 只有在用户所属 Internal Squad 选中对应 Sing-box inbound 时才会出现。

- **保存**：只保存非空且不同于当前 Host 名称的别名。
- **放弃更改**：恢复到上一次成功加载或保存的名称。
- **重置为默认名称**：Host 恢复当前全局名称，TUIC 恢复目标 `subscriptionUrl` 的名称；随后点击保存会删除该用户的自定义别名。

修改用户所属 Internal Squad 后，界面会重新获取该用户当前可见的 Host。

## API

管理接口位于：

```text
GET /api/users/:uuid/host-aliases
PUT /api/users/:uuid/host-aliases
```

PUT 请求会完整替换该用户的 Host 和受管 TUIC 别名集合。Backend 会拒绝不属于该用户当前可见集合的 Host 或 Profile UUID，名称会去除首尾空格并限制为 1 到 50 个字符。

## 部署与迁移

部署新版本时，容器入口会自动应用迁移 `20260828003000_add_user_host_aliases` 和 `20261024180000_add_user_singbox_profile_aliases`。升级前应备份 PostgreSQL、`.env` 和 Compose 文件，并使用固定镜像标签或 digest。

数据库迁移只增加别名表和索引，不修改现有用户、Host、Profile 或订阅数据。未设置别名的用户继续使用原有默认名称。

## 回滚

应用回滚时，把 Compose 中的 Remnawave 镜像恢复为升级前标签，再只重建 Remnawave 服务：

```bash
docker compose up -d --no-deps remnawave
```

保留 `user_host_aliases` 和 `user_singbox_profile_aliases` 表不会影响旧版本运行，也能避免重新升级时丢失已保存别名。只有确认永久放弃该功能并已另行备份数据后，才应手工删除对应表。
