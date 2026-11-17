# CHANGELOG — 变更记录

> 按时间倒序。只记录实际发生的操作，不把文档完成写成软件功能完成。

## 2026-11-17（S08 执行，CodeBuddy；用户「S07验收通过，继续」后启动，状态 S08_DONE_PENDING_ACCEPTANCE）

S07 验收通过后先提交 `4b659ed` 并建 tag **`s07-accepted`**，备份正式库（`11_BACKUPS/s08_pre_run_20261117/`，SHA-256 `245790CF…36D701C`），再执行 S08 五站 GPS 空间与动态分析；停在 S08 等验收，未开始 S09。

- **GPS 与站距**（`0010_s08_spatial.sql` / `spatial.py`）：`station_location` 版本化记录坐标系/精度/水深/朝向/来源/有效期，`station_distance` 记录距离/方法/坐标系状态；网页可编辑，历史不覆盖；只接入用户提供的 2000/2001 两台坐标，**P1—P5 不自动分配**，其余三台保持 UNKNOWN。
- **坐标审计与离线地图**：范围、坐标系声明、疑似颠倒、同点重复均只提示不改写；跨坐标系拒绝混算。真实两台坐标系未声明，站距按 WGS84 近似给 **157.809 m（PROVISIONAL）**，不作正式站距；只做离线坐标示意，无在线底图/投影/鱼群轨迹/密度插值。
- **覆盖与比较**：2000 用当日生效参数给 CIRCLE_ONLY、R=5.2 m；2001 缺参数保持 UNKNOWN；两台朝向缺，方向足迹 UNKNOWN。输出每日五站活动、日期×站位、昼夜×站位、三水层×站位、周/月变化；缺站缺测 NA 不填 0。
- **统计与环境**：同期/领先 1 日相关只称关联；真实 2000/2001 只有 1 个共同有效日，所有对为 INSUFFICIENT_DATA，稳定度 INSUFFICIENT_DATA。水温/潮汐/风向 BLOCKED，风速 PROVISIONAL 且站间比较 BLOCKED（共享来源）。
- **动态与入口**：`/s08` 提供日期/时间滑块、播放暂停、步进、倍速、单站/五站、环境同步与固定色标；离散帧无轨迹无插值；`scripts/s08_spatial.py` 六个子命令；新增 8 项测试，**223 passed**；21 个原始 CSV 哈希 21/21 不变。
- **修复**：环境源字段名 `source_kind`→`kind`、环境 UTC→本地小时对齐、单窗口稳定度伪 1.0、未声明坐标系混算、CLI `frames` 缺 `--date` 五项已修正并用真实库复跑。
- **未动**：21 个原始 CSV、V4 包、S07 既有断言；未开始 S09。

## 2026-11-17（S07 执行，CodeBuddy；用户「S06验收通过，继续」后启动，状态 S07_DONE_PENDING_ACCEPTANCE）

S06 验收通过后先提交 `62bff10` 并建 tag **`s06-accepted`**，备份正式库（`11_BACKUPS/s07_pre_run_20261117/`，SHA-256 `008B216E…D0981C6D`），再执行 S07 深度/人工底界/三水层/长期规律；停在 S07 等验收，未开始 S08。

- **按日期参数与几何**（`beam_geometry.py`）：`effective_params()` 按生效区间取当日参数版本；2000 条件算例（3.68 m / 45° / 全角 15° / R=5.2）中心轴底距 5.204306、较陡/较平边缘 4.638538/6.045061、椭圆与面积、裁底体积 2.353045、最远前向 4.125174 全部落在规范容差内；R 始终锁定 5.2，理论值不覆盖。
- **底界与分层**（`s07_depth.py`）：近底候选只在 `build_mask` 保留样本上标记，人工底界 `NOT_DETECTED` → 2,691,290 候选 `PENDING_REVIEW`、额外排除 0；三水层按离底高度 \(z=h-r\sin\alpha\) 划分，2000/10-31 三层样本 3,123,324/9,031,692/8,650,575 合计 20,805,591，与 S03 逐样本相等。
- **规律与数据集**（`s07_patterns.py` / `s07_datasets.py`）：L0—L3 证据等级不按天数自动升级；真实 4 日结果 L1（峰时稳定度 0.25、曲线相关 0.13、昼夜一致度 0.80）；第一阶段实际边界 2026-10-31—11-03、正式同步时间 NULL，补录 7 个 run 后冻结，版本 v5、5 个版本留痕。
- **入口与测试**：`/s07` 网页与 `scripts/s07_pipeline.py` 四个子命令；新增 11 项测试，**215 passed**；21 个原始 CSV 哈希 21/21 不变。
- **修复**：单日设备被误计为峰值高稳定、趋势方向与秩相关不一致、首次冻结缺 run 关联/初始版本三项均已留存旧版本并修正。
- **未动**：21 个原始 CSV、V4 包、S06 既有断言；未开始 S08。

## 2026-11-17（S06 验收与提交，CodeBuddy）

用户确认 S06 验收完毕；提交 S06 全部代码/证据/文档（`62bff10`）并建 tag `s06-accepted`，随后启动 S07。S06 报告结论不变：`STAGE_S06.md`、204 passed、480 个真实 15 分钟格与天文 PROVISIONAL 标记。

## 2026-11-17（S06 执行，CodeBuddy；用户「S05验收通过，继续」后启动，状态 S06_DONE_PENDING_ACCEPTANCE）

S05 验收通过后先提交 `6a9bfbc` 并建 tag **`s05-accepted`**，备份正式库（`11_BACKUPS/s06_pre_run_20261117/`，SHA-256 `8D3964CC…FFA`），再执行 S06 日内/昼夜/晨昏；停在 S06 等验收，未开始 S07。

- **统一基础格**（`0008_s06_intraday.sql` + `services/intraday.py`）：从 S03 原始文件哈希与同一硬掩码生成 15 分钟格（一天 96 格），60/120 分钟与热图均由此聚合；低覆盖标 NA，不跨缺口插值；同哈希幂等，`--overwrite-grids` 才重算。
- **日内与典型日**：24 小时曲线、15 分钟热图、2 小时分组、逐日峰谷与“早高—中低—再升”形态；典型日先逐日按有效暴露规范化再跨日等权，至少 3 个有效日，2001 单日全部 `INSUFFICIENT_DAYS`。
- **昼夜晨昏**：NOAA 日出日落（90.833°）与民用晨昏（96°）、日出日落前后 ±120 分钟窗；夜间以夜开始日期锚定，跨午夜不重不漏。**两台真实 GPS 坐标系未声明，天文结果一律 PROVISIONAL**，无坐标则 BLOCKED。
- **环境关联**：日内 lag=0 探索性相关（有效样本、Fisher CI、Holm），真实风速 120 对 r=−0.097、Holm p=0.512，不给出关联结论；水温代理不进入解释变量。
- **真实产物**：`S06-DDC45D6F9491`，480 个 15 分钟格；2000 四日典型日 06 时 825 次/有效小时；2000 的 10-31/11-02/11-03 检出早晚双峰形态，11-01 与 2001 不强行识别；原始 CSV 21/21 哈希不变。
- **修复**：覆盖率把秒位清零导致低估（已重建全部真实格）、空时间戳行导致整天失败、峰谷比例阈值误用锚点钟点三项。新增 8 项测试，**204 passed**。
- **未动**：21 个原始 CSV、V4 包、S05 既有断言；未开始 S07。

## 2026-11-17（S05 验收与提交，CodeBuddy）

