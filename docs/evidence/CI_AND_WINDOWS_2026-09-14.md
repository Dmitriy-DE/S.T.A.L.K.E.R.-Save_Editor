# Зелёная матрица и первая Windows-сборка — 2026-09-14

Владелец включил GitHub Actions. Ниже — что показали первые реальные прогоны и
что в них было починено. Все находки — настоящие дефекты, а не «подгон под CI».

## Матрица тестов

`tests` на `ubuntu-24.04` и `windows-2025` × Python 3.11/3.12 — **4/4 success**
(run `51e496e`). До этого прогон не доходил до шагов ни разу.

| Находка | Где | Суть |
|---|---|---|
| `startup_failure` без jobs | обоих workflow | метки runner указывали на снятые с обслуживания образы |
| SyntaxError на шаге компиляции | `test.yml` | шаг объявлял `shell: python`, а телом была shell-команда. Ошибка существовала с момента написания workflow и не проявлялась, потому что прогон до неё не доходил |
| 6 ошибок типов в Qt-коде | `ui/inventory_model.py`, `ui/main_window.py` | `mypy` в CI видит настоящие типы Qt; локальный venv без Qt всё смягчал. `rowCount`/`columnCount`/`flags`/`data` объявляли только `QModelIndex`, хотя Qt передаёт и `QPersistentModelIndex` — нарушение Liskov |
| Qt-сьют без дисплея | обоих workflow | PySide6 стал runtime-зависимостью → UI-тесты пошли на раннеры. Добавлены `QT_QPA_PLATFORM=offscreen` и системные библиотеки Qt |
| 8 падений на Windows | тесты | `.py` нельзя запустить как исполняемый файл (WinError 193) — fake helper обёрнут в `.cmd`; POSIX execute bit не существует на NTFS — тест пропускается с указанием причины |
| Молчаливый отказ preview и Cloud | `ui/main_window.py`, `ui/cloud_view.py` | сигнал воркера приходит раньше, чем завершается его поток; действия отказывались стартовать «пока занято» **молча**. На быстрой машине окно незаметно, на раннере — 30 секунд ожидания сигнала, которого никто не пошлёт |

Последний пункт — продуктовый дефект, а не тестовый: кнопка, которая ничего не
делает и ничего не говорит, неотличима от сломанной. Теперь и окно, и Cloud-вкладка
сообщают, почему отказали.

## Первая сборка под Windows

`standalone-build` на `windows-2025`, Python 3.11 — **success**, включая
`SaveEditor-diagnostic.exe --diagnostic` на самом раннере.

Находка: `packaging/editor.spec` искал свои entry points по
`endswith("packaging/gui_entry.py")`. На Windows PyInstaller отдаёт
`packaging\gui_entry.py`, и сборка падала в середине с голым `StopIteration`.

Артефакты run `f506836`:

```text
7cdfeedb24204c14cb2772223df5e3b5ff7c63a8d9bf7b4a031a91da7acb3520  SaveEditor-windows-x86_64-v0.3.0-experimental.zip
60ffec5ef7a21dfd5536ce71fe263a5cb590c3a812c47cd4bbaa33efc3df17d5  SaveEditor-linux-x86_64-v0.3.0-experimental.tar.gz
781e9332c55fa495f00b00eb1d2839d8cf711858c5559e542b72c93feb6162f1  stalker2-save-editor_0.3.0-experimental_amd64.deb
```

Windows zip: 51 MB, 249 файлов, внутри `SaveEditor.exe` и
`SaveEditor-diagnostic.exe`. Эти хэши относятся к сборке **до** правки манифеста
ниже, поэтому релизными не являются.

Ещё одна находка в манифесте: `source_dirty: true` при чистом checkout. Причина
— каталог вывода `artifacts/` лежит внутри дерева, и собственные продукты сборки
попадали в отчёт как изменения источника. Проверка теперь исключает каталог
вывода.

## Что всё ещё не проверено

- Запуск `SaveEditor.exe` на живом Windows-десктопе: раннер проверил только
  консольный diagnostic, окно на реальном сеансе никто не открывал.
- DPI 100/150/200 % и клавиатура.
- Реальные Steam и GeForce NOW: загрузка, повторное сохранение в игре.
