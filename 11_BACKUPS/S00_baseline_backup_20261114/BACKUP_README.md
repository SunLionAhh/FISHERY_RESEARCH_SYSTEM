# S00 基线备份（2026-11-14T21:40:42）

- 备份来源：项目根目录 FISHERY_RESEARCH_SYSTEM
- 文件清单：BACKUP_MANIFEST.csv（30 条，含 SHA-256）
- 缺失条目：无
- 8.38 GB 原始 CSV 不入备份：属 01_ORIGINAL_DATA 只读保护，
  完整性由 10_TEST_REPORTS/s00_verification/RAW_CSV_SHA256_RECHECK.csv（21/21 PASS）
  与 Git .gitignore 排除规则覆盖；恢复策略为「登记 + 哈希校验」而非物理复制。
- Git 回滚点：初始提交 183e469e5ff62b39adda2e2fde693995879b3e2e（代码与文档）。
- 恢复方法：把本目录内文件复制回项目对应路径，并逐条比对 BACKUP_MANIFEST.csv 的 SHA-256。
