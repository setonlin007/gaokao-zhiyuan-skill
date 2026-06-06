# lib/ — 确定性逻辑(L1)

无 LLM 参与的纯计算，保证数字不被幻觉污染。**Python 标准库实现，零外部依赖。**
原则：输入硬数据 → 输出分档结果；LLM 只在下游(L3)把结果翻译成人话。

## 模块

| 文件 | 职责 | 对应 DESIGN |
|---|---|---|
| `config.py` | 冲稳保阈值 / 配额 / 大小年阈值（集中可调） | §5 注 |
| `data_loader.py` | 读 `data/` 的 CSV/JSON，转类型、丢脏行 | §8 / SCHEMAS |
| `stage.py` | **P0 阶段判定**：今天日期 + 时间线.json → 考前/考中/考后各子阶段 | §3 |
| `rank.py` | 位次换算：一分一段表把分数→位次（就近不高于兜底） | §5 步骤2 |
| `subject_filter.py` | **选科硬过滤（第一过滤器）**：选科不匹配先剔除 | §5 步骤1 |
| `chongwenbao.py` | 多年均值分档 + 招生计划修正 + 梯度配额 + 调剂提示 + 城市/民办过滤 | §5 步骤3-9 |
| `selfcheck.py` | 用合成样例数据跑通全链路，验证逻辑（无网络、无 LLM） | — |

## Q1 调用顺序（务必照此序）

```
P0 stage.detect_stage          # 先判阶段，决定分数口径与是否产清单
→ rank.score_to_rank           # 分数→位次（已是位次则跳过）
→ subject_filter.filter_eligible   # 【第一硬过滤】选科不匹配先剔除
→ chongwenbao.rank_candidates  # 多年均值分档 + 计划修正 + 配额 + 调剂提示
```

## 设计纪律

- 全程不生成数字，只查表/算术；**绝不输出"录取概率 X%"**（伪精确=幻觉）。
- 分档基准是**近3年位次均值**，不是单年最低位次（抗大小年）。
- 新高考省投档单位必须是**专业组/专业类**粒度（粒度由时间线.json 声明）。

## 运行自测

```bash
python3 /Users/setonlin/my-workspace/private/money/gaokao-zhiyuan-skill/lib/selfcheck.py
```

样例数据在 `_selfcheck_data/`，**全为合成、`source_url=SAMPLE`**，仅供验证逻辑，绝不可当真实数据使用（守铁律一）。
