# Findings & Decisions

## Requirements
- 将 run.py 的 8 阶段 pipeline 转为 Claude Code 插件
- claude -p 调用变为 subagent (Agent tool) 调用
- 主 agent 负责任务循环，通过 TodoTask 追踪进度
- 保留 PROGRESS.md 本地进度管理
- 保留 --force / 续写模式
- 循环模板按迭代模式生成 todo task

## Research Findings

### Claude Code 插件体系
- 插件结构: `.claude-plugin/plugin.json` + `skills/` + `commands/` + `agents/`
- SKILL.md = YAML frontmatter (name, description) + Markdown body (完整指令)
- Skill 通过 `Skill` tool 加载，内容注入对话上下文
- Agent tool 可派发 general-purpose subagent，自定义 prompt
- Slash command 在 `commands/*.md` 中定义，触发 skill

### 现有 run.py 映射到插件
| run.py 组件 | 插件对应 |
|------------|---------|
| `execute_claude_agent()` | Agent tool (general-purpose subagent) |
| `main()` 循环 + ProgressManager | 主 SKILL.md 指导 Claude 管理 TodoTask |
| 各 stage_xxx() 的 prompt | `prompts/*.md` 模板文件 |
| `PROGRESS.md` | 保留，主 skill 指导 Claude 用 Read/Edit 操作 |
| `check_api_health()` | 不需要 — Claude Code 自管理 |
| `--force` 参数 | slash command 参数或重新运行 |

### Subagent 调用模式
```python
# 旧模式 (run.py):
execute_claude_agent(prompt, context_files=["PRD.md"])

# 新模式 (SKILL.md 指导):
Agent(
  subagent_type="general-purpose",
  prompt="Read prompts/stage_architect.md, replace {IDEA} with user's idea. Execute the task."
)
```

### 任务循环设计
```
主 Skill 流程:
1. 读取 PROGRESS.md (或创建新的)
2. 解析已完成的阶段
3. 对每个 pending 阶段:
   a. TaskCreate 创建任务
   b. TaskUpdate 标记 in_progress
   c. Agent tool 派发 subagent (读取对应 prompt 模板)
   d. subagent 完成后:
      - TaskUpdate 标记 completed
      - Edit 更新 PROGRESS.md
4. Stage 2 完成后，读取 architecture.json，动态展开模块任务
```

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 纯 skills-based 插件 | 不需要 MCP server，纯指令注入即可 |
| prompt 模板存为 .md | subagent 可以用 Read 读取，变量替换由主 skill 指导 |
| 主 skill 不写 Python | 整个插件是 markdown 文件集合，Claude 作为执行引擎 |
| 复用 PROGRESS.md 格式 | 已验证可用，且人可编辑 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Stage 3 模块数量动态 | 主 skill 指导 Claude 在 Stage 2 后读取 architecture.json，动态生成 TodoTask |

## Resources
- 插件示例: ~/.claude/plugins/cache/superpowers-marketplace/superpowers/4.1.0/
- 最小插件: ~/.claude/plugins/cache/zai-coding-plugins/glm-plan-usage/0.0.1/
- 当前 run.py: ./run.py
