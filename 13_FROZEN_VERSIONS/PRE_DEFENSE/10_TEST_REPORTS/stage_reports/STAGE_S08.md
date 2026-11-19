# STAGE_S08 — 五站 GPS 空间、站间距离、空间比较与动态时间轴

> 阶段：S08（LEVEL 7）｜依据：`FISHERY_FULL_PLAN_V4/03_CODEX_STAGE_TASKS_FINAL.md` 第十一章（任务一至七）、`09_DEVELOPER_ACCEPTANCE.md`（K19—K24、K33、K34）
> 执行日期：2026-11-17｜环境：Windows 11 / 项目 `.venv` Python 3.10.11 / pytest 9.2.0
> 回滚点：S07 验收后提交 `4b659ed` 并建 tag **`s07-accepted`**；运行前备份正式库 `11_BACKUPS/s08_pre_run_20261117/fishery.db`（SHA-256 `245790CF906102CF9714997D95BC83B09D68D9CEC06484FD21F63C20436D701C`）。
> **状态：S08 完成待验收。只展示真实坐标与离散实测帧；三站无坐标保持 UNKNOWN，朝向与坐标系未声明保持 UNKNOWN，站距只给 PROVISIONAL 示意，不虚构轨迹或连续密度插值。**

---

## 0. 交付物

| 类型 | 位置 |
| --- | --- |
| 迁移 | `app/migrations/0010_s08_spatial.sql`：`station_location`（版本化站位、坐标系/精度/水深/朝向/来源/有效期）、`station_distance`（距离、方法、坐标系状态、说明） |
| 服务 | `app/services/spatial.py`：坐标审计、S01 GPS 接入、站距、离线地图 payload、日活动、空间统计、四类热图、环境联合、离散动态帧、JSON/CSV 归档 |
| Web/CLI | `/s08` 页面（可编辑站位、坐标示意、分析表、时间滑块/播放暂停/单站五站切换）；`scripts/s08_spatial.py`（sync / station / distances / map / analyze / frames） |
| 测试 | `tests/s08_helpers.py`、`tests/test_s08_spatial.py`（8 项）；全库 **223 passed**（S07 215 + 新增 8） |
| 证据 | `10_TEST_REPORTS/s08_verification/`：`sync.txt`、`map.txt`、`analyze.json`、`frames_real.txt`、`pytest.txt`、`raw_hash_check.txt`、`real_data/*.csv` |

---

## 1. 任务一：GPS 管理（K19—K21）

- `station_location` 只记录用户给出的坐标；`station_id` 可空，**不自动分配 P1—P5**。网页 `/s08` 可逐台录入或清空经纬度、坐标系、GPS 精度、水深、探头水平朝向、坐标来源、测量日期与生效日期；保存时写新行并闭合旧行 `effective_to`，历史不覆盖。
- `sync` 从 S01 `device_positions` 接入真实已有坐标；真实库接入 **2 条**（2000、2001），两台 `station_id` 均为 NULL，来源保留 `USER_PROVIDED_2026-11-15（USER_PROVIDED_PARAMETERS.md）`；2002/2003/2005 未接坐标，保持 UNKNOWN。
- 坐标审计 `coordinate_audit()` 同时检查范围、坐标系声明、疑似经纬度颠倒、同点重复站位；只提示与阻断，**不自动交换经纬度或改写用户数据**。范围外的经纬度在网页与 CLI 均被后端拒绝（400 语义转为页面提示，不写库）。
- 站位按 `effective_from <= 观测日 < effective_to` 的半开区间匹配；测试验证 2000 在 2026-11-02 改朝向 90°→120° 后，迁移前后查询分别命中各自版本。

## 2. 任务二：空间地图（K23/K24）

