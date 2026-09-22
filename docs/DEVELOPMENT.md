# Развитие русификатора

Рабочая база проекта задаётся корневым `project.json`. Все сохранённые пути
относительны корню репозитория; ISO пользователь передаёт командам отдельно через
`--input`.

Идентификатор проекта хранится в `project.json`; отдельного манифеста выпуска или
предварительно собранного патча нет.

## Базовые проверки

```powershell
python -B tools/project.py status
python -B tools/project.py audit
python -B tools/verify_distribution.py
```

`audit` сверяет 43 ресурса с `resources/manifest.json`, разбирает контейнеры,
выполняет round-trip всех RDR и строго проверяет 95 таблиц анимаций. ISO для этого
не нужен. `verify_distribution.py` без `--input` проверяет состав корневого
установщика; с `--input` дополнительно выполняет прямую сборку в режиме проверки
без записи ISO.

## Редактируемые материалы

- `sources/rdr/` — снимки 291 раздела RDR в JSON;
- `sources/compiled/` — локально генерируемые и игнорируемые Git справочные каталоги имён ZANIM/ZWEAPON;
- `sources/executable/` — проверенные видимые строки EXE;
- `sources/dictionaries/` — словари и принятые точечные исправления;
- `resources/files/` — единственный источник готовых бинарных ресурсов выпуска.

JSON хранится как UTF-8, но игровой текст использует собственные однобайтовые
кодировки. Для преобразований применять `tools/text_encoding.py`. Не заменять
Latin-1-представление игровых байтов обычной кириллицей.

Обновить редактируемые снимки из текущих ресурсов:

```powershell
python -B tools/resources.py export
```

## Новая ветка с правкой

1. Обновить `main` и создать отдельную ветку с коротким осмысленным именем:

   ```powershell
   git switch main
   git switch -c fix/short-description
   ```

2. Для изменения одного RDR отредактировать его JSON и применить правку к
   соответствующему ресурсу в текущей ветке:

   ```powershell
   python -B tools/resources.py apply --input "sources/rdr/.../file.rdr.json"
   ```

   Команда проверяет SHA-256 исходной ревизии, выполняет runtime round-trip,
   обновляет ресурс, его строку в `resources/manifest.json` и контрольные суммы
   редактируемого JSON. Предыдущая версия остаётся доступна в Git.

3. Для сложной правки использовать функции из `tools/socom_formats.py` и
   обязательно выполнить `rdr_runtime.runtime_roundtrip`. Для ZANIM перед сборкой
   вызвать `animation_runtime.inspect(data, True)`.
4. Проверить изменения и просмотреть diff:

   ```powershell
   python -B tools/project.py audit
   git status --short
   git diff --stat
   ```

5. Если менялись ресурсы других типов, согласованно обновить их записи в
   `resources/manifest.json` и соответствующие материалы `sources/`. После
   проверки закоммитить ветку и передать её на review/слияние.

## Обновление выпуска

После принятия ресурсов обновить версию и ожидаемые контрольные суммы в
`project.json`. Сборка всегда читает актуальные `resources/files/` и
`resources/manifest.json`; отдельный накопительный патч не создаётся.

Полная проверка перед выпуском:

```powershell
python -B tools/project.py audit
python -B tools/project.py verify --input ".\SOCOM-original.iso"
python -B tools/verify_distribution.py --input ".\SOCOM-original.iso" --full-install
```

Проверка `--full-install` создаёт временный ISO в системной временной папке,
сверяет все 678 файлов и 70 неизменённых файлов звука/видео/распознавания, а затем
удаляет временные данные. Для отдельного ручного образа:

```powershell
python -B tools/project.py build --input ".\SOCOM-original.iso" --output ".\SOCOM-test-ru.iso"
```

Существующий выходной файл не перезаписывается. Не хранить в репозитории ISO,
`reports/`, `*.partial`, `*.pindex.tmp` или кэши Python. Историю правок
вести через ветки и коммиты Git, не через параллельные архивы ресурсов.
