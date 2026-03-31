# CLAUDE.md

This file provides guidance to Claude Code when working with the DeerFlow project.

## Project Overview

**DeerFlow** (Deep Exploration and Efficient Research Flow) is ByteDance 开源的 AI Super Agent 框架，v2.0 是完全重写版本。基于 LangGraph 构建，支持子代理编排、沙箱执行、持久记忆、MCP 集成和可扩展技能系统。

## Architecture

```
用户 → Nginx (:2026) → Frontend (:3000) / Gateway API (:8001) / LangGraph Server (:2024)
```

| 服务 | 端口 | 说明 |
|------|------|------|
| **Nginx** | 2026 | 统一入口反向代理 |
| **Frontend** | 3000 | Next.js 16 + React 19 Web 界面 |
| **Gateway API** | 8001 | FastAPI REST API（模型、MCP、技能、内存、上传等） |
| **LangGraph Server** | 2024 | Agent 运行时和工作流引擎 |
| **Provisioner** | 8002 | 可选，Docker/K8s sandbox 模式 |

### 项目结构

```
deer-flow/
├── Makefile                 # 根级命令 (check, install, dev, stop)
├── config.yaml              # 主配置文件 (从 config.example.yaml 复制)
├── extensions_config.json   # MCP 服务器和技能配置
├── backend/                 # Python 后端
│   ├── packages/harness/    # deerflow-harness 核心框架包 (import: deerflow.*)
│   │   └── deerflow/
│   │       ├── agents/      # LangGraph agent 系统 (lead_agent + 12 个中间件)
│   │       ├── sandbox/     # 沙箱执行系统 (本地/Docker)
│   │       ├── subagents/   # 子代理委派系统
│   │       ├── tools/       # 内建工具
│   │       ├── mcp/         # MCP 集成
│   │       ├── models/      # 模型工厂 (thinking/vision 支持)
│   │       ├── skills/      # 技能发现和加载
│   │       ├── community/   # 社区工具 (tavily, jina, firecrawl)
│   │       └── config/      # 配置系统
│   ├── app/                 # 应用层 (import: app.*)
│   │   ├── gateway/         # FastAPI Gateway API
│   │   └── channels/        # IM 集成 (飞书/Slack/Telegram)
│   └── tests/               # 测试套件
├── frontend/                # Next.js 前端
│   └── src/
│       ├── app/             # App Router 路由
│       ├── components/      # React 组件 (ui/ workspace/ landing/)
│       └── core/            # 业务逻辑 (threads/ api/ artifacts/ i18n/)
└── skills/                  # Agent 技能目录
    ├── public/              # 公共技能 (已提交)
    └── custom/              # 自定义技能 (gitignored)
```

### Harness / App 分层

- **Harness** (`packages/harness/deerflow/`): 可发布的 agent 框架包，`import deerflow.*`
- **App** (`app/`): 应用层代码，`import app.*`
- **依赖规则**: App 可以导入 deerflow，但 deerflow 绝不导入 app（CI 强制检查）

## Tech Stack

**后端**: Python 3.12+, LangGraph, FastAPI, uv (包管理), ruff (lint/format)
**前端**: Next.js 16, React 19, TypeScript 5.8, Tailwind CSS 4, pnpm 10.26.2, Shadcn UI, TanStack Query
**基础设施**: Nginx, Docker (可选沙箱)

## Commands

### 全应用（根目录执行）

```bash
make config       # 生成本地配置文件
make check        # 检查系统依赖
make install      # 安装所有依赖 (前端 + 后端)
make dev          # 启动所有服务 (开发模式，热重载)
make stop         # 停止所有服务
make up           # Docker 生产模式启动
make down         # Docker 停止
```

### 后端（backend/ 目录）

```bash
make install      # 安装后端依赖
make dev          # LangGraph server (:2024)
make gateway      # Gateway API (:8001)
make test         # 运行所有测试
make lint         # ruff lint
make format       # ruff format
```

### 前端（frontend/ 目录）