用户确认 S05 验收完毕；提交 S05 全部代码/证据/文档（`6a9bfbc`）并建 tag `s05-accepted`，随后启动 S06。S05 报告结论不变：`STAGE_S05.md`、196 passed、风速 288 行导入与 BLOCKED 项诚实留痕。

## 2026-11-17（S05 执行，CodeBuddy；用户「验收通过，继续」后启动，状态 S05_DONE_PENDING_ACCEPTANCE）

S04 验收通过后先提交 `1658a38` 并建 tag **`s04-accepted`**，备份正式库（`11_BACKUPS/s05_pre_run_20261117/`，SHA-256 `7EC830F0…91F1E8CF`），再执行 S05 环境数据接入与联合分析；停在 S05 等验收，未开始 S06。

- **导入与数据库**（`0007_environment.sql` + `environment_import.py`）：CSV/XLSX 字段识别与映射、时区与 UTC 双时间、单位白名单换算、预览、缺测/异常/重复/来源冲突检查、来源登记、批次与原文件归档；五张环境表建立。
- **真实导入**：Open-Meteo 逐小时风速 XLSX 288 行（168 模型历史 + 120 预报，预报不参与分析）；水温因无独立文件，从声学 CSV 按日派生 4 行代理并标 `DERIVED`，不进入联合解释变量。潮汐仅 PNG 截图、风向无列 → 全部 BLOCKED，不估读不伪造。
- **联合与滞后**（`environment_analysis.py`）：7 组预设时滞全输出、Fisher z 95% CI、lag-1 自相关折减有效样本、Holm 校正、多因素最小二乘与诊断；真实 120 对风速—声学小时数据 r=−0.177~−0.096、Holm p=1，无关联证据；联合模型 R²=0.0092，水温代理排除。
- **自动获取**（`environment_fetch.py`）：三候选数据源评估全部 BLOCKED、适配器契约与失败日志；`FETCH-FE91F63EA6` 记录阻断原因，未联网、未覆盖手动数据。
- **入口与测试**：`/environment` 等 4 条路由 + CLI `s05_environment.py`；新增 12 项测试，**196 passed**；21 个原始 CSV 哈希 21/21 不变。
- **修复**：预报关键词误标逐行质量、水温代理位置键冲突、测试归档污染真实目录三项均在验收前修正并加回归/隔离测试。
- **未动**：21 个原始 CSV、V4 包、S04 既有断言；未开始 S06。

## 2026-11-17（S04 验收与提交，CodeBuddy）

用户确认 S04 验收完毕；提交 S04 全部代码/证据/文档（`1658a38`）并建 tag `s04-accepted`，随后启动 S05。S04 报告结论不变：`STAGE_S04.md`、184 passed、跨午夜/时区对账与 5 组真实比较。

## 2026-11-17（S04 执行，CodeBuddy；用户「验收完毕，继续」后启动，状态 S04_DONE_PENDING_ACCEPTANCE）

S03 验收通过后先提交 `1dfa91a` 并建 tag **`s03-accepted`**，备份正式库（`11_BACKUPS/s04_pre_run_20261117/`，SHA-256 `C0CCA95C…F35CF`），再执行 S04 任意时间/天数/设备比较；停在 S04 等验收，未开始 S05。

- **筛选引擎**（`app/services/comparison.py`）：日期区间两端包含、非连续日期集合、任意天数（日历日/有效日模式）、`[start,end)` 小时窗与跨午夜归属（当日 `[start,24)` + 次日 `[0,end)` 归起始日，不重复不漏）；支持声明时区并输出本地/UTC 半开区间，未知时区拒绝；空集给明确原因。
- **比较与基线**：V4 指定 8 组日期比较（合成 7 日序列逐组对账，真实库只有 4 有效日 → 第 5/7 日比较标 `INSUFFICIENT_DATES`，不伪造）；任意设备对照（缺对记 `MISSING_PAIR`）；前 3/7/30/N 有效观测日、前 N 日历日、全部历史、任意区间与滚动基线，附成员清单与分母表，缺测日不进基线，参考为 0 时百分比 NA。
- **指标与总结**：每项含参考值/比较值/差值/变化百分比/有效样本量/覆盖率/结论；日内子窗口时长覆盖率标 estimated，信号分布与水温为 NA；自动总结明确“不等同于真实鱼类数量变化”，水层指标因 S07 门禁未过不输出。
- **真实数据**：2000 四日矩阵（D1 vs D2 +16.20%、D4 vs 前3日均值 +34.03%）、双设备同日 2001 vs 2000 +389.56%（各自有效时长规范化）、06—18 时窗口、22—02 跨午夜、前 3 有效日基线（n=3、合并率 530.9403）；5 次比较均落盘 JSON/CSV/MD 并存 `comparison_runs` 可复现。
- **入口**：`/compare` 表单与结果页、CLI `scripts/s04_compare.py`、`0006_comparison.sql` 比较留痕表；新增 26 项测试，**184 passed**；原始 CSV 21/21 哈希不变。
- **顺带修复 S03 测试污染**：`/daily/.../missing` 未传 `project_root` 导致 pytest 重写真实 `s03/analysis_index.json`；给 `create_app` 增加 `PROJECT_ROOT` 配置、网页显式传参、测试夹具指向 `tmp_path`，真实索引恢复 HEAD 内容，复跑后无改动。
- **未动**：21 个原始 CSV、V4 包、S03 既有断言；未开始 S05。

## 2026-11-17（S03 验收与提交，CodeBuddy）

用户确认 S03 验收完毕；提交 S03 全部代码/证据/文档（`1dfa91a`）并建 tag `s03-accepted`，随后启动 S04。S03 报告结论不变：`STAGE_S03.md`、158 passed、真实 8 步增量验证与独立复算 PASS。

## 2026-11-17（S03 执行，CodeBuddy；用户「S02通过，继续做S03」后启动，状态 S03_DONE_PENDING_ACCEPTANCE）

先建 tag `s02-accepted`（指向 `6c04e9e`）作回滚点，运行前备份正式库（`11_BACKUPS/s03_pre_run_20261117/`），再执行 S03 每日统计/增量上传/缺测/基础图表；停在 S03 等验收，未开始 S04。

- **统计引擎**（`app/services/daily_stats.py`）：所有样本只走 `build_mask(allow_blocked=False)`；逐指标分子/分母/单位/NA 规则见 `10_TEST_REPORTS/s03_verification/metric_definitions.csv`；type-7 精确分位数、总体标准差、阈值候选事件 `CANDIDATE_RUN_V1`（200/连续3格，非鱼量结论）；区内无候选记 0、无区内观测记 NA，缺测不填 0。
- **增量上传**（`app/services/incremental.py` + `scripts/s03_daily_pipeline.py`）：一天一台一批次，run_id + 参数/映射/算法/文件哈希完整快照；重复跳过、同日异容冲突审查、迟到、历史补传、冻结数据集保护、缺测自动登记、旧 run 仅标 `SUPERSEDED`；`analysis_index.json` 随每次上传更新。
- **真实数据**：2000/2001 的 2026-10-31 全量统计（192,235 / 189,834 条；区内样本 20,805,591 / 20,720,840；覆盖率 0.9235 / 0.9910；候选事件 13,093 / 68,784）。真实 8 步增量验证用 2000 的 11-01 → 跳过 11-02 → 11-03 → 补传 11-02 完成，第 2 天先 MISSING 后 REPROCESSED，原始 CSV 哈希 21/21 不变。
- **真实数据缺陷登记**：11-02 文件有 **37 行信号数组有效槽位为 0**，原逐行阻断导致整天失败；修复为计入 `invalid_records` 并写 QC 备注（不填 0），补传成功；失败与成功日志均归档。
- **日报与图表**（`app/services/reporting.py`）：日报 MD + 指标 CSV + 6 类 PNG（活动曲线/信号分布/覆盖率/缺测/底界排除/统计表），配色取自 `FIGURE_COLOR_SPEC_V1` A 方案；缺测图不伪造 0 曲线。新增 `/daily` 等 4 条网页路由。
- **修复**：首次真实统计 `file_sha256` 为空（复用未算哈希的 inspection）→ 显式传哈希并以 `--force` 为两台重算生成新 run，旧 run 保留为 `SUPERSEDED`，未覆盖历史结果。
- **测试与复算**：新增 22 项（158 passed）；`12_DOCUMENTATION/verify_s03_stats.py` 纯标准库独立重算两台真实前 2,000 行，kept_samples/sum/mean/候选事件/排除原因逐项 PASS。
- **未动**：21 个原始 CSV、V4 包、S00—S02 既有断言；未开始 S04。