- 页面提供**离线本地坐标示意**（`map_mode=OFFLINE_LOCAL_COORDINATE_SKETCH`），无在线底图、无地图投影；点位按用户坐标相对关系缩放，缺坐标不绘制并在表中列 UNKNOWN。
- 真实坐标（用户已提供、未改）：2000 = 121.2117505073547 / 27.99346353124773，2001 = 121.2130272388458 / 27.99260143251764；两台 `coordinate_reference_system` 均缺失，审计标 `CRS_UNDECLARED`，状态 PROVISIONAL。
- 站距：同坐标系组才计算；跨坐标系直接拒绝混算。两台因坐标系未声明，距离以 WGS84 近似给 **157.809 m（PROVISIONAL）**，方法记 `HAVERSINE_WGS84_ASSUMED_UNDECLARED`，说明中明确“仅作相对位置示意，不作正式站距”。
- 覆盖示意使用 S07 当日生效参数的**人工斜距上限**：2000 给 `CIRCLE_ONLY`、R=5.2 m、中心轴理论底距 5.204306 m；2001 因缺当日参数给 `UNKNOWN`。两台朝向均缺，方向足迹保持 UNKNOWN；整改新增 `directional_footprint()`：一旦录入 heading 且当日参数可用，即输出 `CONDITIONAL_SECTOR` 的条件扇形包络（heading=0° 朝北、顺时针，半角取内部波束半角，半径取前向投影上限），附完整本地坐标多边形；**仍不宣称实测海底足迹、不代表鱼位置或密度**。

## 3. 任务三：空间活动比较

- 输出每日五站活动率（次/有效观测小时）、日期×站位矩阵、昼夜×站位、三水层×站位、周/月变化；缺站/缺测写 NA，不补 0、不伪造。
- 真实库（2026-10-31—11-03）：2000 有 4 日（活动率 590.758 / 508.395 / 498.163 / 713.612 次/h），2001 仅 1 日（2892.109 次/h），2002/2003/2005 为 0 日。昼夜记录 8 条、水层记录 3 条、周窗口 2 个、月窗口 3 个，均来自 S06/S07 既有留痕，**没有用空间插值补足缺站**。
- 周为查询窗口内顺序 7 日分箱（页面已注明不等同自然周）；月按自然月分组。

## 4. 任务四：空间统计（K33）

- 站位差异含有效日数、均值、CV 与有效观测小时合计；同步性含同期 Pearson 与“a 领先 1 日”相关，均只称关联/时差，**不冒充鱼群迁移确认**。
- 真实库 2000/2001 只有 1 个共同有效日，Pearson 为 NA，全部 10 个设备对状态 `INSUFFICIENT_DATA`；格局稳定度仅 1 个顺序窗口，按新规则退为 `INSUFFICIENT_DATA`，不因单窗口首位站占比 1.0 就升级。
- 方法留痕明确：未校正时间自相关、有效观测时长与伪重复，不给显著性或因果结论。

## 5. 任务五：环境联合

| 变量 | 状态 | 站间比较 | 依据 |
| --- | --- | --- | --- |
| WIND_SPEED | PROVISIONAL | BLOCKED | 真实数值来自 S05 模型历史，但为共享单点/网格来源，无逐站独立观测 |
| WATER_TEMP | BLOCKED | BLOCKED | 只有派生代理，不作独立环境证据 |
| TIDE_HEIGHT | BLOCKED | BLOCKED | 潮汐截图不估读，无数值观测 |
| WIND_DIRECTION | BLOCKED | BLOCKED | 原资料缺列 |

- 动态帧环境按**本地 `observed_at`** 对齐（与声学本地日期同一时间轴），不再误用 `observed_at_utc`；每帧保留 `quality_flag` 与 `source_id`，缺测为 NA。

## 6. 任务六：动态空间（K34）

- `/s08` 提供日期滑块、时间步进、播放/暂停、0.5/1/2/4 倍速、单站/五站同步切换；色标固定（浅蓝 0—2、中蓝 2—5、深蓝 >5、灰色 NA），图例与缺测规则固定。
- CLI：`frames --devices 2000,2001 --start 2026-10-31 --end 2026-10-31 --step-hours 1` 生成 **24 个离散帧**；全查询窗口 4 天为 **96 帧**。帧内只有该小时已实测的站位候选事件与同步环境值，缺测帧标 NA。
- 输出不含轨迹字段、不含连续密度插值；`analyze` 同时归档 `spatial_summary.json`、`station_locations.csv`、`station_distances.csv`、`spatial_activity.csv`、`dynamic_frames.csv`，网页与 CLI 同源。