```bash
pnpm install      # 安装依赖
pnpm dev          # 开发服务器 (:3000, Turbopack)
pnpm build        # 生产构建
pnpm check        # ESLint + TypeScript 类型检查
pnpm lint:fix     # ESLint 自动修复
```

## Configuration

1. `make config` 从 `config.example.yaml` 生成 `config.yaml`
2. 在 `config.yaml` 中配置至少一个模型（支持 OpenAI/Anthropic/DeepSeek/Doubao 等）
3. 在 `.env` 或环境变量中设置 API Key（如 `OPENAI_API_KEY`, `TAVILY_API_KEY`）
4. MCP 服务器和技能在 `extensions_config.json` 中配置

配置值以 `$` 开头会被解析为环境变量，如 `api_key: $OPENAI_API_KEY`。

## Development Guidelines

- **TDD 强制**: 每个新功能或 bug 修复必须附带单元测试
- **文档同步**: 代码变更后更新相关 README.md 和 CLAUDE.md
- **后端代码风格**: ruff, 240 字符行宽, Python 3.12+ 类型注解, 双引号
- **前端代码风格**: ESLint + Prettier, import 排序（内置→外部→内部）, `cn()` 处理 Tailwind 类名, `@/*` 路径别名
- **前端组件**: `ui/` 和 `ai-elements/` 是自动生成的，不要手动编辑

## Opus + Codex 协作工作流

本项目采用 **Claude Opus 编码 + Codex Review** 的双模型协作模式，职责严格分离。

### 角色分工

| 阶段 | 执行者 | 职责 |
|------|--------|------|
| 设计 | Claude Opus | 分析需求 → 设计方案 → 写实现计划 |
| 编码 | Claude Opus | 按计划写代码 + 测试 |
| Review | Codex | 用标准提示词独立审查变更 |
| 修复 | Claude Opus | 根据 Codex 反馈修复问题 |
| 验证 | Codex | 二次确认修复正确性 |

### Codex Review 标准提示词

当调用 Codex MCP 做代码审查时，**必须**使用以下提示词模板：

```
You are an independent code reviewer. Another AI wrote this code.
Your ONLY job: find bugs, logic errors, and security issues.

Review checklist:
1. Logic correctness — is the control flow right?
2. Edge cases — null, empty, overflow, concurrent access?
3. Security — injection, XSS, auth bypass, secrets leak?
4. Requirements match — does it do what was asked?

STRICT RULES:
- Do NOT suggest refactoring, renaming, or style changes
- Do NOT add comments, docstrings, or type annotations
- Do NOT propose "improvements" or "better approaches"
- ONLY report: bugs, logic errors, security vulnerabilities
- If no issues found, say "LGTM — no bugs found"

Output format per issue:
[SEVERITY: critical/high/medium] file:line — description
```

### 调用方式

通过 Codex MCP 工具调用，使用 `approval-policy: "never"` 实现自动执行：

```
mcp__codex__codex(
  prompt: "<标准提示词>\n\n<待审查的代码或 diff>",
  approval-policy: "never"
)
```

### 重要约束

- **最后一行规则最重要**：不加"只报告 bug"约束，Codex 会把审查当重构做
- Codex 报告的问题由 Claude Opus 负责修复，修复后可再次提交 Codex 验证
- Review 范围应聚焦于本次变更的 diff，而非全量代码

## Key Concepts

- **Lead Agent**: 主代理入口，通过中间件链处理请求
- **ThreadState**: 扩展的 Agent 状态，包含 sandbox、artifacts、todos 等
- **Sandbox**: 虚拟路径系统 `/mnt/user-data/{workspace,uploads,outputs}`
- **Subagents**: 最多 3 个并发子代理，15 分钟超时
- **Memory**: 自动提取事实和上下文，注入系统提示词
- **Skills**: `skills/{public,custom}/` 下的 `SKILL.md` 文件定义技能
- **MCP**: 多服务器管理，支持 stdio/SSE/HTTP，延迟初始化 + mtime 缓存失效
