# ESPHome Dehumidifier Helper

**將 ESPHome 裝置的既有實體，整合成一個 Home Assistant 標準除濕機。**

A Home Assistant custom integration that combines existing ESPHome entities into a standard dehumidifier entity, with automatic discovery and GUI configuration.

ESPHome 除濕機接入 Home Assistant 後，電源、濕度、設定濕度和模式通常各自是一個實體。這個助手把它們組合成 `humidifier.xxx`，讓你從同一個除濕機介面查看濕度、開關電源、設定目標與切換模式，也能用 HA 標準除濕機動作建立自動化。

**適用範圍由 ESPHome 實體結構決定，品牌不限於日立。** 裝置必須先透過 Home Assistant 內建 ESPHome 整合接入；本助手使用那些已存在的實體完成控制。

```text
除濕機 → ESPHome Native API → Home Assistant ESPHome 整合
                                      │
                                      ├─ switch：電源
                                      ├─ sensor：目前濕度
                                      ├─ number：設定濕度
                                      ├─ select：運轉模式（選用）
                                      └─ select / fan：風量（保留原實體）
                                      │
                         ESPHome Dehumidifier Helper
                                      │
                      humidifier.xxx（dehumidifier）
```

## 能做什麼

- 建立官方 `HumidifierEntity`，裝置類別為 `dehumidifier`。
- 開關電源、顯示目前濕度、查看和設定目標濕度。
- 自動讀取來源 number 的濕度上下限與步進值。
- 有模式 select 時，直接使用它的模式選項，包含中文名稱。
- GUI 選擇裝置後自動辨識來源；只有無法判斷的項目才需要手動選擇。
- 提供選項頁，之後可以修正實體對應，無需刪除整合重建。
- 支援多台 ESPHome 除濕機、裝置名稱的 MAC suffix、來源實體改名與整合重新載入。
- 即時追蹤 HA 狀態事件；主要來源失聯時，除濕機也顯示無法使用。
- 建立的 humidifier 掛在原本的 ESPHome 裝置下。
- 提供英文和繁體中文介面，支援 HACS Custom Repository 安裝。

所有設定都在 HA GUI 完成，不需修改 `configuration.yaml`、使用 MQTT，或更換既有 ESPHome Native API 連線。

## 相容條件