## 7. 任务七：测试与数据保护

```text
.\.venv\Scripts\python.exe -m pytest 04_SOURCE_CODE\tests -q
223 passed in 16.50s
```

覆盖：S01 GPS 接入且不分配 P 码、经纬度范围校验、历史版本与迁移前后匹配、跨坐标系拒算、疑似颠倒/重复点审计、日活动与统计、环境联合状态、离散帧缺测 NA、Web 路由与 CSV 归档。

原始数据保护：`10_TEST_REPORTS/RAW_CSV_ARCHIVE_MANIFEST.csv` 21 个声学 CSV 哈希 **21/21 一致**（`raw_hash_check.txt`）；S08 只读 S01/S03/S05/S06/S07 的库内结果，不改原始 CSV。

## 8. 本阶段发现与处置

| # | 发现 | 处置 |
| --- | --- | --- |
| D-01 | `environment_joint` 误引用不存在的 `environment_source.source_kind` | 改为 `s.kind AS source_kind`，避免查询失败被误当作无数据 |
| D-02 | 动态帧/环境联合误用 `observed_at_utc[:13]` 对齐本地小时（相差 8 小时） | 改用本地 `observed_at`，并在输出 `note` 中显式说明对齐口径 |
| D-03 | 仅 1 个顺序窗口时“首位站占比”恒为 1.0，被误标 PROVISIONAL 稳定度 | 要求至少 2 个窗口才给 PROVISIONAL，否则 INSUFFICIENT_DATA |
| D-04 | 两台真实坐标坐标系均未声明，直接混算会冒充正式站距 | 拆分为同组计算；未声明组只给 PROVISIONAL 近似并写明不可作正式站距 |
| D-05 | CLI `frames` 子命令缺 `--date`，导致分析入口构造 map 时属性错误 | 补 `--date` 参数，并用真实库复跑生成 `frames_real.txt` |
| D-06（再验收整改 P2-6） | 原代码 heading 一旦提供只会输出 `HEADING_DECLARED_NO_MEASURED_FOOTPRINT`，没有任何方向足迹几何 | 新增 `directional_footprint()`，基于 heading、内部半角和前向投影上限生成条件扇形本地多边形；缺 heading 仍 UNKNOWN，且不替代实测足迹 |
| D-07（用户补充方位角） | 五台设备 heading 原为 UNKNOWN | 用户 2026-11-19 提供手机罗盘截图：2000=110°、2001=260°、2002=270°、2003=234°、2005=165°。脚本 `s08_import_headings.py` 复制截图并登记 SHA-256，写为 `effective_from=2026-10-31` 的新版本；`heading_reference` 明确为手机磁北罗盘、假定部署期朝向未变。仅有 2000 同时具备坐标与当日参数，其 `map_payload` 已生成 `CONDITIONAL_SECTOR`；其余仍因缺坐标/参数不画方向足迹 |

## 9. 已知限制（不伪造）

1. 五站中仅两台有用户提供的坐标，且坐标系未声明；站距仍为 PROVISIONAL。五台已有用户提供的手机罗盘磁北方位角，但 2002/2003/2005 无坐标、2001 缺当日参数，不能给出正式方向足迹或确认覆盖重叠；2000 仅能画条件扇形包络，不是实测足迹。
2. 2001 缺当日生效声学参数，覆盖示意保持 UNKNOWN；不能借用 2000 的参数替代。
3. 2000/2001 仅 1 个共同有效日，空间相关、同步性与格局稳定性均不成立；不能声称站间同步规律。
4. 环境值为共享来源且缺水温独立观测、潮汐数值与风向列；站间环境响应比较为 BLOCKED。
5. 动态播放为离散小时帧；单步/倍速只改变播放节奏，不产生新的空间位置、鱼群轨迹或密度估计。

**结论：S08 的 7 项任务均有代码、真实数据、网页/CLI 与测试证据；停在 S08 等验收，未开始 S09。**
