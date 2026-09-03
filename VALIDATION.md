# 交付驗證紀錄

日期：2026-09-03。整合版本：1.1.0。官方 API 基準：Home Assistant Core 2026.8.3。

依 Simon 指示，完成本機檢查，實際 HA 安裝與硬體驗收由 Simon 執行。沒有安裝 HA 測試套件、沒有寫入連線中的 HA、沒有控制實際除濕機，也沒有執行或更動 ESPHome 環境。

## 已執行

| 項目 | 結果與範圍 |
| --- | --- |
| Python syntax / compile | Python 3.14.6；compileall 及逐檔 compile 成功。 |
| manifest 格式 | JSON 可解析；必要欄位、型別、domain/目錄/常數一致性、版本、dependencies、config_flow、integration_type、iot_class 檢查成功。URL 格式檢查成功，不代表預定 repository 已發布。 |
| HACS 靜態格式 | 單一 custom_components 子目錄、hacs.json、最低 HA 版本與本地 256×256 PNG 通過。 |
| 翻譯 | strings、en、zh-Hant 的 key 與 placeholders 一致；JSON 全部可解析。 |
| 離線邏輯檢查 | `python3.14 -m unittest discover -s tests -v`：21 項通過。採記憶體 Registry doubles，未模擬完整 HA。 |
| 舊 API 搜尋 | 元件 Python 原始碼未使用舊 async_track_state_change、單數 async_forward_entry_setup、SUPPORT_MODES、DEVICE_CLASS_DEHUMIDIFIER、async_setup_platform、SCAN_INTERVAL、update_interval，或指派 OptionsFlow.config_entry。 |
| 身分查找檢查 | 無 entity_id 名稱／拼音／MAC suffix 推測；entity_id 只用於從 HA 讀 state、服務目標、顯示和 Registry 事件。 |
| 安裝包 | package.py 逐一比對 ZIP 成員與原始檔 bytes，並產生整包 SHA-256。 |

離線檢查不等於官方 hassfest 通過。本次未執行官方 hassfest、HACS 遠端 action、HA 平台載入或 GUI 互動；已提供 GitHub workflow，發布 repository 後可執行。

## 1.1.0 命名與文件檢查

- 本機資料夾已改為 `hacs-esphome-dehumidifier-helper`，component 目錄與 domain 一致使用 `esphome_dehumidifier_helper`。
- Manifest、HACS 名稱與英文翻譯一致為 ESPHome Dehumidifier Helper；繁體中文為「ESPHome 除濕機助手」。
- Documentation 與 issue tracker 指向 `xangin/hacs-esphome-dehumidifier-helper`。
- 已知的日立 firmware project identifier 保留作為相容提示，不會被替換為助手的 domain。
- README 以功能介紹、相容條件、首次安裝與 GUI 使用為主；詳細技術說明另放於 `docs/IMPLEMENTATION.md`。

## 多台裝置與改名的特別檢查

- 三個必要來源的候選、手動選單和後端驗證都有同一個 device_id 邊界；測試兩台名稱與角色相同的 ESPHome device，不會交叉選取。
- Config Flow 每台裝置使用獨立穩定 unique ID，並呼叫 HA 官方文件列出的 `async_set_unique_id`／`_abort_if_unique_id_configured`；另以 device_id 防止 identity metadata 變動後重複新增。
- 第二次新增會排除已設定 device_id。相同裝置同時開啟兩個 flow 時，交由 HA 的 unique ID 並行機制阻擋；此部分已檢閱程式與官方 API，尚待 HA GUI 驗收。
- 改來源 entity_id 後，以原 Registry UUID 解析新名稱；測試同步 Config Entry data/options，以及用保存後的 entry 重新解析，結果一致。
- 原 Registry 項目重新建立、UUID 變動但 unique ID 不變時可恢復。若舊 entity_id 指向不同 unique ID，測試確認不會誤控替代實體。
- 暫時 disable 時保留 reference；重新 enable 後恢復解析。清除 optional mode 後，data/options/ref 同步清除，不會重新套用舊設定。

## 程式審查要點

- HumidifierDeviceClass.DEHUMIDIFIER、HumidifierEntityFeature.MODES、HumidifierAction、target_humidity_step 依官方 2026.8.3 原始碼確認。
- modes 直接傳遞 select options／state，無固定英文 enum 假設。
- 開關／number／select 控制走 HA async service，沒有直接連 ESPHome、MQTT 或額外通訊。
- `async_track_state_change_event` 監控來源；Registry event 監控改名與移除／恢復；device event 監控裝置狀態變動。所有訂閱均經 entity 的 unload/remove 生命週期解除。
- Availability 取三個必要來源、裝置存在與停用狀態；無效數值回傳 None，不會拋數值轉換 exception。
- Device 關聯沿用官方 switch_as_x 的 device_entry 用法。無手動修改 registry identifier、manufacturer 或原 ESPHome Entity Registry 欄位。
- Options Flow 使用 OptionsFlowWithReload，沒有自訂寫入唯讀 config_entry 或過期的 OptionsFlow 初始化範例。

## Simon 的實際驗收

1. 複製 custom_components 資料夾、重新啟動 HA，確認整合可在「新增整合」找到。
2. 選一台具備必要來源的 ESPHome 除濕機裝置，確認自動對應及中文頁面；完成後確認 humidifier 出現在同一個 Device。
3. 開／關、改目標濕度、改模式，確認原 ESPHome entity 和實際除濕機收到動作，回報後同步到 humidifier。
4. 從原 ESPHome entities 修改開關／number／select，確認 humidifier 立即反映；改 sensor state 時確認 current humidity 同步。
5. 在 HA 改 power、humidity、target、mode 的顯示名稱與 entity_id，再操作 humidifier；重新載入整合與重啟 HA 後再檢查一次。
6. 停用／重新啟用來源，或讓 ESPHome 斷線／恢復連線，確認 unavailable 與恢復行為；來源 `unknown`／`unavailable` 不應留下舊濕度值。
7. 加入第二／第三台裝置，確認互不控制，且同台不能重複新增。
8. 在選項頁更換來源；清除 mode，確認 modes feature 消失、基本控制保留。再加回 mode，確認功能恢復。
9. 手動 fallback 頁確認只能選本台、正確 domain 的來源；有多個同名來源時應要求選擇。
10. 確認原風量 select／fan 仍可操作；humidifier 沒有猜測的 drying action。

如果整合找不到，先確認檔案層級與 HA 版本。若找不到裝置，確認 ESPHome 已加入、必要來源未停用；缺少 humidity device_class 時可用 original_name 或 GUI 手動指定。檢查「設定 → 系統 → 日誌」中的 esphome_dehumidifier_helper 訊息即可回報，不需開啟 ESPHome 輪詢。
