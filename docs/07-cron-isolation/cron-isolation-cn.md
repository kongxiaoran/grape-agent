# Cron 与隔离执行（概念 / 原理 / 实现）

## 概念

Cron 模块用于周期任务执行，并把结果投递到指定通道。

## 原理

- 任务定义持久化到 store
- scheduler 轮询到期任务并分配执行
- 任务支持两种会话策略：`isolated`（每次新 session/workspace）与 `sticky`（复用同一任务会话）

## 实现

核心文件：

- `grape_agent/cron/models.py`
- `grape_agent/cron/store.py`
- `grape_agent/cron/scheduler.py`
- `grape_agent/cron/executor.py`
- `grape_agent/cron/delivery.py`

关键点：

- 并发数限制 `max_concurrency`
- 默认超时 `default_timeout_sec`
- 通道回投递由 `CronDelivery` 统一处理

## 验证

1. 开启 `cron.enabled=true`
2. 新建短周期任务
3. 验证任务执行结果和通道投递日志

## 代码行号引用

- Cron 配置项（并发、轮询、默认超时）  
  `grape_agent/config.py:198`, `grape_agent/config.py:203`, `grape_agent/config.py:205`
- 调度器轮询与并发信号量  
  `grape_agent/cron/scheduler.py:16`, `grape_agent/cron/scheduler.py:31`, `grape_agent/cron/scheduler.py:71`
- 执行器会话策略（`sticky`/`isolated`）与超时控制  
  `grape_agent/cron/executor.py:16`, `grape_agent/cron/executor.py:47`, `grape_agent/cron/executor.py:77`
- 结果回投递到通道  
  `grape_agent/cron/delivery.py:10`, `grape_agent/cron/delivery.py:16`, `grape_agent/cron/delivery.py:32`
- Gateway 的 `cron.*` 方法入口  
  `grape_agent/gateway/handlers/cron.py:8`, `grape_agent/gateway/handlers/cron.py:24`, `grape_agent/gateway/handlers/cron.py:66`
