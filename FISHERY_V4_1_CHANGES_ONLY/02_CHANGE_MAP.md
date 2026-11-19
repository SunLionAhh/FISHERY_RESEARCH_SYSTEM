# V4 → V4.1 变更清单

## 修改方式

本次没有将全部原文推倒重写。三份完整规范在保留旧要求的基础上增加相关章节细则；总规划整合细则、32条新增验收和示意图。辅助说明同步更新。原硬截断、五设备/GPS和几何规则继续有效。

## 三份规范改动位置

- 主规范：9.5、10.3、12.1、14.2、15.5、16.1—16.4、19.1、20.1、21.1，以及版本声明。
- 执行指南：第8章新增执行要求，9.15新增32项验收，以及版本声明。
- 阶段任务：S00、S03—S11相关章节追加本次任务，保留原阶段职责与授权边界；S01/S02原截断基础要求继续有效。
- 完整逐条新增正文见01_CHANGED_CLAUSES_ONLY.md。

## 同步修改的文本文件

| V4文件 | V4.1文件 |
| --- | --- |
| 00_README.txt | 00_README.txt |
| 01_MASTER_SPEC_FINAL.md | 01_MASTER_SPEC_FINAL.md |
| 02_CODEX_EXECUTION_GUIDE_FINAL.md | 02_CODEX_EXECUTION_GUIDE_FINAL.md |
| 03_CODEX_STAGE_TASKS_FINAL.md | 03_CODEX_STAGE_TASKS_FINAL.md |
| 04_FULL_PLAN_V4.html | 04_FULL_PLAN_V4_1.html |
| 04_FULL_PLAN_V4.txt | 04_FULL_PLAN_V4_1.txt |
| 05_PATTERNS_EXPLAINED.html | 05_PATTERNS_EXPLAINED.html |
| 06_CODEX_START.txt | 06_CODEX_START.txt |
| 07_SOURCE_REFERENCES.txt | 07_SOURCE_REFERENCES.txt |
| 08_USER_REQUIREMENTS_V4.md | 08_USER_REQUIREMENTS_V4.md |
| 09_DEVELOPER_ACCEPTANCE.md | 09_DEVELOPER_ACCEPTANCE.md |
| 13_REVISION_AND_VERIFICATION.txt | 13_REVISION_AND_VERIFICATION.txt |

总规划HTML/TXT改名为V4_1，增加新章节导航、实施/验收全文与图片引用；已有正文范围保留。工时从V4的57—89调整为V4.1讨论预算62—98工程人日，需按现有成果实测重估，并非工期承诺。05/06/07/08/09/13及README同步说明新版本与新增要求。03_V4_TO_V4_1_TEXT_DIFF.diff包含上述文本统一换行后的逐行差异；CRLF/LF格式变化不作为功能改动展示。它不是完整文件替换件。

## 完全未修改的文件（已按字节比较）

- 10_DEVICE_CONFIG_EXAMPLE.json
- 11_GPS_BEAM_GEOMETRY.md
- 12_GEOMETRY_EXAMPLE.png
- 12_GEOMETRY_EXAMPLE.svg

## 本包带出的新增文件

- 14_PATTERN_UI_CONTRACT_V4_1.md
- 15_V4_1_ACCEPTANCE.md
- 16_PATTERN_DASHBOARD_PREVIEW.png
- 17_60DAY_OVERVIEW_PREVIEW.png
- 18_V4_1_CONTRACT_FIXTURES.json

完整包的MANIFEST因文件变化重新生成；本修改包另有自己的校验清单，不可替换完整包的清单。

## 如何交给开发者

如果开发者已经收到完整V4.1包，不要再次合入本包条款；本包仅用于快速看改动。如果仍使用原V4，先按01/02说明理解范围，再根据基线差异合入。已有私下修改时先核对，不可盲目覆盖。图16/17为静态合成示例，JSON18为契约测试输入，不得作为真实研究数据。