## 2026-11-17（S02 增补：盲区口径落地，CodeBuddy）

用户提供盲区口径：「信号强度列以第一个出现的 0 开始才算是数据盲区的结束；设备的数据盲区是 0.5 m」。全量实证后落地，S02 仍停在待验收，未开始 S03 统计。

- **实证（两台全量 89.7s 重跑）**：首零索引（0 基）众数 2000=**17**（47.96%）、2001=**16**（46.65%），范围 15—63 / 11—62，随噪声波动；无 0 的行 0；首零前取值 1—255。0.5/17≈0.0294 与已确认格宽 0.0375 不一致 → **首零只作逐行盲区结束标志，不用于反推距离轴**；几何以映射 v2 为准。
- **映射 v2（并行会话 2026-11-16 登记，本会话核实）**：INTERVAL、首格起点 0.5 m、格宽 0.0375 m、末格终点 38.0 m、CONFIRMED（证据含微信"百岁山"确认与首点 0.5 m 用户确认）→ 两台 `build_mask` **OK**，`issues.csv` P0×2 消除（10 → 8 项）；v1 UNKNOWN 只读保留，K06 阻断机制仍由测试证明。
- **硬掩码落地两层盲区排除**（`distance_mapping.py`，唯一入口 `build_mask`）：① 行内首零之前 → `NEAR_FIELD`（位置性规则，优先级最高）；② 几何 r<0.5 m（点）/整段在盲区内或跨界盲区边界（区间）→ `NEAR_FIELD`。原有规则不变（无浮点容差、跨界截断整段排除、映射未核实 BLOCKED、不零填充）。
- **审计/解析**：`csv_parser.first_zero_index()`；`audit_s02` 新增首零分布/首零前取值/无 0 行统计；`signal_array_audit.csv` 新增 `blind_zone_m`、`first_zero_*`、`pre_zero_*`、`candidate_spacing_if_blind_zone_boundary` 列；`DATA_AUDIT_REPORT.md` §4 盲区实证、§8/§10 掩码状态动态化。
- **测试**：新增盲区 4 项 + 首零解析 1 项 + 行内盲区夹具断言；K04 幅度不变性用例界外值改非 0（避免误触发行内盲区，意图不变）。**136 passed**。
- **文档**：`STAGE_S02.md` §13 增补、矩阵 K06 更新、索引状态与测试计数、`s02_verification/audit_run.txt` 与 `mask_run.txt` 刷新。
- **待确认**：若用户本意为「首零固定对应 0.5 m（以首零定位距离轴）」，与格宽 0.0375 冲突，需重新登记映射版本；当前按「首零=逐行盲区结束标志」实现。
- **未动**：两份原始 CSV（SHA-256 复验一致）、V4 包、S03 未开始。

## 2026-11-16（距离映射 CONFIRMED 解阻，S03 前置门槛清除；状态 MAPPING_CONFIRMED_PENDING_S03）

经微信“百岁山”确认采样参数 + 用户确认首点距离，对两台登记 CONFIRMED 映射 v2，解除 2000/2001 距离分析 BLOCKED；S03 前置门槛已清除，但尚未开始 S03 正式统计。

- **确认参数**：`sample_mode=INTERVAL`（“一段距离区间”）；`sample_interval_m=0.0375`（“一格 3.75cm”）；`first_sample_distance_m=0.5`（用户确认，与盲区 0.5m 一致）；range=37.5、point_count=1000；末格终点 = 0.5 + 1000×0.0375 = **38.0m**（解释“末点不是 37.5”）。
- **登记**：脚本 `scripts/register_confirmed_mapping.py`，对两台各登记 v2（support=CONFIRMED），v1（UNVERIFIED）只读保留不覆盖；`audit_logs` 记录 CONFIRM_MAPPING（actor=Administrator）。
- **2001 适用依据**：五台种子数据登记为“同型号探鱼仪”，且 2000/2001 信号数组结构完全一致（1000 槽/37.5 量程/0-255）；采样参数为同型号固件级硬件特性，按同型号外推，evidence 已注明，可回滚。
- **验证**：构造数据正式模式 `build_mask` status=OK、保留 125 格、第 125 格 [5.1875,5.225) 跨界整段排除；真实 CSV 首行（`14_TEMP/verify_real_mask.py`）两台 status=OK、kept=125（1 跨界 + 874 越界 = 1000）；全量 pytest **131 passed**。
- **未做**：未开始 S03 正式统计；未改原始 CSV 与 V4 包；未打 `s02-accepted` tag（待用户签收）。

## 2026-11-16（S02 执行，CodeBuddy；状态 S02_DONE_PENDING_ACCEPTANCE）

S01 复验通过 → 建 tag `s01-accepted` → 执行 S02（真实 CSV 解析与数据质量审计），停在 S02 等验收，未开始 S03。

- **文件检查**：2000 = 398,320,647 B、UTF-8-SIG + LF、192,235 数据行；2001 = 396,831,479 B、**GB18030 + CRLF**、189,834 数据行；两份 SHA-256 与 `RAW_CSV_ARCHIVE_MANIFEST.csv` **PASS**。2001 此前读取失败即因按 UTF-8 解码；现逐文件探测（BOM → 严格 UTF-8 → GB18030 回退）。
- **流式解析**（`app/services/csv_parser.py`）：逐行 `csv.reader`，不加载全文；保留行号/序号/时间戳原文/数组原文；支持 `2026-10-31 00:00:00` 与 `2026/10/31 0:00` 等格式；全量审计 94.2 s。
- **新发现（写入 issues/报告）**：① 每行数组 **1001 token = 1000 有效槽位 + 1 个尾部空项**（冒号结尾），不能把空项当第 1001 个采样；② 2001 时间戳**只到分钟**（单分钟最多 150 行），不能与秒级轴对齐；③ 2000 水深 0 值 150,750 行（78.4%），2001 17,250 行（9.1%）；④ 2000 同秒 78,639 组、2001 同分钟 1,427 组，均未去重。
- **距离映射**（迁移 `0003_distance_mappings.sql` + `app/services/distance_mapping.py`）：按 `(device_id, version)` 版本化；两台登记 v1（range 37.5、1000 槽位、`sample_mode=UNKNOWN`、`support_status=UNVERIFIED`、首点距离 NULL），证据写明缺项。**正式距离分析 BLOCKED**（`DistanceMappingBlocked`），诊断模式 `status=BLOCKED`、`kept=()`，不冒充 0 样本。
- **统一硬掩码**：唯一入口 `build_mask`；点样本 `r<=cutoff` 保留、**无浮点容差**（5.201 排除、5.2+1e-12 排除）；区间整段在界内才保留、跨界整段排除；排除原因 5 类（人工越界/跨界区间/距离未知/无效值/映射未核实），预留近场与底部干扰给 S07；越界幅度 0→65535/1e9 区内保留值与求和不变。
- **8 份审计工件**（`10_TEST_REPORTS/data_audit/`）：field_dictionary、signal_array_audit、timestamp_audit、coverage_audit、device_comparability、bottom_reference_audit、issues（10 项含 2 项 P0 BLOCKED）、DATA_AUDIT_REPORT.md；独立入口 `scripts/s02_data_audit.py`。
- **2000 底界审计**：3.68 m（USER_DEFINED_ESTIMATED/NOT_DETECTED）、45°、15°FULL 条件算例 β=7.5、人工截断 5.2 m、派生 5.2043059095 仅参考不覆盖 5.2；2001 倾角 UNKNOWN → 几何 BLOCKED。
- **测试**：新增 `test_s02_mask.py`（16）与 `test_s02_parser.py`（9），全库 **115 passed**；S01 既有断言未改。`test_s00_smoke` 允许 `scripts/`；`verify_s01_fix.py` 迁移断言改为「前两个必须为 0001/0002」以容纳后续迁移。
- **证据**：`10_TEST_REPORTS/s02_verification/`（`boundary_cases.csv` 手算对照、`mask_run.txt`、`audit_run.log`）。
- **未动**：两份原始 CSV（哈希 PASS）、V4 包；未开始 S03；无破坏性 Git 操作。

