# Docker 环境安装与基础服务启动（pgx-rag）

> 这份文档解决一件事：**把 `docker compose up -d` 在这台机器上真正跑通**。
> 里面对环境现状的描述都是实测结果（2026-11-10），不是通用模板。

---

## 0. 这台机器的现状（已核查）

| 项目 | 实测值 | 对安装的影响 |
|---|---|---|
| 系统 | Windows 11 25H2，build 26200.9445（注册表 ProductName 仍写 “Windows 10 Home China”，是历史遗留字段，忽略） | Home 版没有完整 Hyper-V，但 **WSL2 后端可用**，够用 |
| CPU | Intel i9-14900HX | x86_64，所有镜像都有 amd64 版本 |
| 虚拟化 | `HvHost`、`vmcompute` 服务均在 Running | 虚拟化已在 BIOS 层开启，不用再进 BIOS |
| WSL | `wsl --version` = 2.6.3.0，内核 6.6.87.2；发行版 **Ubuntu（Version=2，状态 Stopped）** | **这是好事**：Docker Desktop 的 WSL2 后端依赖它，已经现成可用 |
| Docker | 未安装。`docker` 不在 PATH，`C:\Program Files\Docker`、`%LOCALAPPDATA%\Docker`、`%ProgramData%\DockerDesktop` 三处都不存在 | 需要从零装 Docker Desktop |
| 当前用户 | `LAPTOP-EIDRJHCT\Deide`，**不是管理员** | 安装必须走 UAC 提权，必须用「以管理员身份运行」的终端 |
| 磁盘 | C: 剩 32 GB / 400 GB；D: 剩 83 GB / 551 GB | **C 盘偏紧**，镜像要挪到 D 盘（第 3 步） |
| 端口 | 原生 `MySQL80` 服务在跑，占用 3306 | 所以容器映射到 **3307**，`conf/app_config.yaml` 已对齐 |

> 注意：在 DSH 沙箱里执行 `wsl -l -v` 会返回 `Wsl/E_ACCESSDENIED`，那是沙箱限制，**不是环境坏了**。
> 用管理员终端手动跑一次确认即可：`wsl -l -v` 应输出 `Ubuntu  Stopped  2`。

---

## 1. 安装 Docker Desktop

打开**「以管理员身份运行」**的 PowerShell（开始菜单搜 PowerShell → 右键 → 以管理员身份运行），执行：

```powershell
winget install --id Docker.DockerDesktop -e --source winget `
  --accept-package-agreements --accept-source-agreements
```

- 大约下载 500 MB+，装到 `C:\Program Files\Docker\Docker`，安装完提示 **注销或重启**，照做。
- 重启后通常会自动把当前用户加进 `docker-users` 组；若 `docker` 仍不可用，管理员终端执行：
  ```powershell
  net localgroup docker-users "$env:USERNAME" /add
  ```
  再注销重进。

**winget 装不上时的备选**（直接下官方安装包，右键 → 以管理员身份运行）：

<https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe>

---

## 2. 首次启动 Docker Desktop 的设置

启动 Docker Desktop（托盘出现鲸鱼图标），按下面四项确认：

1. **接受协议** → 出现登录页时点 **Skip / Continue without signing in**（本项目不需要 Docker 账号登录）。
2. **Settings → General** → 勾选 **Use the WSL 2 based engine**（默认已勾）。
3. **Settings → Resources → WSL Integration** → 打开 **Ubuntu** 的开关（这样 `wsl -d Ubuntu` 里也能用到 docker，可选）。
4. 等到左下角显示 **Engine running**（绿色），再进行下一步。

> 首次启动若提示 “WSL update required”，在普通终端执行 `wsl --update`，然后用管理员终端 `wsl --shutdown` 再重启 Docker Desktop。

---

## 3. 把镜像数据挪到 D 盘（重要，C 盘只剩 32 GB）

本项目五个服务拉下来约 **4–5 GB**，Docker 默认把 WSL 磁盘镜像放在 `C:\Users\Deide\AppData\Local\Docker\wsl`，会把 C 盘吃紧。

**Settings → Resources → Advanced → Disk image location** 改成：

```
D:\Docker\wsl
```

改完后点 **Apply & restart**，Docker 会把已有数据搬过去（首次为空，几乎瞬间完成）。

顺手可以限制 WSL 的内存占用，避免 Docker 把整机内存吃光。若这台是 16 GB 内存，建一个
`C:\Users\Deide\.wslconfig`：

```ini
[wsl2]
memory=8GB
processors=8
swap=2GB
```

改完 `wsl --shutdown` 生效。

---

## 4. 验证 Docker 本体

**普通**（非管理员）新开一个终端：

```powershell
docker version
docker compose version
docker run --rm hello-world
```

三行依次应有：
- `Server: Docker Desktop ...`（能连上引擎，说明不是只有客户端）
- `Docker Compose version v2.x`
- `Hello from Docker!`

任何一步失败，先看第 8 节排查表，别急着往下走。

---

## 5. 启动项目的基础服务

```powershell
cd "D:\AI RAG\pgx-rag\docker"

