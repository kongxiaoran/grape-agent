# 仓库结构治理策略

## 目录分层原则

- `grape_agent/`: 产品源码
- `tests/`: 单元与集成测试
- `docs/`: 面向学习与实现的技术文档
- `examples/`: 教学示例
- `scripts/`: 环境初始化与辅助脚本

## 非源码产物策略

下列内容不应作为开源主线结构的一部分：

- 本地产物：`build/`, `*.egg-info`, `.DS_Store`
- 运行时数据：`logs/`, `workspace/`, `workspace-reviewer/`
- 本地虚拟环境：`.venv/`

建议：通过 `.gitignore` 与发布流程确保这些目录不进入发布版本。

## 文档治理原则

- 所有长期文档必须在 `docs/README.md` 可导航
- 同主题仅保留 1 份主文档，旧版本放 `docs/archive/`
- 每篇模块文档使用统一结构：概念 / 原理 / 实现 / 验证

## 推荐后续整理动作

1. 清理根目录历史散落文档（如早期临时总结文件）
2. 收敛 `operations` 与 `deploy` 重复内容
3. 设立“文档变更必更新索引”的 PR 规则

## 代码行号引用

- 源码主目录（运行入口）：`grape_agent/cli.py:1302`
- 配置与目录搜索策略：`grape_agent/config.py:666`, `grape_agent/config.py:704`
