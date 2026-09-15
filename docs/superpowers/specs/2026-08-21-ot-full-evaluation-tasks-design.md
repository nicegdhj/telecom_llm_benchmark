# OT-Full 评测任务设计

日期：2026-08-21
状态：已确认

## 1. 目标

基于 `data/ot-full` 下的 8 个子目录，为每个数据集新增一个可由 ais_bench 独立执行的评测任务。任务名严格使用 `ot_<子目录名>`，原始 JSONL 文件保持不变，不生成重复数据副本。

## 2. 任务清单

| 任务名 | 数据路径 | 条数 | 题型 | 评估器 |
|---|---|---:|---|---|
| `ot_3gpp_tsg` | `data/ot-full/3gpp_tsg/test-00000-of-00001.jsonl` | 2000 | 3GPP 工作组固定标签分类 | `JsonFieldEvaluator` |
| `ot_oranbench` | `data/ot-full/oranbench/test-00000-of-00001.jsonl` | 1500 | 四选一 | `AccEvaluator` |
| `ot_sixg_bench` | `data/ot-full/sixg_bench/test-00000-of-00001.jsonl` | 3722 | 四选一 | `AccEvaluator` |
| `ot_srsranbench` | `data/ot-full/srsranbench/test-00000-of-00001.jsonl` | 1502 | 四选一 | `AccEvaluator` |
| `ot_telelogs` | `data/ot-full/telelogs/test-00000-of-00001.jsonl` | 864 | C1-C8 根因分类 | `AccEvaluator` |
| `ot_telemath` | `data/ot-full/telemath/test-00000-of-00001.jsonl` | 500 | 数值计算 | `MATHEvaluator` |
| `ot_teleqna` | `data/ot-full/teleqna/test-00000-of-00001.jsonl` | 10000 | 二至五选一 | `AccEvaluator` |
| `ot_teletables` | `data/ot-full/teletables/test-00000-of-00001.jsonl` | 500 | 五选一 | `AccEvaluator` |

总计 20588 条。

## 3. 数据适配

新增一个通用 `OTDataset`，直接读取指定 JSONL，并通过配置参数选择以下模式：

- `mcq`：读取 `question`、`choices`、`answer`；将选项依次格式化为 `A.` 至 `E.`，将从 0 开始的答案索引转换为对应选项字母。
- `json_label`：读取 `question`、`answer`；将标签答案转换为 `{"WORKING GROUP": "<标签>"}`，用于 3GPP 工作组字段级精确判分。
- `plain`：读取 `question`、`answer`；保留问题文本，并将答案转换为字符串，供 TeleLogs 和 TeleMath 使用。

适配后的统一字段为 `input` 和 `output`。附加元数据字段不参与推理和判分，但原始文件不会被修改。

加载时校验每行 JSON、必填字段、选项列表、答案索引类型及范围。失败信息必须包含数据文件和 1-based 行号，便于定位坏数据。

## 4. 推理提示词与答案解析

### 4.1 选择题

`ot_oranbench`、`ot_sixg_bench`、`ot_srsranbench`、`ot_teleqna`、`ot_teletables` 使用统一选择题提示词，要求模型只输出一个选项字母。推理结果通过现有 `first_option_postprocess` 提取 `A-E`，再由 `AccEvaluator` 与标准答案比较。

### 4.2 3GPP 工作组分类

`ot_3gpp_tsg` 保留原问题中限定的工作组列表与 JSON 输出要求。`JsonFieldEvaluator` 只比较 `WORKING GROUP` 字段，采用精确匹配和严格模式；模型附带额外说明但能解析出 JSON 时仍按字段值判分。

### 4.3 TeleLogs

`ot_telelogs` 保留原问题内容和 `\boxed{}` 输出要求。新增最小文本后处理器，将 `C1`、`\boxed{C1}`、`\boxed{1}`、`答案：C1` 等输出统一为 `C1-C8`；无法唯一解析时返回空字符串并判错。

### 4.4 TeleMath

`ot_telemath` 在问题末尾追加逐步推理和最终答案放入 `\boxed{}` 的要求。使用现有 `MATHEvaluator`：优先判断数学表达式等价性，数值兜底采用绝对误差小于 `1e-3`。

## 5. 配置组织

在 `ais_bench/benchmark/configs/datasets/ot_full/` 下新增 8 个独立配置文件：

- `ot_3gpp_tsg.py`
- `ot_oranbench.py`
- `ot_sixg_bench.py`
- `ot_srsranbench.py`
- `ot_telelogs.py`
- `ot_telemath.py`
- `ot_teleqna.py`
- `ot_teletables.py`

每个文件只导出本任务对应的 `*_datasets` 列表，配置中的 `abbr` 与任务名一致。执行示例：

```bash
ais_bench --models maas --datasets ot_3gpp_tsg
```

本次不修改平台任务目录、现有运行脚本、原始数据和其他任务配置。

## 6. 测试与验收

自动化测试覆盖：

1. 8 个原始数据文件均能由 `OTDataset` 完整加载，条数与任务清单一致。
2. `mcq` 模式正确生成动态选项文本，并把 0-based 索引转换为 `A-E`。
3. `json_label` 模式正确生成 `WORKING GROUP` 标准答案 JSON。
4. `plain` 模式正确保留 TeleLogs 标签和 TeleMath 数值答案。
5. TeleLogs 后处理器兼容约定的四类输出形式，并拒绝无效或多义答案。
6. 8 个配置文件均可导入，任务名、路径、数据模式和评估器与设计矩阵一致。
7. 执行相关单元测试和配置加载检查，最终运行 `git diff --check`。

验收标准：不调用线上模型即可证明全部任务可被发现、数据可加载、标准答案可正确构造、评估器配置无误。
