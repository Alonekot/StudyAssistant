import os
import hashlib
import re
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ExifTags
import threading
import shutil

# ------------------------------------------------------------
# 1. Функции для извлечения даты из файла
# ------------------------------------------------------------

def get_date_from_exif(filepath):
    """Извлекает дату съёмки из EXIF (теги 36867 или 306)"""
    try:
        img = Image.open(filepath)
        exif = img._getexif()
        if exif:
            for tag, value in exif.items():
                tagname = ExifTags.TAGS.get(tag, '')
                if tagname in ('DateTimeOriginal', 'DateTimeDigitized', 'DateTime'):
                    # Ожидаем формат "YYYY:MM:DD HH:MM:SS"
                    try:
                        dt = datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                        return dt.date()
                    except:
                        continue
    except Exception:
        pass
    return None

def parse_date_from_filename(filename):
    """Пытается найти дату в имени файла по нескольким шаблонам"""
    patterns = [
        r'(\d{4})[-_.](\d{1,2})[-_.](\d{1,2})',  # YYYY-MM-DD или YYYY_MM_DD
        r'(\d{2})[-_.](\d{2})[-_.](\d{4})',      # DD-MM-YYYY
        r'(\d{8})',                              # YYYYMMDD
        r'(\d{6})',                              # YYMMDD
        r'(\d{2})[-_.](\d{2})[-_.](\d{2})',      # DD-MM-YY
    ]
    for pat in patterns:
        match = re.search(pat, filename)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                # Пытаемся определить порядок
                g1, g2, g3 = groups
                # Если g1 длиной 4 – это год, значит YYYY-MM-DD
                if len(g1) == 4:
                    try:
                        return datetime.date(int(g1), int(g2), int(g3))
                    except:
                        pass
                elif len(g3) == 4:
                    # DD-MM-YYYY
                    try:
                        return datetime.date(int(g3), int(g2), int(g1))
                    except:
                        pass
                else:
                    # DD-MM-YY или YY-MM-DD, пробуем оба
                    # Сначала попробуем DD-MM-YY
                    try:
                        year = 2000 + int(g3) if int(g3) < 70 else 1900 + int(g3)
                        return datetime.date(year, int(g2), int(g1))
                    except:
                        pass
                    # Пробуем YY-MM-DD
                    try:
                        year = 2000 + int(g1) if int(g1) < 70 else 1900 + int(g1)
                        return datetime.date(year, int(g2), int(g3))
                    except:
                        pass
            elif len(groups) == 1:
                # Число из 6 или 8 цифр
                s = groups[0]
                if len(s) == 8:
                    try:
                        return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
                    except:
                        pass
                elif len(s) == 6:
                    try:
                        year = 2000 + int(s[:2]) if int(s[:2]) < 70 else 1900 + int(s[:2])
                        return datetime.date(year, int(s[2:4]), int(s[4:6]))
                    except:
                        pass
    return None

def get_date_from_mtime(filepath):
    """Возвращает дату модификации файла (только дата)"""
    try:
        ts = os.path.getmtime(filepath)
        return datetime.datetime.fromtimestamp(ts).date()
    except:
        return None

def get_best_date(filepath):
    """
    Определяет дату съёмки с приоритетом: EXIF > имя > mtime.
    Возвращает объект date или None, если ничего не найдено.
    """
    d = get_date_from_exif(filepath)
    if d:
        return d
    d = parse_date_from_filename(os.path.basename(filepath))
    if d:
        return d
    d = get_date_from_mtime(filepath)
    return d

# ------------------------------------------------------------
# 2. Функции поиска дубликатов
# ------------------------------------------------------------

def compute_sha256(filepath, block_size=8192):
    """Вычисляет SHA-256 хэш файла (читает блоками)"""
    sha = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(block_size), b''):
                sha.update(chunk)
        return sha.hexdigest()
    except:
        return None

