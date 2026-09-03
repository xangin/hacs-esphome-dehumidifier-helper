# 實作與相容性說明

本文件說明 ESPHome Dehumidifier Helper 的來源辨識與事件追蹤。使用與安裝方式見 [README](../README.md)。API 核對基準為 Home Assistant Core 2026.8.3。

## 自動辨識

先以 **device_id** 限定同一台裝置，再限制 **Entity Registry platform == esphome**、正確 domain、未停用。手動選單與後端驗證套用相同邊界，不能把另一台裝置的實體填進來。自動辨識排除 diagnostic 類別，但不會擅自啟用、隱藏或改名來源實體。

| 功能 | 自動判斷順序 |
| --- | --- |
| 目前濕度 | sensor 的 `original_device_class`、Registry `device_class` 或 State `device_class` 為 `humidity` 最優先；多個 humidity sensor 時以已知 original_name 和 `%` 再比較。沒有 humidity class 時才採明確濕度名稱。 |
| 電源 | switch 的 `original_name` 為「電源」、`Power` 或 `Power Switch`；否則僅有一個非診斷 switch 時可採用。 |
| 設定濕度 | number 的 `original_name` 為「設定濕度」、「目標濕度」、`Target Humidity` 或 `Relative Humidity`；其次採唯一 `%` number。 |
| 模式 | select 的 `original_name` 為「運轉模式」、`Operation Mode` 或 `Operating Mode`。 |
| 風量 | select／fan 的 `original_name` 為「風量」、「風速」、`Fan Speed`、`Fan Level` 或 `Fan`。 |

名稱只作去除多餘空白和不分英文大小寫的完整比對。**不從 entity_id 猜英文、拼音或 MAC suffix。** 同分候選不任選第一個，交由 GUI 手動選擇。不能把同一個 select 同時指定給模式和風量。

初版曾以 ST01 日立 ESPHome firmware 的下列來源定義檢查辨識規則；這是已知的對應範例，其他品牌可依相同角色結構使用：

| 既有設定 | 對應功能 |
| --- | --- |
| `Power Switch` | 電源 |
| `Humidity Indoor`，元件提供 humidity device class | 目前濕度 |
| `Relative Humidity` | 設定濕度 |
| `Operation Mode` | 模式 |
| 原生 `Fan` | 保留的風量控制 |

這份舊設定的 package project name 是 `SimonIoT.ST01-Hitachi-AC`，也能透過實體結構 fallback 辨識。這些名稱可沿用，不需要在 ESPHome YAML 增加 `original_name:` 欄位。

## 實體行為

| Humidifier 功能 | 來源／動作 |
| --- | --- |
| `turn_on` / `turn_off` | 呼叫來源的 `switch.turn_on` / `switch.turn_off`。 |
| `is_on` | 電源 switch 的 `on` / `off`；無有效狀態時回傳 None。 |
| `current_humidity` | sensor 的有限數值百分比。 |
| `target_humidity` | number 的有限數值百分比。 |
| `set_humidity` | 驗證範圍和 step 後呼叫 `number.set_value`，不默默四捨五入。 |
| `min_humidity` / `max_humidity` | number State attributes 的 `min` / `max`；缺少或無效時 fallback 40 / 80，集中在 const.py。 |
| `target_humidity_step` | number State attribute `step`；無有效正數則不提供。 |
| `mode` / `available_modes` | select 的 state / options，原樣保留中文模式字串。 |
| `set_mode` | 驗證目前 options 後呼叫 `select.select_option`。 |
| `available` | 裝置存在且啟用，三個必要來源存在、非 unknown/unavailable，power 與兩個濕度值均有效。 |
| `action` | 第一版不提供，回傳 None。沒有可靠的壓縮機／除濕活動來源，不推算 drying。 |

模式單獨 unavailable 時保留電源與濕度控制；模式 state 會回傳 None，來源無法使用時拒絕模式指令。整台裝置斷線時，主要 ESPHome entities unavailable 會使 humidifier unavailable。`unknown`、`unavailable`、None、非數字、NaN、無限大及超出 0–100 的濕度均安全處理。

狀態完全來自 HA State Machine，不做 optimistic 更新、不保存另一份目標濕度或模式。`blocking=True` 是**等待 HA 非同步服務結果**，不是 blocking I/O；來源服務錯誤正常往上回報，並保留 HA 的操作 context。

使用 `async_track_state_change_event` 追蹤四個主要來源，收到事件立即 `async_write_ha_state()`。卸載時取消所有 listener；沒有固定 update interval、輪詢或直接 ESPHome API 客戶端。

## 改名、重新載入與資料格式

Config Entry data 保存 `device_id`、五個 `*_entity_id`，另外保存 `source_refs`：每個來源的 Registry UUID、domain、platform、unique_id。

```json
{
  "device_id": "<device registry id>",
  "power_entity_id": "switch.<currently resolved id>",
  "humidity_entity_id": "sensor.<currently resolved id>",
  "target_humidity_entity_id": "number.<currently resolved id>",
  "mode_entity_id": "select.<currently resolved id>",
  "fan_entity_id": null,
  "source_refs": {
    "power_entity_id": {
      "registry_id": "<entity registry uuid>",
      "domain": "switch",
      "platform": "esphome",
      "unique_id": "<opaque source unique id>"
    }
  }
}
```

以上僅示意格式，不需手動編輯。Options 保存完整選擇，包含明確的 null，避免清空 optional 欄位後又套回舊綁定。

