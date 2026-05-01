# Task Plan: 将 Auto_Claude_CLI 转为 Claude Code Plugin

## Goal
将 run.py 中的 Python subprocess + claude -p 调用模式，重构成 Claude Code 技能插件：主 agent 通过 TaskCreate 管理任务循环，每个阶段派发 subagent (Agent tool) 执行实际工作，保留 PROGRESS.md 进度管理。

## Current Phase
Phase 5

## Phases

### Phase 1: 需求分析与架构设计
- **Status:** complete

### Phase 2: 创建插件骨架
- **Status:** complete

### Phase 3: 实现主 Skill (任务循环)
- [x] 重写 SKILL.md — 所有 prompt 内联，自包含，无外部文件依赖
- [x] 精确定义 dispatch protocol: TaskCreate → Edit PROGRESS → Agent tool → TaskUpdate → Edit PROGRESS
- [x] 每个阶段的 subagent prompt 内联在 SKILL.md 中 (blockquote 格式)
- [x] prompt 模板文件同步更新为 reference copies
- **Status:** complete

### Phase 4: Stage 3 动态模块展开
- [x] STEP 3 (Expand Development Tasks) — 完整定义在 SKILL.md 中
- [x] Resume 场景：扫描已有 module 行，保留 [x] 状态和时间戳
- [x] completed_modules 列表从 PROGRESS.md 重建
- [x] 与现有 PROGRESS.md checkbox 格式兼容
- **Status:** complete

### Phase 5: 测试与验证
- [ ] 手动测试完整 pipeline：`/build "写一个 hello world CLI"`
- [ ] 测试断点续写：中断后 `/build` 继续
- [ ] 测试 --force 模式
- **Status:** pending

## Key Questions
1. subagent 的 prompt 模板文件放在哪里？→ skills/auto-factory/prompts/ 目录下
2. 主 skill 如何控制循环？→ 指导 Claude 用 TaskCreate/TaskUpdate + Agent tool 逐阶段执行
3. PROGRESS.md 的读写谁负责？→ 主 skill 指导 Claude 直接用 Read/Edit 工具操作
4. 插件安装方式？→ 发布到 GitHub marketplace 或本地安装

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 技能插件而非 MCP 插件 | 纯 instruction-based，不需要额外服务进程 |
| prompt 内联在 SKILL.md | 消除文件路径依赖，subagent 直接拿到完整 prompt |
| 保留 PROGRESS.md 格式 | 已有格式完善，且人可编辑 |
| Agent tool general-purpose 类型 | 灵活度最高，可自定义完整 prompt |
| prompt 模板文件仅作 reference | prompts/*.md 是文档参考，SKILL.md 是执行源 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       | 1       |            |

## Notes
- 核心变化：Python subprocess(`claude -p`) → Claude Code Agent tool(subagent)
- 不再需要 check_api_health() — Claude Code 自身管理 API 连接
- 不再需要 countdown() — 限流由 Claude Code 处理
- 插件是纯 markdown 文件集合，零 Python 代码