最低需求：**Home Assistant Core 2026.6.0 以上**。已依 [2026.6.0 官方原始碼](https://github.com/home-assistant/core/blob/2026.6.0/homeassistant/components/humidifier/__init__.py) 核對 Humidifier、濕度步進、Config Flow、Options Flow、Registry 與事件追蹤 API。

同一台 ESPHome 裝置下，至少要有三個已啟用、可用的實體：

| 功能 | 必要性 | 來源類型 | 名稱範例 |
| --- | --- | --- | --- |
| 電源 | 必要 | `switch` | 電源、Power、Power Switch |
| 目前濕度 | 必要 | `sensor` | 濕度、Humidity；建議帶有 humidity device class |
| 設定濕度 | 必要 | `number` | 設定濕度、Target Humidity、Relative Humidity |
| 運轉模式 | 選用 | `select` | 運轉模式、Operation Mode |
| 風量 | 選用 | `select` 或 `fan` | 風量、Fan Speed、Fan |

實體名稱可以不同；無法自動辨識時，可在 GUI 指定。候選來源限定在選取的 ESPHome 裝置內，避免混用其他除濕機的實體。

如果 firmware 用 `fan` 的開關代表整機電源，或用 `select` 代表目標濕度，目前還不能直接套用；需要先擴充來源類型的對應方式。**本版僅建立除濕機，不提供加濕機類別。**

## 安裝

### 方法一：HACS Custom Repository

1. 先安裝並設定 HACS。
2. 在 HACS 右上角選單開啟「自訂儲存庫」。
3. 輸入以下 repository URL，類型選擇「整合」：

   ```text
   https://github.com/xangin/hacs-esphome-dehumidifier-helper
   ```

4. 在 HACS 搜尋 **ESPHome Dehumidifier Helper**，下載整合。
5. 重新啟動 Home Assistant。
6. 依下方「第一次設定」新增整合。

### 方法二：手動安裝

1. 從 [Releases](https://github.com/xangin/hacs-esphome-dehumidifier-helper/releases) 下載安裝 ZIP，或使用 GitHub 的 **Code → Download ZIP** 下載原始碼。
2. 解壓後，將 `custom_components/esphome_dehumidifier_helper` 整個資料夾複製到 HA 設定目錄下的 `custom_components/`。
3. 確認最終檔案位於：

   ```text
   /config/custom_components/esphome_dehumidifier_helper/manifest.json
   ```

4. 重新啟動 Home Assistant，再進行第一次設定。

請勿把整個 repository 資料夾直接當作 component 複製；HA 必須能在上述位置讀到 manifest。

## 第一次設定

1. 確認除濕機已經透過 HA 的 ESPHome 整合加入，原本的電源、濕度和設定濕度實體可以正常使用。
2. 開啟 **設定 → 裝置與服務 → 新增整合**。
3. 搜尋 **ESPHome Dehumidifier Helper**；繁體中文介面顯示「**ESPHome 除濕機助手**」。
4. 在「選擇 ESPHome 除濕機」下拉選單選擇你的裝置。
5. 助手會分析該裝置的來源實體：
   - 能自動辨識時，顯示「已偵測到以下實體」，檢查後提交即可。
   - 有缺少或多個候選時，顯示需要手動選擇的欄位。
   - 模式和風量可留空；確認頁的「—」表示未使用該項來源。
6. 完成後，回到原本的 ESPHome 裝置頁，找到新增的除濕機實體。

實際 `entity_id` 由 Home Assistant 依名稱、語系與現有實體產生，不固定為某個字串。每台除濕機各新增一次整合，設定彼此獨立。

## 日常使用

在新增的除濕機實體中，你可以開關電源、查看目前與目標濕度、調整目標濕度，以及切換來源 select 提供的模式。也可以在儀表板加入這個實體，或在自動化 GUI 使用標準的除濕機開啟、關閉、設定濕度和設定模式動作。

從原本 ESPHome 實體操作，或設備回報新狀態時，助手也會即時同步。它以來源回報為準，不會自行保存另一份電源、濕度或模式狀態。

**風量繼續由原本 ESPHome 的 select／fan 操作。** Humidifier 的官方 API 沒有風速功能，本版僅記錄這項對應供未來擴充，不另外建立風速服務。

### 修正來源對應

開啟 **設定 → 裝置與服務 → ESPHome Dehumidifier Helper → 該裝置的設定／選項**，即可重新指定電源、目前濕度、設定濕度、模式與風量。清空選填欄位可停用該綁定，提交後整合自動重新載入。

來源 entity_id 或顯示名稱變更時，助手會透過保存的 Registry 身分重新追蹤，通常不需重新設定。

## 如何自動辨識

辨識依據是選定裝置的 **device_id、ESPHome platform、實體 domain、device class、original_name 與狀態屬性**。它不會把 `humidity`、中文拼音或 MAC suffix 當作 entity_id 的查找條件。

濕度優先以 humidity device class 判斷；電源、目標濕度、模式和風量會使用已知原始名稱。唯一的 switch 可作為電源 fallback，唯一帶 `%` 的 number 可作為目標濕度 fallback。無法唯一判斷時交由使用者選擇。

日立 ST01 的既有中英文名稱與 firmware project 提示仍保留。其他品牌不需要冒用日立名稱或修改 firmware project：只要符合上述實體結構，就能使用通用辨識及手動對應。已知 project metadata 僅作為候選提示，不是品牌限制。

## 已知限制

- 本助手整理已存在的控制介面；硬體接線、除濕機通訊與 ESPHome firmware 需先正常運作。
- 裝置清單依 ESPHome 實體結構篩選，可能包含結構相似的其他設備；請選擇實際的除濕機。
- HA Device Registry 沒有公開的完整 ESPHome project name 欄位，已知 project 只能透過公開 metadata 作為提示。
- 目前沒有可靠的壓縮機活動來源，因此不提供 `drying` 等 action，也不根據濕度差猜測是否正在除濕。
- 濕度 min/max/step 優先取自來源 number；缺少或無效時，範圍 fallback 為 40–80%。HA 2026.6.0 的標準設定濕度服務仍使用整數；需要小數目標時請操作原 number。
- 模式單獨失聯時，基本電源與濕度控制仍可使用；主要來源失聯或濕度值無效時，整個 humidifier 會顯示無法使用。
- 刪除整個 ESPHome 裝置後再加入，device_id 可能改變，需要重新建立助手設定。單純實體改名不受此限制。

## 專案資訊

| 項目 | 值 |
| --- | --- |
| GitHub repository | `xangin/hacs-esphome-dehumidifier-helper` |
| 整合名稱 | ESPHome Dehumidifier Helper |
| HA domain | `esphome_dehumidifier_helper` |
| 目前版本 | `1.1.1` |
| 最低 Home Assistant Core | `2026.6.0` |

### 找不到裝置或無法完成設定？

先確認 ESPHome 裝置已加入 HA，且電源 switch、濕度 sensor、設定濕度 number 都已啟用。來源名稱不同時可以手動指定；必要來源不存在時，需先讓 firmware 提供對應的實體。

若仍有問題，請至 [Issues](https://github.com/xangin/hacs-esphome-dehumidifier-helper/issues) 提供 HA 版本、助手版本、來源實體類型及相關錯誤日誌。

## 授權

[MIT License](LICENSE) · [xangin](https://github.com/xangin)
