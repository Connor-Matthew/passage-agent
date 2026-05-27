# AI 爆款文章创作器 ✍️

<div align="center">

**AI 爆款文章创作器**

基于多智能体协作，自动完成从选题、大纲、正文到配图的全流程图文创作

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D?style=flat-square&logo=vuedotjs&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)

</div>

## 🏗 项目简介

AI 爆款文章创作器是一个基于 **FastAPI** 构建的智能图文创作平台，通过 **5 个智能体协作** 完成从选题到图文文章的全自动创作，每个阶段都支持用户介入，实现人机协作的创作体验。

```
阶段1: 选题 → 生成 3-5 个标题方案 → 用户选择
阶段2: 标题 → 生成大纲 → 用户编辑 / AI 优化大纲
阶段3: 大纲 → 生成正文 → 分析配图需求 → 生成配图 → 图文合成
```

## 🎯 核心价值

| 特性 | 说明 | 价值 |
|------|------|------|
| 🤖 多智能体协作 | 5 个 Agent 分工协作 | 专业分工，质量更高 |
| 🎨 多元配图 | 6 种配图策略 + 自动降级 | 图文并茂，永不中断 |
| 📡 实时流式输出 | SSE 推送大纲/正文创作过程 | 所见即所得 |
| 🧑‍💻 人机协作 | 三阶段创作，每步可介入 | 创作可控 |
| 💎 VIP 会员体系 | Stripe 支付 + 配额管理 | 商业化就绪 |
| 🐳 Docker 一键部署 | docker compose up 即可运行 | 5 分钟上手 |

## ✨ 功能特性

### 智能体协作

| 智能体 | 功能 | 说明 |
|--------|------|------|
| Agent 1 | 标题生成 | 根据选题生成 3-5 个标题方案供用户选择 |
| Agent 2 | 大纲生成 | 根据标题生成文章大纲（流式输出） |
| Agent 3 | 正文生成 | 根据大纲生成 Markdown 正文（流式输出） |
| Agent 4 | 配图分析 | 分析正文内容，生成配图需求 |
| Agent 5 | 配图生成 | 获取图片并上传到 COS |
| 合成 | 合并图文 | 将配图插入正文生成完整图文 |

### 配图方式（策略模式）

系统采用策略模式实现多种配图方式，支持灵活扩展：

| 方式 | 说明 | 数据来源 | 权限 |
|------|------|---------|------|
| Pexels | 高质量图库检索 | 关键词检索 | 全部用户 |
| Mermaid | 流程图/架构图生成 | AI Prompt 生成 | 全部用户 |
| Iconify | 图标库检索 | 关键词检索 | 全部用户 |
| 表情包 | Bing 图片搜索 | 关键词检索 | 全部用户 |
| Nano Banana | Gemini AI 生图 | AI Prompt 生成 | VIP |
| SVG Diagram | AI 概念示意图 | AI Prompt 生成 | VIP |
| Picsum | 随机图片 | 降级方案 | 自动触发 |

> 当主配图方式失败时，系统会自动降级到 Picsum 随机图片，确保文章生成不中断。

### 文章风格

- 🔬 科技风格 - 专业严谨
- 💝 情感风格 - 温暖感人  
- 📚 教育风格 - 通俗易懂
- 😄 轻松幽默 - 诙谐有趣

## 🛠 技术栈

### 后端

| 技术 | 版本 | 说明 |
|------|------|------|
| FastAPI | 0.115 | Web 框架 |
| OpenAI SDK | 1.58 | AI 模型调用 |
| DashScope | - | 通义千问大模型 |
| SQLAlchemy | 2.0 | ORM 框架 |
| MySQL | 8.0 | 数据存储 |
| Redis | 5.2 | 缓存和会话 |
| Stripe | 14.3 | 支付集成 |
| 腾讯云 COS SDK | 1.9 | 对象存储 |
| Google Gen AI SDK | 1.35 | Gemini AI 生图 |

### 前端

