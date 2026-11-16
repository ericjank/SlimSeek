# SlimSeek（轻索）

一个轻量级、可自托管的 RAG 知识检索系统。导入 PDF、TXT 或 Markdown 文档后，SlimSeek 会建立本地持久化向量索引，通过 OpenAI 兼容 API 或 Ollama 生成基于原文、带来源引用的答案。

## English Description

SlimSeek is a lightweight, self-hosted RAG knowledge retrieval system for PDF, TXT, and Markdown documents. It combines persistent SQLite vector search with OpenAI-compatible APIs or Ollama to deliver grounded answers with source citations through a simple web interface.

## 功能特性

- **文档管理**：上传、查看和删除 PDF、TXT、Markdown 文档，支持重复文件检测。
- **本地向量索引**：使用 SQLite 与 sqlite-vec 持久化文档、文本块和向量，无需独立数据库。
- **双模型接入**：支持 OpenAI 兼容的嵌入与聊天接口，以及 Ollama 本地模型。
- **可信回答**：Top-K 相似度检索、基于上下文生成答案，并展示文档名、页码或块序号、原文片段和相关度。
- **轻量 Web 界面**：使用原生 HTML、CSS 和 JavaScript，无需 Node.js 构建。
- **配置保护**：检测嵌入模型或向量维度变化，避免混用不兼容的索引。
- **异常处理**：覆盖空文件、损坏 PDF、重复上传、模型服务中断和空查询等情况。

## 技术栈

- Python 3.12、uv
- FastAPI、Uvicorn、HTTPX
- SQLite、sqlite-vec
- pypdf
- 原生 HTML、CSS、JavaScript

## 快速开始

### 环境要求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- 一个可用的 OpenAI 兼容服务，或已安装并运行的 [Ollama](https://ollama.com/)

### 安装

```bash
uv sync
cp .env.example .env
```

`.env` 用于保存本地配置和密钥，已被 Git 忽略，不会提交到仓库。

### 方式一：OpenAI 兼容 API

编辑 `.env`：

```dotenv
SLIMSEEK_PROVIDER=openai
SLIMSEEK_OPENAI_BASE_URL=https://api.openai.com/v1
SLIMSEEK_OPENAI_API_KEY=your-api-key
SLIMSEEK_OPENAI_EMBEDDING_MODEL=text-embedding-3-small
SLIMSEEK_OPENAI_CHAT_MODEL=gpt-4o-mini
```

Base URL 应包含兼容服务所需的版本前缀，例如 `/v1`。然后启动：

```bash
uv run slimseek
```

### 方式二：Ollama

准备默认模型：

```bash
ollama pull nomic-embed-text
ollama pull qwen2.5:3b
```

编辑 `.env`：

```dotenv
SLIMSEEK_PROVIDER=ollama
SLIMSEEK_OLLAMA_BASE_URL=http://127.0.0.1:11434
SLIMSEEK_OLLAMA_EMBEDDING_MODEL=nomic-embed-text
SLIMSEEK_OLLAMA_CHAT_MODEL=qwen2.5:3b
```

也可以直接使用已安装的模型，例如：

```bash
SLIMSEEK_PROVIDER=ollama \
SLIMSEEK_OLLAMA_EMBEDDING_MODEL=qwen3-embedding:8b \
SLIMSEEK_OLLAMA_CHAT_MODEL=qwen2.5vl:7b \
uv run slimseek
```

启动后访问 <http://127.0.0.1:8000>，API 文档位于 <http://127.0.0.1:8000/docs>。

## 配置项

所有配置均使用 `SLIMSEEK_` 前缀。常用配置如下：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SLIMSEEK_PROVIDER` | `openai` | 模型提供方：`openai` 或 `ollama` |
| `SLIMSEEK_DATA_DIR` | `data` | 数据库和原始文档保存目录 |
| `SLIMSEEK_HOST` | `127.0.0.1` | 服务监听地址 |
| `SLIMSEEK_PORT` | `8000` | 服务端口 |
| `SLIMSEEK_UPLOAD_MAX_MB` | `20` | 单个上传文件大小上限 |
| `SLIMSEEK_REQUEST_TIMEOUT_SECONDS` | `120` | 模型请求超时时间 |
| `SLIMSEEK_CHUNK_SIZE` | `900` | 文本块目标字符数 |
| `SLIMSEEK_CHUNK_OVERLAP` | `150` | 相邻文本块重叠字符数 |
| `SLIMSEEK_CONTEXT_MAX_CHARS` | `12000` | 发送给生成模型的上下文长度上限 |

完整模型配置示例见 `.env.example`。

## API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 查看服务、模型配置和文档数量 |
| `GET` | `/api/documents` | 获取文档列表 |
| `POST` | `/api/documents` | 使用 multipart/form-data 上传并索引文档 |
| `DELETE` | `/api/documents/{id}` | 删除文档及其索引 |
| `POST` | `/api/query` | 检索并生成带引用的答案 |

查询示例：

```bash
curl -X POST http://127.0.0.1:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"这个项目支持哪些文档格式？","top_k":5}'
```

## 数据与索引

运行数据默认保存在 `data/`：

- `data/slimseek.db`：文档元数据、文本块和向量索引。
- `data/uploads/`：上传的原始文件。

该目录已被 Git 忽略。切换嵌入 provider、嵌入模型或向量维度后，已有索引不能继续使用；请换用新的数据目录，或删除全部文档后重新导入。删除全部文档会重置向量索引配置。

## 项目结构

```text
.
├── pyproject.toml
├── .env.example
└── src/slimseek/
    ├── api.py          # FastAPI 路由与应用入口
    ├── cli.py          # slimseek 启动命令
    ├── config.py       # 环境变量与服务配置
    ├── documents.py    # 文档解析与分块
    ├── providers.py    # OpenAI 兼容 API 与 Ollama
    ├── service.py      # 导入、检索、回答与引用编排
    ├── storage.py      # SQLite 持久化与向量检索
    └── static/         # Web 界面
```

## 开发检查

```bash
uv run python -m compileall -q src
node --check src/slimseek/static/app.js
```

Node.js 仅用于上述 JavaScript 语法检查，运行项目不需要 Node.js。

## 当前边界

首版面向本地单用户和中小规模知识库，不提供用户认证、多租户、OCR、知识图谱、rerank 或异步导入队列。若需暴露到公网，请自行增加认证、访问控制和反向代理安全配置。