## 2026-11-16（S01 验收整改，CodeBuddy；状态 S01_FIXED_PENDING_RECHECK）

独立验收（`10_TEST_REPORTS/stage_reports/ACCEPTANCE_S00_S01.md`）判定 S01 不通过：3 项 D1 + 5 项 P2。本轮只整改，未开始 S02。

- **D1-1 K13 校验（已修）**：`app/services/devices.py` 废弃 `_num()`，新增 `_parse_number()`：非数字→字段级 400（不再 500）；`math.isfinite()` 拒绝 NaN/inf/-inf/1e999；非法值与空值用 `_INVALID` 哨兵区分，杜绝静默入库。截断新增有限上界：优先 `devices.range_m`，为空时 `CUTOFF_FALLBACK_MAX_M=100 m`（文案明确"量程 UNKNOWN，按上限 100 m 临时校验"；阈值来源与"待用户确认量程后收紧"已登记）。同规则覆盖垂直离底/轴斜距/倾角/波束角/方位角/经纬度/定位精度。`routes.py` 新增 `parse_expected_version()`：abc/空串/负数/非整数→400；预览接口 `require_cutoff=False`，非法字段仍 400+JSON。
- **D1-2 依赖锁（已修）**：`requirements-lock.txt` 重建为 `pip freeze --all` 39 行、无 BOM、LF；`pip install --no-deps --dry-run -r` 全解析通过；新增运行期 `requirements.txt`（flask/python-dotenv/requests）。
- **D1-3 迁移原子性（已修）**：`app/db.py` 改为 `isolation_level=None` + 显式 `BEGIN IMMEDIATE/COMMIT/ROLLBACK`，语句用 `sqlite3.complete_statement` 逐字符切分；坏迁移注入后表/数据/schema_migrations 全部回滚。顶部注释同步更正，不再声称未具备的能力。
- **P2-1 站位**：迁移 `0002_devices_station_id.sql` 为 `devices` 增加可空 `station_id`；页面显示"站位：未分配"；`stations` 保持为空，未伪造。
- **P2-2 预览预填**：无参数设备预览链接不再写死 5.2；空截断返回 null + "截断未填写（预览不借用其他设备数值）"。
- **P2-3 操作者**：新增 `app/identity.py`（登录名，弱标识），`created_by`/`actor` 不再恒为 web；seed 仍记 seed；S10 多用户须替换为账号主体。
- **P2-4/P2-5 文档**：矩阵 K13→PASS（写用例 ID）、K01→"S01 部分实现，S02 复验"、K43 登记迁移/依赖整改、第 20 章标注部分实现；`STAGE_S01.md` 新增 §16 验收整改记录（09 第二节字段齐全）、§3 更正迁移事务不实声明、§14 补齐阈值/站位/操作者/K01；总索引状态改 `S01_FIXED_PENDING_RECHECK`。
- **测试**：新增 `04_SOURCE_CODE/tests/test_s01_fix.py` 40 用例（含 6 态截断非法值、expected_version、位置字段、预览、锁文件格式、坏迁移回滚、station_id、操作者、回归）；既有 53 项断言**一字未改**；`pytest` **93 passed**。
- **证据**：`10_TEST_REPORTS/s01_verification/fix_evidence/`（pytest.txt、verify_db.txt、pip_dryrun.txt、curl_cases.txt、bad_migration_and_lock.txt）；`12_DOCUMENTATION/verify_s01_fix.py` 对正式库只读复验全 PASS（2000 仍 5.2/3.68/45/15FULL/β7.5/派生 5.2043059≠5.2；2002/2003/2005 零行）。
- **未动**：21 个原始 CSV、V4 包（`git status` 无相关变更）；未开始 S02；未使用破坏性 Git 命令，整改为新增提交 `5aae0e5`（不 amend）。

## 2026-11-15（S01 执行，CodeBuddy）

### S01：数据库、五台设备和独立参数管理（用户「S00 验收通过，开始 S01」后执行，待验收）

- **回滚点**：创建 tag `s00-accepted`（S00 验收回滚点）。
- **数据库（任务一）**：新建 `03_DATABASE/fishery.db`；迁移框架 `app/db.py` + `migrations/0001_init.sql`（12 张表：devices/stations/device_parameters/device_parameter_versions/device_positions/device_installations/bottom_references/file_registry/import_batches/analysis_runs/datasets+members/audit_logs）；幂等迁移已测；`.gitignore` 排除 `*.db`。
- **五台设备（任务二/三）**：2000/2001/2002/2003/2005（无 2004）入库；独立离底高度双向换算（VERTICAL↔AXIS_SLANT，按本台倾角），派生值标记 is_derived 不写回用户输入、不覆盖 5.2 截断；UNKNOWN 一律 NULL，不自动填 3.68。
- **历史版本（任务四）**：每次保存生成新版本（含来源/测量方式/不确定性/修改原因/生效区间），旧版本不可变；analysis_runs 以 params_snapshot_json 引用版本 id（缓存失效按版本键控）。
- **2000 初始配置（任务五）**：3.68 人工水底参考面（USER_DEFINED_ESTIMATED、NOT_DETECTED）+ 5.2 截断 + 45° 倾角 + 15°FULL（用户裁定）播种；2001 播种用户提供的 5.2/3.6/坐标；2002/2003/2005 保持 UNKNOWN。
- **数据集（任务六）**：DATASET_01_DUAL_STATION（2000+2001）与 DATASET_02_FIVE_STATION（五台）建立，PLANNED，起止待确认。
- **原始文件登记（任务八）**：file_registry 播种 21 行（SHA-256 来自 RAW_CSV_ARCHIVE_MANIFEST.csv），路径唯一+重复检查；原始文件未改动。
- **强制增项网页**：`/` 设备清单+未知参数队列（K01）、`/devices/<id>` 参数/GPS 全字段表单+双历史表、保存前影响预览 JSON、后端校验 400（K13）、并发冲突 409；CSS 全部取自配色板。
- **测试（任务七）**：P1—P5 独立性、修改 P1 不影响他台、倾角换算（45°/30°）、UNKNOWN 不填默认、历史保留、人工底界独立、数据集独立创建——全部 PASS；**pytest 53 passed**（含 K01—K03/K13/K19/GEO-01/GEO-03 与迁移幂等）。
- **界面证据**：真实启动 Flask（127.0.0.1:5000），首页/2000/2001 详情页/预览接口 4 请求全 200，证据归档 `10_TEST_REPORTS/s01_verification/web_evidence/`。
- **配色校验**：check_figure_colors.py 色板外 0 PASS。
- **阶段报告**：`10_TEST_REPORTS/stage_reports/STAGE_S01.md`。**当前停在 S01 等待用户验收；未开始 S02**。与阶段文本的两处偏差均系用户裁定（15°=FULL；2001 参数已提供），已在报告中登记。