def find_duplicates(folders, progress_callback=None):
    """
    Обходит папки, собирает все файлы-изображения (по расширениям),
    группирует по размеру, затем по хэшу.
    Возвращает словарь: {hash: [list_of_filepaths]}
    """
    # Расширения, которые считаем фото (можно расширить)
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.heic'}
    # Собираем все файлы с этими расширениями
    all_files = []
    total = 0
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for root, _, files in os.walk(folder):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in image_extensions:
                    fullpath = os.path.join(root, f)
                    size = os.path.getsize(fullpath)
                    all_files.append((fullpath, size))
                    total += 1
                    if progress_callback:
                        progress_callback(total, 0)  # обновим позже

    # Группируем по размеру
    size_groups = {}
    for path, size in all_files:
        size_groups.setdefault(size, []).append(path)

    # Для каждой группы с размером >1 вычисляем хэш
    duplicates = {}  # hash -> list of paths
    processed = 0
    total_to_hash = sum(len(v) for v in size_groups.values() if len(v) > 1)

    for size, paths in size_groups.items():
        if len(paths) <= 1:
            continue
        hash_groups = {}
        for p in paths:
            h = compute_sha256(p)
            if h:
                hash_groups.setdefault(h, []).append(p)
            processed += 1
            if progress_callback:
                progress_callback(processed, total_to_hash)
        # Оставляем только те хэши, где больше одного файла
        for h, plist in hash_groups.items():
            if len(plist) > 1:
                duplicates[h] = plist

    return duplicates

# ------------------------------------------------------------
# 3. Функции удаления и переименования
# ------------------------------------------------------------

def delete_files(file_list, ask=True):
    """Удаляет файлы, запрашивая подтверждение (если ask=True)"""
    if not file_list:
        return False
    if ask:
        msg = f"Вы уверены, что хотите удалить {len(file_list)} файлов?\n\n" + "\n".join(file_list[:10])
        if len(file_list) > 10:
            msg += f"\n... и ещё {len(file_list)-10} файлов."
        if not messagebox.askyesno("Подтверждение удаления", msg):
            return False
    errors = []
    for f in file_list:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception as e:
            errors.append(f"{f}: {e}")
    if errors:
        messagebox.showerror("Ошибки при удалении", "\n".join(errors))
        return False
    return True

def rename_files(file_list, progress_callback=None):
    """
    Переименовывает файлы, используя дату съёмки (из EXIF/имени/mtime).
    Формат: DD-MM-YYYY_оригинальное_имя.ext
    Если несколько файлов имеют одинаковую дату, добавляет суффикс _1, _2...
    """
    if not file_list:
        return

    # Сначала группируем файлы по дате
    date_groups = {}  # date -> list of (old_path, new_name_candidate)
    for old_path in file_list:
        d = get_best_date(old_path)
        if d is None:
            # Если дату не удалось определить, оставляем имя как есть (можем пропустить)
            continue
        date_str = d.strftime("%d-%m-%Y")
        # Оригинальное имя без расширения
        basename = os.path.basename(old_path)
        name, ext = os.path.splitext(basename)
        # Новое имя: дата + "_" + оригинальное имя (без расширения) + расширение
        new_name = f"{date_str}_{name}{ext}"
        date_groups.setdefault(date_str, []).append((old_path, new_name))

    # Обрабатываем каждую группу дат: разрешаем конфликты имён
    all_renames = []
    for date_str, items in date_groups.items():
        # Проверяем, есть ли дубликаты новых имён среди этой группы
        name_counts = {}
        for old, new_name in items:
            name_counts[new_name] = name_counts.get(new_name, 0) + 1
        # Для каждого файла формируем окончательное имя
        for old, new_name in items:
            if name_counts[new_name] > 1:
                # Добавляем суффикс _1, _2...
                # Найдём порядковый номер среди одинаковых новых имён
                # (простой способ: перебрать все с этим именем)
                idx = 1
                base, ext = os.path.splitext(new_name)
                final_name = new_name
                # Проверим, не занято ли имя уже существующим файлом в той же папке
                folder = os.path.dirname(old)
                # Также учтём, что может быть конфликт с файлом, который не переименовывается
                while os.path.exists(os.path.join(folder, final_name)):
                    final_name = f"{base}_{idx}{ext}"
                    idx += 1
                all_renames.append((old, final_name))
            else:
                # Проверим, не занято ли имя другим файлом (не из этой группы)
                folder = os.path.dirname(old)
                final_name = new_name
                idx = 1
                while os.path.exists(os.path.join(folder, final_name)):
                    base, ext = os.path.splitext(new_name)
                    final_name = f"{base}_{idx}{ext}"
                    idx += 1
                all_renames.append((old, final_name))

    # Теперь выполняем переименование (сначала проверяем все конфликты)
    # Если два файла из разных папок имеют одинаковое имя – это не проблема, они в разных папках.
    # Проблема только в одной папке – уже решено выше.
    # Но нужно быть уверенным, что целевая папка существует (она существует, т.к. мы не меняем папку).

    # Показываем предпросмотр
    preview = "\n".join([f"{old} -> {new}" for old, new in all_renames[:20]])
    if len(all_renames) > 20:
        preview += f"\n... и ещё {len(all_renames)-20} файлов."
    if not messagebox.askyesno("Переименование файлов", f"Будет переименовано {len(all_renames)} файлов.\n\n{preview}\n\nПродолжить?"):
        return

    errors = []
    for old, new in all_renames:
        try:
            os.rename(old, new)
        except Exception as e:
            errors.append(f"{old} -> {new}: {e}")
    if errors:
        messagebox.showerror("Ошибки при переименовании", "\n".join(errors))
    else:
        messagebox.showinfo("Готово", f"Успешно переименовано {len(all_renames)} файлов.")