docker compose config --quiet     # 语法自检，没输出就是通过
docker compose up -d              # mysql / qdrant / elasticsearch / kibana
docker compose ps
```

第一次会拉 4 个镜像并**本地构建** ES 镜像（加 IK 中文分词插件），5–15 分钟取决于网速。
最终 `docker compose ps` 应该是：

```
NAME                SERVICE         STATUS
pgx-mysql           mysql           Up (healthy)
pgx-qdrant          qdrant          Up
pgx-elasticsearch   elasticsearch   Up (healthy)
pgx-kibana          kibana          Up
```

**为什么只有 4 个**：第 5 个服务 `embedding`（TEI）加了 `profiles: ["embedding"]`，
默认不启动——本机没有模型文件，而且现有索引不是它建的（见第 7 节）。

验证各服务是否真的可用：

```powershell
# Elasticsearch：返回带 "You Know, for Search" 的 JSON，且 version.number = 8.19.10
(Invoke-WebRequest http://localhost:9200 -UseBasicParsing).Content

# Qdrant：{"result":{"collections":[]},"status":"ok"}
(Invoke-WebRequest http://localhost:6333/collections -UseBasicParsing).Content

# Kibana：浏览器打开 http://localhost:5601 ，等到 “Kibana is ready” 或登录页
Start-Process http://localhost:5601

# MySQL：容器内 3306 映射到本机 3307，能列出 pgx_meta 即初始化 SQL 已执行
docker exec -it pgx-mysql mysql -udidilili -pdili123 -e "show databases;"
```

MySQL 的建表 SQL 是 `docker/mysql/init/01_schema.sql`，**只在数据卷首次创建时执行**；
改完 SQL 想重跑必须 `docker compose down -v`（会清空数据，慎用）。

---

## 6. 项目自检

```powershell
cd "D:\AI RAG\pgx-rag"
uv run python -m app.scripts.check_services
```

预期输出：

```
✅ MySQL         端口可达
✅ Qdrant        HTTP 200
✅ Elasticsearch HTTP 200
❌ TEI Embedding ConnectError: ...
✅ LLM 密钥      deepseek-chat / 已配置
就绪 4/5
```

`TEI Embedding` 这一行 ❌ 是**预期**的：配置里 `embedding.backend: tei`，但 TEI 容器没启动。
两个选择：

- **保持现状**（推荐，阶段 3 走云端）：把 `conf/app_config.yaml` 的 `embedding.backend` 改成 `dashscope`，
  自检那一行会变成「跳过」，5/5 全绿。
- **要本地向量化**：见第 7 节。

---

## 7. 可选：本地向量化（TEI + bge-large-zh-v1.5）

**前提认知**：`data/index/vectors/vectors.json` 里记录的编码器是
`dashscope:text-embedding-v4`（1024 维）。换成本地 bge-large-zh-v1.5 虽然**维度同样是 1024**，
但**向量空间不同**，旧向量不能复用，必须重建索引。所以这一步只在「要完全离线」时才做。

```powershell
cd "D:\AI RAG\pgx-rag"

# 1) 下模型（约 1.3 GB）。国内直连 huggingface.co 常失败，用镜像站
$env:HF_ENDPOINT = "https://hf-mirror.com"
uv pip install huggingface_hub
uv run huggingface-cli download BAAI/bge-large-zh-v1.5 `
  --local-dir docker/embedding/bge-large-zh-v1.5

# 2) 目录里应看到 config.json / model.safetensors / tokenizer.json /
#    1_Pooling/config.json / modules.json 等文件
dir docker\embedding\bge-large-zh-v1.5

# 3) 带上 embedding profile 启动（会额外拉 TEI 镜像 ~1.5 GB）
cd docker
docker compose --profile embedding up -d
docker compose ps          # 多一个 pgx-embedding，等 STATUS 变成 Up
Invoke-WebRequest http://localhost:8081/health -UseBasicParsing | Select-Object -Expand StatusCode
```

`/health` 返回 200 表示模型已加载完。然后回项目根改 `conf/app_config.yaml`：
`embedding.backend: tei`，并**重建向量索引**（`uv run python scripts/build_index.py --workers 4`，
旧实现脚本在 `legacy/`，迁移后以 `app/scripts` 为准）。

---

## 8. 已修复的三处坑（否则 `up` 必挂）

这三处是这次只读排查时实测出来的，已在本目录改好：

| # | 文件 | 问题 | 处理 |
|---|---|---|---|
| 1 | `docker-compose.yaml` | 文件开头是 python 的 `"""..."""` 文档字符串。YAML 里它不是注释，PyYAML 解析直接报 `expected '<document start>', but found '<scalar>'`，`docker compose` 第一步就失败 | 改成 `#` 注释；并给 ES 加 healthcheck、给 kibana 加 `condition: service_healthy` |
| 2 | `elasticsearch/Dockerfile` | IK 插件地址 `github.com/infinilabs/analysis-ik/releases/download/v8.19.10/...` 实测 **404**（IK 已不再在 GitHub Releases 发布），`docker compose build` 必挂 | 改为 `release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-8.19.10.zip`（该文件实测存在，4 MB） |
| 3 | `docker-compose.yaml` 的 `embedding` | 挂载源 `./embedding/bge-large-zh-v1.5` 目录**不存在**，容器起来会因找不到模型反复重启 | 加 `profiles: ["embedding"]` 隔离，默认不启动（第 7 节按需启用） |

镜像 tag 也都核对过，都是真实存在的：
`mysql:8.0` ✅、`qdrant/qdrant:v1.16` ✅、`elasticsearch:8.19.10` ✅、`kibana:8.19.10` ✅。

---

## 9. 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| `docker: 无法将“docker”项识别为...` | 装完没重启终端/Docker Desktop 没启动。重开终端；托盘鲸鱼图标 → 确认 Engine running |
| `error during connect: ... The system cannot find the file specified` | Docker Desktop 引擎没起来（WSL 后端挂了）。管理员终端 `wsl --shutdown`，再重启 Docker Desktop |
| `docker.elastic.co` 拉不动或极慢 | 改 `elasticsearch/Dockerfile` 的 `BASE_IMAGE=elasticsearch:8.19.10`（Docker Hub 官方同名镜像），然后 `docker compose build --no-cache elasticsearch` |
| `docker compose build` 报 IK 下载失败 | IK 版本必须与 ES 版本**完全一致**；确认 `IK_VERSION` 与 `ES_VERSION` 相同。也可直接注释掉 Dockerfile 里的 `elasticsearch-plugin install`，退回无 IK 的官方镜像（本项目中文分词主要在查询侧，影响可接受） |
| ES 容器 Exited | `docker compose logs elasticsearch`。常见是 `vm.max_map_count` 或内存不足；WSL2 后端一般不会，先看日志 |
| Kibana 一直 `Not Ready` | 等 2–3 分钟；已加 `service_healthy` 依赖，正常情况会自己好 |
| `Bind for 0.0.0.0:3307 failed: port is already allocated` | 端口被占。`netstat -ano \| findstr :3307` 找 PID，或改 `docker-compose.yaml` 里的宿主端口（同时改 `conf/app_config.yaml`） |
| C 盘爆满 | 见第 3 步改 Disk image location；已拉取的镜像可用 `docker system prune -a` 清理 |
| `wsl -l -v` 报 `E_ACCESSDENIED` | 在 DSH 沙箱里正常。用管理员终端执行 `wsl --shutdown` 后重试 |
| 想彻底重来 | `docker compose down -v`（**会删掉 MySQL/ES/Qdrant 全部数据**），再 `up -d` |

---

## 10. 常用命令速查

```powershell
cd "D:\AI RAG\pgx-rag\docker"

docker compose ps                  # 看状态
docker compose logs -f elasticsearch   # 跟随某个服务日志
docker compose stop                # 只停容器，保留数据卷
docker compose start               # 再启动
docker compose down                # 停并删除容器/网络，保留数据卷
docker compose down -v             # 连数据卷一起删（数据全没）
docker compose --profile embedding up -d   # 额外拉起 TEI
docker stats                       # 实时看各容器 CPU/内存
```
