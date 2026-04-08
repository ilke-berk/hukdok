# Backend Refactor Planı

## Hedef Klasör Yapısı

### `extractors/`
- [x] `court_extractor.py`
  - `analyzer.py:405` → `from extractors.court_extractor import find_court_name`
- [x] `date_extractor.py`
  - `analyzer.py:377` → `from extractors.date_extractor import find_best_date`
- [x] `esas_no_extractor.py`
  - `analyzer.py:386` → `from extractors.esas_no_extractor import find_best_esas_no`
- [x] `lawyer_extractor.py` — silindi (hiçbir yerde kullanılmıyordu)

### `sharepoint/` Notu
> `counter_manager.py` ve `log_manager.py` ileride `managers/` klasörüne taşınacak. Bu dosyalardaki importlar **iki kez** değişecek: önce sharepoint taşınırken, sonra managers taşınırken.

### `managers/`
- [x] `admin_manager.py`
  - `admin_manager.py:6` → `from managers.config_manager import DynamicConfig` *(kendi içinde config_manager'a bağımlı)*
  - `routes/cases.py:11` → `from managers.admin_manager import ...`
  - `routes/config.py:8` → `from managers.admin_manager import ...`
  - `routes/processing.py:58` → `from managers.admin_manager import ...`
  - `routes/clients.py:8` → `from managers.admin_manager import add_client`
- [x] `cache_manager.py`
  - `api.py:70` → `from managers import cache_manager`
  - `routes/processing.py:59` → `import managers.cache_manager as _cache_manager`
- [x] `config_manager.py`
  - `config_manager.py:7` → `from managers.log_manager import TechnicalLogger` *(kendi içinde log_manager'a bağımlı)*
  - `api.py:15` → `from managers.config_manager import get_log_dir`
  - `api.py:57` → `from managers.config_manager import DynamicConfig`
  - `analyzer.py:91` → `from managers.config_manager import DynamicConfig`
  - `client_normalizer.py:62` → `from managers.config_manager import get_data_dir`
  - `dependencies.py:9` → `from managers.config_manager import get_log_dir`
  - `file_utils.py:215` → `from managers.config_manager import DynamicConfig`
  - `lawyer_extractor.py:3` → `from managers.config_manager import DynamicConfig`
  - `routes/config.py:7` → `from managers.config_manager import DynamicConfig`
  - `routes/processing.py:18` → `from managers.config_manager import DynamicConfig`
- [x] `counter_manager.py`
  - `counter_manager.py:16` → `from managers.log_manager import TechnicalLogger` *(kendi içinde)*
  - `routes/processing.py:317` → `from managers.counter_manager import get_counter_manager`
  - `routes/processing.py:498` → `from managers.counter_manager import get_counter_manager`
- [x] `log_manager.py`
  - `api.py:58` → `from managers.log_manager import LogManager, TechnicalLogger`
  - `analyzer.py:18` → `from managers.log_manager import TechnicalLogger`
  - `file_utils.py:12` → `from managers.log_manager import TechnicalLogger`
  - `pdf/pdf_converter.py:16` → `from managers.log_manager import TechnicalLogger`
  - `udf_converter.py:31` → `from managers.log_manager import TechnicalLogger`
  - `routes/processing.py:19` → `from managers.log_manager import TechnicalLogger`
  - `routes/processing.py:499` → `from managers.log_manager import LogManager`

### `sharepoint/`
- [x] `auth_graph.py`
  - import güncellenmesi gereken:
    - `counter_manager.py:14` → `from sharepoint.auth_graph import get_graph_token`
    - `email_sender.py:17` → `from sharepoint.auth_graph import get_graph_token`
    - `log_manager.py:9` → `from sharepoint.auth_graph import get_graph_token`
    - `sharepoint_uploader_graph.py:9` → `from sharepoint.auth_graph import get_graph_token` *(kendi klasörü içinde olacak, `.auth_graph` da olur)*
- [x] `sharepoint_uploader_graph.py`
  - import güncellenmesi gereken:
    - `counter_manager.py:15` → `from sharepoint.sharepoint_uploader_graph import _get_site_and_drive_id, _headers`
    - `log_manager.py:10` → `from sharepoint.sharepoint_uploader_graph import _get_site_and_drive_id, _headers`
    - `log_manager.py:181` → `from sharepoint.sharepoint_uploader_graph import upload_file_to_sharepoint`
    - `routes/processing.py:497` → `from sharepoint.sharepoint_uploader_graph import upload_file_to_sharepoint`

### `pdf/`
- [x] `pdf_converter.py`
  - `routes/processing.py:611` → `from pdf.pdf_converter import convert_to_pdfa2b`
- [x] `pdf_utils.py`
  - `analyzer.py:79,82` → `from pdf import pdf_utils` / `from .pdf import pdf_utils`

---

## Yerinde Kalacaklar

- `api.py`
- `analyzer.py`
- `database.py`
- `models.py`
- `schemas.py`
- `dependencies.py`
- `prompts.py`
- `vault.py`
- `file_utils.py`
- `text_utils.py`
- `case_matcher.py`
- `client_normalizer.py`
- `muvekkil_matcher_v2.py`
- `list_searcher.py`
- `udf_converter.py`
- `email_sender.py`
- `auth_verifier.py`

---

## Sıra

1. `extractors/` — bağımlılıkları az, iyi başlangıç
2. `sharepoint/` — counter ve log manager buna bağlı, önce bunlar taşınmalı
3. `managers/` — sharepoint taşındıktan sonra
4. `pdf/` — bağımsız, istediğinde
