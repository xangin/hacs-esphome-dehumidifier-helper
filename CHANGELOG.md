# 版本紀錄

## 1.1.0 — 2026-09-03

- 整合改名為 **ESPHome Dehumidifier Helper**，繁體中文名稱為「ESPHome 除濕機助手」。
- Domain 和 component 目錄改為 `esphome_dehumidifier_helper`。
- GitHub repository 使用 `xangin/hacs-esphome-dehumidifier-helper`；本機資料夾改為 `hacs-esphome-dehumidifier-helper`。
- 明確定位為可共用於不同品牌的 ESPHome 除濕機實體助手。
- 保留日立 ST01 名稱別名與既有 firmware project 提示，改用可擴充的已知 project 清單。
- 更新 GUI、HACS／manifest metadata、打包與檢查腳本。
- 重寫公開 README，介紹功能、相容條件、首次安裝與 GUI 使用方式；詳細設計移至 `docs/IMPLEMENTATION.md`。

## 1.0.0 — 2026-09-02

初始版本名稱為 Hitachi Dehumidifier，domain 為 `hitachi_dehumidifier`。提供標準除濕機實體、GUI 自動辨識／手動補選、Options Flow、多台裝置與改名追蹤。