> 以下为 2026-11-15 用户裁定登记（S00 待验收期间）。

## 2026-11-15（用户裁定与登记，S00 验收前）：2000 经度 121.2117505073547 / 纬度 27.99346353124773；2001 经度 121.2130272388458 / 纬度 27.99260143251764、截断斜距 5.2 m、离底高度 3.6 m。新建 `12_DOCUMENTATION/USER_PROVIDED_PARAMETERS.md` 作为 S01 网页录入的来源依据（字段用 V4 08 权威名，逐台独立，不继承）；数值自检：两站间距 **157.81 m**（南北 −95.86 m、东西 +125.36 m），坐标位于洞头附近海域，量级合理；末位 1e-13° ≈ 1.1e-8 m 属浮点残差，**不作为定位精度**，`position_accuracy_m` 保持 UNKNOWN。仍缺：坐标系（CRS）、定位精度、两台方位角、2001 倾角、2002/2003/2005 全部参数。已同步 PROJECT_MASTER_INDEX、DEV_PLAN R2、STAGE_S00.md 未知项清单。
- **15° 波束角确认为全角（用户裁定）**：用户「这是全角，已确定」。据此登记 `beam_angle_value_deg = 15`、`beam_angle_kind = FULL`、内部半角 β = 7.5°（全角 θ 对应 β = θ/2），五台同型号共用该波束角；S01 网页按台录入并按此派生 `beam_half_angle_deg`。V4 包正文（01/02/03/08/09/10/11/13/00）**不改写**，以本裁定为准；已同步 PROJECT_MASTER_INDEX、SPEC_VERSION_MATRIX（D4 + 待处置项 3）、V4_REQUIREMENTS_INDEX（第 5.8 条加注）、DEV_PLAN（R2）、REQUIREMENTS_TRACEABILITY_MATRIX（K22/GEO-02）、STAGE_S00.md。**仍未确认**：2001/2002/2003/2005 截断值、离底高度、全部设备坐标与方位角。
- **OriginPro 改用 2027（用户裁定）**：用户确认「OriginPro 2027 已安装，就用这个版本」。本机实测注册表：`Origin2027`，版本 10.40.131，安装路径 `C:\Program Files\OriginLab\Origin2027\`；COM ProgID `Origin.ApplicationSI`、`Origin.Application` 已注册（`OriginPro.ApplicationSI` 未注册）。Learning Edition 属性与 12 窗口上限待 S09 实测。规范 01/02 内「2026b」字样不改写，以本裁定为准；STAGE_S00.md、DEV_PLAN、追踪矩阵已同步。
- **设备参数填写范围澄清（非文档改动，答复用户）**：现有数据仅覆盖 2000/2001，但**数据到位 ≠ 参数已知**。按 V4 08 第 5 节，2001/2002/2003/2005 四台的截断斜距、垂直离底高度、全部坐标与方位角均未提供，保持 UNKNOWN——除非用户补充 2001 参数，否则网页需填写的设备为 **4 台**（不是 3 台）。S01 表单按五台全部建立，允许逐台 UNKNOWN/BLOCKED。

> 上一条目：2026-11-14（S00 执行，CodeBuddy）——见下方折叠记录。

## 2026-11-14（S00 执行，CodeBuddy）

### S00：项目检查、目录建立和备份（按 V4 03 第三章 + 06_CODEX_START.txt 执行，待用户验收）

- **环境（任务六）**：核实本机已装 Python 3.10.11（64 位）并复用用户批准的解释器；项目 `.venv` 指向 3.10.11，本轮补装并锁定依赖 flask 3.1.3 / numpy 2.2.6 / pandas 2.3.3 / matplotlib 3.10.9 / pytest 9.2.0 / openpyxl 3.1.5 等 36 项（`04_SOURCE_CODE/requirements-lock.txt`），全部在目标解释器内实测导入。**如实登记**：PyCharm 实装 2025.2.1.1（规范写 2024.1）；OriginPro 2026b 未安装、`Origin.ApplicationSI` COM ProgID 未注册（S09 BLOCKED）；`E:\鱼探仪` 路径不存在；实测硬件 Ryzen 7 9700X / 31.2 GB / 磁盘空闲约 4.8 TB。
- **完整性校验（任务五）**：新增 `12_DOCUMENTATION/s00_verify_integrity.py`，独立重算并复核 **V4 包 16/16**（对照 MANIFEST_SHA256.json）与 **21 个原始 CSV 21/21**（合计 8,380,445,292 字节，对照 RAW_CSV_PRECHECK_INVENTORY_CURRENT.csv）全部 PASS；证据在 `10_TEST_REPORTS/s00_verification/`。未照抄清单，逐文件重新哈希。
- **备份（任务七）**：新增 `12_DOCUMENTATION/s00_backup_assets.py`，30 个可恢复资产备份至 `11_BACKUPS/S00_baseline_backup_20261114/`（含逐文件 SHA-256 的 BACKUP_MANIFEST.csv 与恢复说明）；8.38 GB 原始 CSV 不做物理备份（只读保护，完整性由哈希清单覆盖）。
- **追踪矩阵与计划（S00 核心交付）**：新增 `12_DOCUMENTATION/REQUIREMENTS_TRACEABILITY_MATRIX.md`（24 章 / 36 交付 / 31 入口 / 18 报告 / 16 图 / 45 条 K / GEO-01—12 逐项登记，当前除 S00 相关 3 项外均为「未实施」）与 `12_DOCUMENTATION/DEV_PLAN_S00_S11.md`（12 阶段、57—89 人日参考、关键路径、V4 硬契约落位检查表、R1—R10 风险）。
- **自动测试**：新增 `04_SOURCE_CODE/tests/test_s00_smoke.py`，`python -m pytest` **29 passed**（目录骨架、五设备无 2004、21 CSV、V4 权威文件、示例配置五台隔离、目标解释器、依赖导入等）。
- **配色校验**：`check_figure_colors.py` 输出色板 26 色一致 PASS、参考图 3 张 PASS、生成物色板外 **0 种** PASS（已写入 STAGE_S00.md）。
- **规范冲突检查**：V4 01/02/03 与 08/09/10/11 逐点对照，未发现未裁定冲突；V4 与历史基线差异以 SPEC_VERSION_MATRIX.md D1—D12 为准，本轮独立复核无新增差异。
- **阶段报告**：生成 `10_TEST_REPORTS/stage_reports/STAGE_S00.md`（18 节，含环境实测、原始数据、备份、性能预算拟定、未知项、S01 前置）。**当前停在 S00 等待用户验收；未开始 S01**。
- **未做**：未生成 import_batch_id / run_id / manifest.json；未建立 SQLite；未解析导入任何原始 CSV；未使用破坏性 Git 命令；阶段回滚点 tag 按用户要求待验收后创建。

> 以下为开工前准备记录（WorkBuddy 辅助）。
> **初始 Git 安全回滚点**：`183e469e5ff62b39adda2e2fde693995879b3e2e`（2026-11-14 19:27，69 个文件 / 约 3.74 MB）。`.gitignore` 排除 8.38 GB 原始 CSV，`.gitattributes` 禁用换行转换以保证 V4 包 SHA-256 字节保真；S00 须核验复用并另建阶段回滚点。
> 2026-11-14 晚些时候修订：本轮会话进行中项目根目录出现 21 个原始 CSV，下文「原始数据不在本机」类表述已按 `RAW_CSV_ARRIVAL_NOTE.md` 更正。
> 同日 18:50 再修订：用户指示「整理一下文件夹」后，21 个 CSV 已按设备归档至 `01_ORIGINAL_DATA/FISHFINDER/2000/`、`2001/`，下文「未归档 / 归档须用户允许」类表述已按新状态更正。
> 同日 19:00 再修订：用户新增科研配色规格 `FIGURE_COLOR_SPEC_V1`，所有生成图片强制执行，详见下文专节。
> 同日 19:04 再修订：用户确认「双站先行 / 21 个 CSV 为完整导出 / 五站功能继续开发 / 后续持续上传」，**撤销**「缺 17 个文件＝全项目阻断」的误判；同时项目根目录出现 `FISHERY_FULL_PLAN_V4/` V4 规范包，登记为版本冲突 C13。下文旧表述以这两份新记录为准。
> 同日 **19:13—19:17 再修订**：用户确认「这是全部要求」「以 V4 为准」「只有 2000/2001/2002/2003/2005 五台、没有 2004」「Python 3.10 可以装」「Git 安全回滚点需要」「2001 到 11-07 结束不会补传」。项目已切换 V4 基准、按设备归位目录、初始化 Git 仓库并建立初始回滚点；下文旧表述以 `SPEC_VERSION_MATRIX.md` 与 `V4_REQUIREMENTS_INDEX.md` 为准。

## 2026-11-14

### V4 基准切换与四项用户裁定（19:13—19:17）

- 用户 19:13 指向 `FISHERY_FULL_PLAN_V4/` 并说明「这是全部要求，你整理一下」；19:17 明确「以 V4 为准。Python 3.10 可以装。Git 安全回滚点需要。2001 是观测到 11-07 结束，不会补传」，并强调「设备只有 2000、2001、2002、2003、2005 五台，没有 2004，不要混淆」。
- 通读 V4 包全部 17 个文件，逐文件重算并复核包内 `MANIFEST_SHA256.json` **16/16 一致**（清单不含自身）；确认 V4 01/02/03 为「FINAL 1.5 恢复正文 + 用户 V4 修订」，正文比历史基线更完整（1,793 / 986 / 2,313 行）。
- 新增 `12_DOCUMENTATION/V4_REQUIREMENTS_INDEX.md`（`SPEC_BASELINE_V4`）：17 文件导览、效力层级、**路径解析规则**（V4 文档内 `00_PROJECT_SPEC/01|02|03_*.md` 一律映射到包内同名文件）、24 章 / S00—S11 / 36 交付 / 31 入口 / 18 报告 / 16 图 / 45 条 K / GEO-01—12 / W1—W3 / D0—D2 / 用户十步验收、要求与项目现状对照。
- 新增 `12_DOCUMENTATION/SPEC_VERSION_MATRIX.md`：D1—D12 版本差异、四项裁定落地、仍待处置项；澄清「31 入口覆盖 29 项界面能力」不是冲突，撤销该待裁定项。
- 新增 `00_PROJECT_SPEC/README.md`（历史基线只读声明）与 `01_ORIGINAL_DATA/FISHFINDER/README.md`（V4 设备清单、只读保护、持续上传、双站口径）。
- **设备目录归位**：删除空的 `2004/`、补建 `2005/`；现为 2000 / 2001 / 2002 / 2003 / 2005 五台，与 V4 完全一致。未移动或改写 21 个原始 CSV。
- `12_DOCUMENTATION/S00_START_PROMPT.md` 整体切换 V4 基准：V4 03 第二章**修订版 22 条**（第 8 条为「人工分析截断 5.2 m；5.2043 m 仅理论参考」）、`06_CODEX_START.txt` 要求、路径解析规则、四项用户裁定、本机实测事实与配色规格。
- 建立 **Git 安全回滚点**：`git init`、新增 `.gitignore`（排除 `01_ORIGINAL_DATA/FISHFINDER/**/*.csv` 共 8.38 GB、`14_TEMP/`、`.venv/`、缓存），初始提交号见本文件顶部「初始回滚点」。S00 须核验复用并另建阶段回滚点。
- 批量同步 30 余处文档表述：`PROJECT_MASTER_INDEX.md` 与 `PROJECT_STRUCTURE.md` 重写为 V4 基准；`ENVIRONMENT_PRECHECK.md`、`RAW_CSV_ARRIVAL_NOTE.md`、`V4_PACKAGE_ARRIVAL_NOTE.md`、`WORKBUDDY_SCOPE_AND_GAPS.md`、`SCOPE_CONFIRMATION_DUAL_STATION.md`、`10_TEST_REPORTS/README.md`、`V4_REQUIREMENTS_INDEX.md`、`generate_demo.py` 中的版本待裁定 / 2004 / Python / Git / 2001 补传等旧口径全部更新，历史时间线以修订说明保留。
- **刻意没做**：未拆散、改名或改写 V4 包内任何文件；未覆盖或删除 `00_PROJECT_SPEC/` 历史基线；未安装 Python 3.10（已获授权，S00 执行）；未把 V4 参数写成已实现；未生成 `STAGE_S00.md`；未解析或导入任何原始 CSV。

### 双站先行范围确认与 V4 规范包到位（用户 19:04 指示，19:04 完成）

- 用户确认：「原目录名 探鱼-2001_2026-11-07 这是完整导出。根据主规范和指南是先做两台的。2000数据是10月31号到11月12有的，2001是10月31到11月7号。然后五台一起的功能是继续开发，后续会上传数据」「按照要求是可以持续上传」。
- 核对规范原文：01 主规范 2.1（第一阶段 2000/2001、天数由真实数据决定）、4 章数据集（`DATASET_01_DUAL_STATION` 为两台实际同期观测）、**第八章「必须从早期开发阶段支持逐日增量上传」**、02 指南 5.1、03 阶段任务 S01/S07/S11、03 第二章话术第 10/11/15 条。与归档清单逐日核对：2000 13 个 / 10-31—11-12、2001 8 个 / 10-31—11-07，**与用户说明完全一致**。
- **撤销旧误判**：附录 A1 的 38 个 / 11.07 GB 是另一时点、另一阶段的外部目录盘点，不是第一阶段应有全集；「缺 17 个文件 / 2002/2003/2005 全缺 / 全项目阻断」等结论全部作废，逐份修订 `WORKBUDDY_SCOPE_AND_GAPS.md`（C1/C8/G1/G2、第五节）、`RAW_CSV_ARRIVAL_NOTE.md`、`ENVIRONMENT_PRECHECK.md`、`S00_START_PROMPT.md`、`PROJECT_MASTER_INDEX.md`、`PROJECT_STRUCTURE.md`、`DEMO_PROTOTYPE.html`。
- 新增 `12_DOCUMENTATION/SCOPE_CONFIRMATION_DUAL_STATION.md`（`SCOPE_DUAL_STATION_V1`）：6 条用户确认、规范依据表、逐日核对、撤销清单、开发顺序影响表；并登记**仍待确认的科研口径**——两站结束日相差 5 天，共同重叠窗口须按文件内真实时间戳计算，2000 的 11-08—11-12 为单站延伸，不得计入双站同期样本量。
- 登记持续上传硬约束：`import_batch_id`、历史补传/延迟上传/重复上传/冲突审查、补传只重算受影响结果、旧分析与冻结版本保留；S02 解析器不得写成一次性批处理。
- 发现项目根目录新出现 `FISHERY_FULL_PLAN_V4/`（目录创建 19:02:27，17 个文件，mtime 18:54—18:59）。逐文件重算大小与 SHA-256，**包内清单 16/16 全部一致、0 不符**；清单外唯一文件为清单自身。
- 新增 `12_DOCUMENTATION/V4_PACKAGE_ARRIVAL_NOTE.md`：登记 V4 自述效力（08 同主题最高效力、01/02/03 同步修订、不再宣称与早期 DOCX 逐字相同）、V-1—V-8 与 FINAL 1.5 的实质差异（设备 2005、5.2 m 硬截断、S01 参数网页、15° 全/半角待确认、S02 起截断生效、不以搬迁原始 CSV 为前置、45 条验收、31 类入口）、与已完成归档不冲突的说明、4 项待用户裁定（**该 4 项已于 19:17 全部裁定关闭，见本文件上方新章节**）。
- `S00_START_PROMPT.md` 同步：补充双站完整导出、持续上传、同期窗口口径、V4 版本冲突须裁定且两套都读不得静默择一；**复验 22 条要点仍与 03 第二章原文逐字一致**。
- **刻意没做**：未修改 `00_PROJECT_SPEC/` 任何文件，未把 V4 三份规范覆盖或复制进去，未改动 `01_ORIGINAL_DATA/FISHFINDER/` 设备目录（2002/2003/2004 仍空、未擅自增设 2005），未替换/删除 `S00_START_PROMPT.md`，未把 V4 的 5.2 m 截断或 45 条验收写成已实现，未做两套规范逐条差异矩阵（列入 S00 待办），未生成 `STAGE_S00.md`。

### 环境与资料准备（非阶段验收）

- 初始化本地工作区，从企业微信缓存目录归档 6 份资料：三份 FINAL 1.5 规范、开发总规划、洞头逐小时风速 xlsx、潮汐 zip。原件仍保留在来源目录，未删除。
- 将 `02_CODEX_EXECUTION_GUIDE_FINAL.md.docx`、`03_CODEX_STAGE_TASKS_FINAL.md.docx` 无损转换为同名 `.md`：还原标题层级、有序/无序列表及 03 中的 1 张 13 行表格；校验 02 的 497 个非空段落、03 的 1191 个非空段落（含 39 个表格单元格）全部匹配，无内容丢失。
- 两份原始 `.md.docx` 移入 `00_PROJECT_SPEC/_source/` 作为只读备份。
- 按 02 执行指南第 3 章与 S00 任务三、四建立 `FISHERY_RESEARCH_SYSTEM/` 下 `00`—`14` 共 15 个一级目录及原始数据子目录；移除此前的临时分类目录（`data/`、`docs/`、`output/`、`scripts/`）。
- 资料归位：三份规范 → `00_PROJECT_SPEC/`；风速 xlsx → `01_ORIGINAL_DATA/ENVIRONMENT/WIND/`；潮汐 zip → `01_ORIGINAL_DATA/ENVIRONMENT/TIDE/`；开发总规划 → `12_DOCUMENTATION/`。
- 建立 `PROJECT_MASTER_INDEX.md`、`PROJECT_STRUCTURE.md`、`CHANGELOG.md`。
- 整理 `12_DOCUMENTATION/S00_START_PROMPT.md`：基于 03 第二章原文话术，补充实际 Windows 路径与当前准备状态，未改动任何科研定义。

### 科研配色规格 V1（用户 18:55 指示，19:00 完成）

- 用户指示：「里面出的图片要使用科研配色方案，给你几个图片你参考一下。记录这条规格，并严格执行」，并提供三张参考图。
- 逐字核对三张参考图色卡，得到三套色板共 **17 色**（A 6 色 / B 5 色 / C 6 色），HEX 与 RGB 一一对应；另定义 9 个中性色，合计 26 色白名单。三张原图复制到 `05_CONFIG/COLOR_REFERENCE/`，原件仍在企业微信缓存目录未动，SHA-256 已登记。
- 新增 `05_CONFIG/FIGURE_COLOR_SPEC.md`（规格全文：适用范围、三套色板、语义角色、版式 10 条规则、禁止项、执行与校验）与 `05_CONFIG/figure_palette.json`（唯一机器可读色值源）。
- 新增 `12_DOCUMENTATION/figure_palette.py`（绘图脚本统一取色加载器，含 HEX/RGB 自检）与 `12_DOCUMENTATION/check_figure_colors.py`（校验色板一致性、参考图 SHA-256、生成物色值白名单）。
- **已实际落地**：`generate_demo.py` 改为从加载器取色、禁止硬编码；`DEMO_PROTOTYPE.html` 全页重绘并新增三套色板展示区。风速折线三时段用方案 A（深蓝/珊瑚红/灰蓝紫），卡片顶边按方案 C 轮转，浅底与提示区用方案 B。校验结果：**455 处色值 / 25 种唯一色 / 色板外 0 种 → PASS**。
- 明确不适用项：11 张潮汐 PNG 属原始资料截图，保持原样未改色、未重绘；参考图含原作者水印，仅作色值依据，不得作为出版素材。
- 同步登记到 `PROJECT_MASTER_INDEX.md`（新增「用户确认的补充规格」章节）、`PROJECT_STRUCTURE.md`、`WORKBUDDY_SCOPE_AND_GAPS.md` 与 `S00_START_PROMPT.md`（要求编码 Agent 在 S07/S09/S10 出图时统一取色并记录校验输出）。
- 启动话术 22 条要点仍与 03 第二章原文逐字一致；本规格只补充操作性约束，未改动任何科研定义或参数数值。

### 原始 CSV 按设备归档（用户 18:48 指示，18:50 完成）

- 用户指令：「你看看探鱼-2001_2026-11-07文件夹。这里面是设备2000和设备2001的数据。你整理一下文件夹。」构成 02 指南 3.2 所要求的用户明确允许。
- 按文件名前缀分设备：`探鱼-2001_2026-11-07/` 下 21 个 CSV → `01_ORIGINAL_DATA/FISHFINDER/2000/`（13 个 / 5,164,450,657 字节）、`2001/`（8 个 / 3,215,994,635 字节），**符合 02 指南 4.1**。
- 方式为同盘 `os.rename` 原子移动：未复制、未改写内容、未改文件名、未改时间戳；目标若存在同名文件则整体中止，不覆盖。
- 移动后逐文件重算 SHA-256 并比对字节数与 mtime，**21/21 三项全部 PASS**，合计仍为 8,380,445,292 字节。源目录清空后移除，原目录名保留在清单的 `source_relative_path` 中。
- 产物：`10_TEST_REPORTS/RAW_CSV_ARCHIVE_MANIFEST.csv`（来源→现行路径 + 移动前后哈希 + 校验结果）、`10_TEST_REPORTS/RAW_CSV_PRECHECK_INVENTORY_CURRENT.csv`（归档后复跑清单，含现行路径）、`12_DOCUMENTATION/archive_raw_csv.py`（可复现脚本）、`12_DOCUMENTATION/precheck_raw_csv.py`（已改为扫描归档位置并自动与归档前快照比对）。
- 归档后独立复跑预检：21 个文件、8,380,445,292 字节、4,025,012 文本行，与归档前快照 **21/21 SHA-256 与字节数一致**；编码 8 UTF-8 / 13 GBK、信号点数 21/21 为 1000，结论未变。
- `RAW_CSV_PRECHECK_INVENTORY.csv` 保留为**归档前快照**，不改写，作为校验基准；其 `note` 列的旧路径描述已失效，现行路径以 `RAW_CSV_ARCHIVE_MANIFEST.csv` 为准。
- 同步修订 `ENVIRONMENT_PRECHECK.md`、`WORKBUDDY_SCOPE_AND_GAPS.md`、`PROJECT_MASTER_INDEX.md`、`PROJECT_STRUCTURE.md`、`S00_START_PROMPT.md`、`RAW_CSV_ARRIVAL_NOTE.md`、`DEMO_PROTOTYPE.html`，把「位置不符 / 归档须用户允许 / 未归档」更正为「已按设备归档、位置合规、归档不等于导入」。

### 本机环境与资料预检（WorkBuddy 辅助，非阶段验收）

- 实测本机环境：Windows NT 10.0.22621；**未安装 Python 3.10**（仅 3.11.15/3.13/3.14）；PyCharm 2025.2.1.1（规范写 2024.1）；未发现 OriginPro；Git 2.45.1 可用但仓库未初始化；pandas/numpy/matplotlib/openpyxl 缺失。详见 `10_TEST_REPORTS/ENVIRONMENT_PRECHECK.md`。
- 首次核查确认 `E:\鱼探仪` 不存在、E/F 盘深度 4 内未搜到探鱼 CSV。**后续修订**：同日 18:25 左右项目根目录出现 `探鱼-2001_2026-11-07/`，含 21 个 CSV / 8,380,445,292 字节 / 4,025,012 文本行（2000 号 13 个、2001 号 8 个）。目录创建时间 18:25:21，来源与放置方式未确认；文件大小 3 秒内稳定。**未移动、未改名、未修改任何原始文件**（02 指南 3.2）。
- 对 21 个原始 CSV 执行流式只读预检：全量 SHA-256、字节数、文本行数、编码、BOM、换行、时间格式、首末时间戳、信号点数，输出 `10_TEST_REPORTS/RAW_CSV_PRECHECK_INVENTORY.csv`，脚本 `12_DOCUMENTATION/precheck_raw_csv.py`。实测 8 个 UTF-8/BOM/LF/ISO 与 13 个 GBK/CRLF/斜杠时间格式混用（同一设备不同日期），信号数组按冒号切分 1001 项、末项为空，去掉后**统一 1000 点**；2001 号此前读取失败更可能是编码问题而非文件损坏。
- 新增 `10_TEST_REPORTS/RAW_CSV_ARRIVAL_NOTE.md`：到位时间线、与规范/规划的 5 项差异（位置不符、缺 17 个文件、缺 2002/2003/2005、缺 3+8 天、目录名与内容不符）、结构预检结果、明确未做的 S02 审计项。（**此为当时结论；其中「缺 17 个 / 缺设备 / 缺日期 / 目录名未确认」4 项已于 19:04 由用户确认撤销，见本文件顶部修订说明与 `SCOPE_CONFIRMATION_DUAL_STATION.md`**）
- 同步修订 `ENVIRONMENT_PRECHECK.md`、`WORKBUDDY_SCOPE_AND_GAPS.md`（新增 C12、改 C8 与 G1）、`PROJECT_MASTER_INDEX.md`、`PROJECT_STRUCTURE.md`、`S00_START_PROMPT.md`、`DEMO_PROTOTYPE.html`，把「原始数据不在本机」全面更正为「部分到位、位置不符、仍缺 17 个」。（**同为当时状态，19:04 已撤销数量/设备/日期缺口**）
- 真实计算并登记 8 份归档资料的 SHA-256（三份规范、两份 docx 原件、开发总规划、风速 xlsx、潮汐 zip）。
- 直接解析风速 xlsx 内部 OOXML：288 行 / 12 天 × 24 条 / 1.3—12.71 m/s / 0 空值；确认来源为 Open-Meteo **数值气象模型**，含 144 历史存档 + 24 当日滚动 + **120 未来预报**，原表自述「历史时段也不是现场实测」。生成 `02_IMPORTED_DATA/ENVIRONMENT/WIND/wind_hourly_20261030_20261110_PREPROCESSED.csv`（补齐 UTC/本地双时间、来源类型、时段属性、质量标记、原始行号）。
- 解压潮汐 zip：11 张 PNG 曲线截图，逐张识别日期（2026-10-31—11-10）、农历、潮型，登记 `tide_image_inventory.csv`（含每张 SHA-256）。**刻意未做图像数字化**，遵循附录 A1「禁止生成超出图片分辨率的伪精确值」。
- 新增 `12_DOCUMENTATION/preprocess_environment.py` 作为可复现预处理脚本（不改 `01_ORIGINAL_DATA`）。
- 新增 `12_DOCUMENTATION/WORKBUDDY_SCOPE_AND_GAPS.md`：能力边界、C1—C11 共 11 条规范冲突、G1—G5 分级缺口清单，以及「是否只做网页版」的定位判断。
- 新增 `12_DOCUMENTATION/DEMO_PROTOTYPE.html` + `generate_demo.py` + `demo_assets/`：单文件**只读演示原型**，仅用真实的 288 条风速记录与 11 张潮汐截图，全离线、无外部资源；明确标注不是 S10 工作台，声学分析区保持空白而不填充模拟值。
- 同步更新 `PROJECT_MASTER_INDEX.md`、`PROJECT_STRUCTURE.md` 的状态与目录内容。

### 明确未做的事

- 对已到位的 21 个原始 CSV **仅做只读结构预检与 SHA-256**，未做 S02 全量审计（同秒多记录、时间断档、信号值范围、异常、设备可比性、底界）；未生成 `field_dictionary.csv` 等 8 项正式产物。
- CSV 已按设备归档，但**归档不等于导入**：未生成 `import_batch_id`，未入数据库，未建立 `02_IMPORTED_DATA` 中的正式导入批次，未做 S02 审计。
- 未建立 `.venv`（用户 19:17 已批准安装 3.10，S00 执行）与 SQLite 数据库（S00/S01）；**Git 仓库与初始回滚点已建立**；未编写或运行 Flask/解析/统计代码，未运行 Pytest。
- 未生成 `STAGE_S00.md` 阶段报告（须由编码 Agent 在目标解释器内实测后输出）。
- 未生成 `import_batch_id` / `run_id` / `manifest.json`；预处理的两个 CSV **不是正式导入批次**，S05 须重新核验。
- 未对潮汐曲线做图像估读，未生成潮位数值序列、活动指标、论文图表或证据包。
- 未进行任何阶段验收、数据冻结或备份恢复演练。

**当前状态：S00 未实施（NOT_STARTED）。** 上述均为开工前的资料准备、预检、归档、范围与版本登记，不构成 S00 PASS。四项用户裁定已于 19:17 关闭（以 V4 为准 / 无 2004 / 批准安装 Python 3.10 / Git 初始回滚点已建），2001 到 11-07 结束不补传；直接把 `S00_START_PROMPT.md` 整段发给编码 Agent 即可开工。S00 仍须安装 3.10 并建 `.venv`、核验回滚点、在目标解释器内复测环境、生成 `STAGE_S00.md` 后停止等待验收。五站功能继续开发，2002/2003/2005 数据后续持续上传。