# ------------------------------------------------------------
# 4. GUI приложение
# ------------------------------------------------------------

class DupeFinderApp:
    def __init__(self, root):
        self.root = root
        root.title("Photo Duplicate Finder & Renamer")
        root.geometry("800x600")

        # Переменные
        self.folders = []
        self.duplicates = {}  # hash -> list of paths
        self.selected_to_delete = []  # список путей, которые пользователь отметил для удаления

        # Создаём виджеты
        self.create_widgets()

    def create_widgets(self):
        # Верхняя панель: выбор папок
        top_frame = ttk.Frame(self.root)
        top_frame.pack(pady=5, fill=tk.X)

        ttk.Label(top_frame, text="Папки для сканирования:").pack(side=tk.LEFT, padx=5)

        self.folder_listbox = tk.Listbox(top_frame, height=4, selectmode=tk.EXTENDED)
        self.folder_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        btn_frame = ttk.Frame(top_frame)
        btn_frame.pack(side=tk.RIGHT, padx=5)

        ttk.Button(btn_frame, text="Добавить папку", command=self.add_folder).pack(pady=2)
        ttk.Button(btn_frame, text="Удалить выбранные", command=self.remove_folders).pack(pady=2)

        # Кнопка поиска
        self.scan_btn = ttk.Button(self.root, text="Найти дубликаты", command=self.start_scan)
        self.scan_btn.pack(pady=5)

        # Прогресс
        self.progress_var = tk.IntVar()
        self.progress_bar = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, padx=10, pady=5)
        self.status_label = ttk.Label(self.root, text="Готов")
        self.status_label.pack()

        # Таблица результатов
        columns = ("hash", "files")
        self.tree = ttk.Treeview(self.root, columns=columns, show="tree headings")
        self.tree.heading("#0", text="Группа")
        self.tree.heading("hash", text="Хэш (SHA-256)")
        self.tree.heading("files", text="Файлы")
        self.tree.column("#0", width=200)
        self.tree.column("hash", width=200)
        self.tree.column("files", width=300)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Привязываем двойной клик для просмотра файлов группы
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # Кнопки действий
        action_frame = ttk.Frame(self.root)
        action_frame.pack(pady=5)

        ttk.Button(action_frame, text="Удалить выбранные", command=self.delete_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Переименовать оставшиеся", command=self.rename_remaining).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Очистить результаты", command=self.clear_results).pack(side=tk.LEFT, padx=5)

        # Статусная строка
        self.status_var = tk.StringVar(value="Готов")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            if folder not in self.folders:
                self.folders.append(folder)
                self.folder_listbox.insert(tk.END, folder)

    def remove_folders(self):
        selected = self.folder_listbox.curselection()
        for idx in reversed(selected):
            self.folder_listbox.delete(idx)
            del self.folders[idx]

    def start_scan(self):
        if not self.folders:
            messagebox.showwarning("Нет папок", "Добавьте хотя бы одну папку.")
            return
        # Запускаем сканирование в отдельном потоке, чтобы GUI не зависал
        self.scan_btn.config(state=tk.DISABLED)
        self.status_var.set("Сканирование...")
        self.progress_var.set(0)
        threading.Thread(target=self.scan_thread, daemon=True).start()

    def scan_thread(self):
        def update_progress(current, total):
            if total > 0:
                self.progress_var.set(int((current / total) * 100))
            self.status_var.set(f"Обработано {current} из {total}")

        duplicates = find_duplicates(self.folders, progress_callback=update_progress)
        self.root.after(0, self.scan_finished, duplicates)

    def scan_finished(self, duplicates):
        self.duplicates = duplicates
        self.scan_btn.config(state=tk.NORMAL)
        self.status_var.set(f"Найдено {len(duplicates)} групп дубликатов")
        self.populate_tree(duplicates)

    def populate_tree(self, duplicates):
        # Очищаем дерево
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not duplicates:
            self.tree.insert("", tk.END, text="Дубликатов не найдено")
            return

        for h, paths in duplicates.items():
            # Корневой узел группы
            group_id = self.tree.insert("", tk.END, text=f"Группа #{len(paths)} файлов", values=(h[:8]+"...", str(len(paths))))
            # Добавляем файлы как дочерние
            for p in paths:
                self.tree.insert(group_id, tk.END, text=os.path.basename(p), values=(p, ""))

    def on_tree_double_click(self, event):
        # При двойном клике показываем полный путь файла (если выбран дочерний элемент)
        item = self.tree.selection()
        if item:
            # Проверим, является ли это дочерним (имеет родителя)
            parent = self.tree.parent(item[0])
            if parent:
                # Это файл, покажем полный путь
                full_path = self.tree.item(item[0], "values")[0]
                if full_path:
                    messagebox.showinfo("Полный путь", full_path)

    def delete_selected(self):
        # Собираем все выбранные файлы (отмеченные в дереве)
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Нет выбора", "Выберите файлы для удаления (зажмите Ctrl для множественного выбора).")
            return

        files_to_delete = []
        for item in selected_items:
            # Если выбран корневой узел группы, удаляем все файлы группы
            if not self.tree.parent(item):
                # Корневой узел
                children = self.tree.get_children(item)
                for child in children:
                    full_path = self.tree.item(child, "values")[0]
                    if full_path:
                        files_to_delete.append(full_path)
            else:
                # Дочерний (файл)
                full_path = self.tree.item(item, "values")[0]
                if full_path:
                    files_to_delete.append(full_path)

        if not files_to_delete:
            return

        # Просим подтверждение
        if not messagebox.askyesno("Удаление файлов", f"Вы выбрали {len(files_to_delete)} файлов для удаления.\nПродолжить?"):
            return

        # Удаляем
        success = delete_files(files_to_delete, ask=False)  # уже спросили
        if success:
            # Обновляем дерево: убираем удалённые файлы
            # Проще перестроить дерево заново, используя сохранённые дубликаты, но убирая удалённые
            remaining = {}
            for h, paths in self.duplicates.items():
                remaining_paths = [p for p in paths if p not in files_to_delete]
                if len(remaining_paths) > 1:
                    remaining[h] = remaining_paths
                # Если остался один файл, он уже не дубликат
            self.duplicates = remaining
            self.populate_tree(remaining)
            self.status_var.set(f"Удалено {len(files_to_delete)} файлов, осталось {len(remaining)} групп дубликатов")

    def rename_remaining(self):
        # Собираем все файлы из всех групп дубликатов (это те, которые остались после удаления)
        # Но мы можем переименовать все файлы во всех папках? Лучше ограничиться только теми, что в дубликатах,
        # так как пользователь может хотеть переименовать только их.
        # Однако по заданию "переименовывать думаю стоит только оригинал" – т.е. после удаления дубликатов оставшиеся уникальные файлы.
        # Но мы можем переименовать все файлы в выбранных папках? Это более рискованно.
        # Предлагаем переименовать только файлы, которые были в группах дубликатов (т.е. те, что прошли сканирование).
        # Если пользователь хочет переименовать все, он может выбрать отдельную функцию.
        # Мы сделаем так: собираем все пути из self.duplicates (это уже только группы с >1 файлами, но после удаления там могут быть остатки).
        # Лучше переименовывать только те файлы, которые остались после удаления (т.е. все файлы из текущих групп).
        all_files = []
        for paths in self.duplicates.values():
            all_files.extend(paths)

        if not all_files:
            messagebox.showinfo("Нет файлов", "Нет файлов для переименования (возможно, все дубликаты удалены).")
            return

        # Запускаем переименование в потоке (может быть долгим)
        self.status_var.set("Переименование...")
        threading.Thread(target=self.rename_thread, args=(all_files,), daemon=True).start()

    def rename_thread(self, files):
        rename_files(files)
        self.root.after(0, self.rename_finished)

    def rename_finished(self):
        self.status_var.set("Переименование завершено")

    def clear_results(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.duplicates = {}
        self.status_var.set("Результаты очищены")

# ------------------------------------------------------------
# 5. Запуск
# ------------------------------------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app = DupeFinderApp(root)
    root.mainloop()