| 技术 | 版本 | 说明 |
|------|------|------|
| Vue | 3.5 | 前端框架 |
| TypeScript | 5.8 | 类型安全 |
| Ant Design Vue | 4.2 | UI 组件库 |
| Vite | 7.0 | 构建工具 |
| Pinia | 3.0 | 状态管理 |
| Vue Router | 4.5 | 路由管理 |
| ECharts | 6.0 | 数据可视化 |
| Axios | 1.11 | HTTP 客户端 |

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- MySQL 8.0+
- Redis 7.x

### 1. 数据库初始化

```bash
mysql -uroot -p < sql/create_table.sql
```

### 2. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```yaml
# 必填配置
DASHSCOPE_API_KEY=your-dashscope-api-key
PEXELS_API_KEY=your-pexels-api-key

# 可选配置
STRIPE_API_KEY=sk_test_xxx  # 支付功能
TENCENT_COS_SECRET_ID=xxx   # 图片上传
```

### 3. 启动后端

```bash
cd python-backend
pip install uv
uv sync
uv run uvicorn app.main:app --reload
```

接口文档：http://localhost:8123/docs

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端页面：http://localhost:5173

## 🐳 Docker 一键部署（推荐）

### 前置条件

- Docker 20.10+
- Docker Compose v2+

### 快速启动

```bash
# 1. 复制环境变量配置文件
cp .env.example .env

# 2. 编辑 .env 文件，填写必需的 API Key
# 必须配置：DASHSCOPE_API_KEY 和 PEXELS_API_KEY
vim .env

# 3. 一键启动所有服务
docker compose up -d --build
```

### 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| 前端 | 80 | 访问地址：http://localhost |
| 后端 | 8123 | API 接口：http://localhost:8123 |
| 接口文档 | 8123 | http://localhost:8123/docs |
| MySQL | 不暴露 | 仅内部网络访问 |
| Redis | 不暴露 | 仅内部网络访问 |

### 常用命令

```bash
# 查看服务状态
docker compose ps

# 查看服务日志
docker compose logs -f backend    # 后端日志
docker compose logs -f frontend   # 前端日志

# 重启单个服务
docker compose restart backend

# 停止所有服务
docker compose down

# 停止并删除数据卷（清空数据）
docker compose down -v
```

## 📁 项目结构

```
├── python-backend/                # Python 后端
│   ├── app/
│   │   ├── agent/                 # 智能体模块
│   │   │   ├── agents/            # 各智能体实现
│   │   │   ├── context/           # 流式处理上下文
│   │   │   └── orchestrator.py    # 智能体编排器
│   │   ├── routers/               # API 路由
│   │   ├── services/              # 业务服务
│   │   ├── models/                # 数据模型
│   │   └── schemas/               # Pydantic Schema
│   ├── Dockerfile                 # 后端 Docker 配置
│   └── pyproject.toml             # Python 依赖
├── frontend/                      # 前端项目
│   ├── src/
│   │   ├── pages/                 # 页面组件
│   │   ├── components/            # 公共组件
│   │   ├── api/                   # API 接口
│   │   └── stores/                # 状态管理
│   └── Dockerfile                 # 前端 Docker 配置
├── sql/                           # 数据库脚本
│   ├── create_table.sql           # 建表语句
│   └── ...                        # 增量更新脚本
├── docker-compose.yml             # Docker 编排
└── .env.example                   # 环境变量示例
```

## 🔑 API Key 获取

| 服务 | 获取地址 | 说明 |
|------|---------|------|
| 通义千问 | https://bailian.console.aliyun.com | 必需 |
| Pexels | https://www.pexels.com/api/ | 必需 |
| Stripe | https://dashboard.stripe.com | 支付功能 |
| 腾讯云 COS | https://console.cloud.tencent.com | 图片上传 |
| Gemini | https://makersuite.google.com | AI 生图（VIP） |

## 🧪 测试账号

| 账号 | 密码 | 角色 |
|------|------|------|
| admin | 12345678 | 管理员 |
| user | 12345678 | 普通用户 |
| test | 12345678 | 测试账号 |

## 📖 相关文档

- [VIP 功能说明](VIP_FEATURES.md) - VIP 会员权益介绍
- [Stripe 支付配置](STRIPE_SETUP.md) - 支付功能配置指南

## 📄 License

MIT License