來源改 `entity_id` 時，Registry 事件依 UUID／unique ID 解析新 ID，更新 Config Entry 和 listener。每次重載與每次送出指令也重新解析。來源暫時停用或移除時保留穩定 reference；恢復相同 unique ID 的來源可重新接上。舊 entity_id 被另一個實體使用時，不會以舊字串誤控它。

Config Flow unique ID 依序取 ESPHome Device Registry identifier、Registry network MAC connection、device UUID。這裡的 MAC 直接來自 Registry，是不透明身分值；完全不解析名稱 suffix。另以 device_id 防止同裝置重複加入，HA 的 flow unique ID 機制也會阻擋同裝置的並行設定流程。

如果刪掉**整個 ESPHome device registry 項目**後再重新加入，device_id 可能改變；本版不會自動跨裝置重綁，需刪除此 wrapper 的 config entry 後重建。這和單純修改實體名稱／entity_id 不同。

## 目前 HA API 的限制與採用方式

1. **完整 project name**：Device Registry 沒有正式 project_name 欄位。HA 2026.8.3 ESPHome 將 project 名稱拆成 manufacturer/model；本版把 `simon_iot` + `hitachi_dehumidifier` 當優先提示，不宣稱這是完整 project name 的可靠還原。仍列出具備 switch + sensor + number 結構的其他 ESPHome 裝置，讓舊 firmware 可手動確認。這種結構可能也符合其他 ESPHome 設備，使用者仍須選自己的除濕機。未讀 ESPHome runtime_data/private API。
2. **精確裝置清單**：DeviceSelector 沒有 `include_devices` allow-list，不能直接表達本版的 Registry 結構篩選。本版使用官方 `SelectSelector` 顯示裝置名稱與 device_id；實體選擇使用官方 `EntitySelector` 的 `filter` 和 `include_entities`，並再做後端驗證。無候選時使用空的 SelectSelector，避免 `include_entities=[]` 意外變成無限制清單。
3. **Device 關聯**：直接指定公開的 Entity `device_entry`，和 HA 內建 `switch_as_x` 一致，掛回原有 ESPHome Device。沒有新增衝突 identifiers、沒有改寫 manufacturer。`MANUFACTURER = "Simon IoT"` 與 MODEL 已集中保留在 constants，但現有 Device 的 metadata 由 ESPHome 整合維護，不會為了套這兩個值而覆蓋原 Device。
4. **Fan speed**：`HumidifierEntityFeature` 目前只有 MODES；風量保留原實體。
5. **Step 與小數設定值**：目前正式支援 `target_humidity_step`，本版直接映射。但 HA 2026.8.3 的 `humidifier.set_humidity` 服務仍會轉成整數；如果未來 firmware 需要小數目標，須用原 number 實體操作。本版不自訂替代 Humidifier API。
6. **模式名稱**：官方允許自訂 mode 字串，因此不把中文模式硬轉成固定英文 enum。若某硬體模式禁止調整濕度，是否切換模式取決於 firmware；本版不猜測哪個模式適合調濕。
7. **Action**：`HumidifierAction.DRYING/IDLE/OFF` 已核對，但現有水箱滿／除霜訊號無法可靠證明正在除濕。擴充時應新增明確來源 role/reference，再實作 `action` property，不以濕度比較推估。

`DOMAIN`、`NAME`、`MANUFACTURER`、`MODEL`、`KNOWN_ESPHOME_PROJECTS` 與名稱別名集中在 `const.py`。HA 必須在載入 Python 前讀取靜態 manifest，因此 domain/name 也必須同步更新目錄、manifest、hacs.json 與 translations；`scripts/validate.py` 會檢查主要欄位一致性。

## 核對來源

- [HA 2026.8.3 release](https://github.com/home-assistant/core/releases/tag/2026.8.3)
- [Humidifier Entity 官方文件](https://developers.home-assistant.io/docs/core/entity/humidifier/) 與 [2026.8.3 原始碼](https://github.com/home-assistant/core/blob/2026.8.3/homeassistant/components/humidifier/__init__.py)
- [Config Flow](https://developers.home-assistant.io/docs/core/integration/config_flow/)／[Options Flow](https://developers.home-assistant.io/docs/core/integration/options_flow/)
- [Entity Registry](https://github.com/home-assistant/core/blob/2026.8.3/homeassistant/helpers/entity_registry.py)／[Device Registry](https://github.com/home-assistant/core/blob/2026.8.3/homeassistant/helpers/device_registry.py)
- [2026.8.3 Selectors](https://github.com/home-assistant/core/blob/2026.8.3/homeassistant/helpers/selector.py)／[事件 helpers](https://github.com/home-assistant/core/blob/2026.8.3/homeassistant/helpers/event.py)
- [ESPHome 裝置 metadata](https://github.com/home-assistant/core/blob/2026.8.3/homeassistant/components/esphome/manager.py)／[switch_as_x Device 關聯方式](https://github.com/home-assistant/core/blob/2026.8.3/homeassistant/components/switch_as_x/entity.py)
- [HACS integration repository 規範](https://www.hacs.xyz/docs/publish/integration/)／[本地 brand 圖示](https://developers.home-assistant.io/docs/core/integration/brand_images/)
- [Template Humidifier 參考](https://github.com/tsunglung/hass_humidifier_template)：只參考功能範圍；此專案獨立實作 GUI Config Entry 架構。
