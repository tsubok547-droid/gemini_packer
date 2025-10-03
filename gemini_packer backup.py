import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import zipfile
from pathlib import Path
import math
import shutil

from tkinterdnd2 import DND_FILES, TkinterDnD

class GeminiPackerApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gemini Packer")
        self.geometry("700x800")
        self.root_path = None
        self.item_map = {}

        ### ★★★★★ 画像読み込み処理をファイルベースに変更 ★★★★★ ###
        try:
            # スクリプト自身の場所を基準に 'assets' フォルダのパスを決定
            script_dir = Path(__file__).resolve().parent
            assets_dir = script_dir / "assets"

            image_paths = {
                'unchecked': assets_dir / 'unchecked.gif',
                'checked': assets_dir / 'checked.gif',
                'partial': assets_dir / 'partial.gif'
            }

            self.check_images = {}
            for name, path in image_paths.items():
                if not path.exists():
                    # ファイルが存在しない場合はエラーを発生させる
                    raise FileNotFoundError(f"画像ファイルが見つかりません: {path}")
                # file引数で画像ファイルを直接読み込む
                self.check_images[name] = tk.PhotoImage(file=str(path))

        except Exception as e:
            # 画像の読み込みに失敗したら、エラーメッセージを出してアプリを終了する
            messagebox.showerror(
                "リソース読み込みエラー",
                f"画像の読み込みに失敗しました。\n\n{e}\n\n'assets'フォルダと中のGIFファイルが正しい場所にあるか確認してください。"
            )
            # self.destroy()だとウィンドウが残ることがあるのでquit()を使う
            self.quit()
            return # 初期化処理を中断
        ### ★★★★★ 修正はここまで ★★★★★ ###

        self._setup_ui()
        self.tree.bind("<Button-1>", self._on_left_click)
        self.tree.bind("<Button-3>", self._on_right_click)

    # (以降のメソッドは前回のものから変更ありません)
    def _setup_ui(self):
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=5)
        self.pack_button = ttk.Button(button_frame, text="✅ 選択したファイルをZIP化", command=self.process_packing)
        self.pack_button.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.save_cache_button = ttk.Button(button_frame, text="💾 現在の選択を保存", command=self.save_cache)
        self.save_cache_button.pack(side="left", expand=True, fill="x", padx=(5, 0))
        
        tree_frame = ttk.Frame(self)
        tree_frame.pack(expand=True, fill="both", padx=10, pady=(5, 10))
        self.tree = ttk.Treeview(tree_frame, show="tree")
        ysb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        xsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self._on_drop)

    def _on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        if not paths: return
        dropped_path = Path(paths[0])
        if not dropped_path.is_dir():
            messagebox.showerror("エラー", "単一のプロジェクトフォルダをドロップしてください。")
            return
        self.root_path = dropped_path
        self.tree.delete(*self.tree.get_children())
        self.item_map = {}
        self._populate_tree("", self.root_path)
        self._load_cache()

    def _populate_tree(self, parent_id, path):
        is_dir = path.is_dir()
        node_id = self.tree.insert(parent_id, "end", text=f" {path.name}", 
                                   image=self.check_images['unchecked'], 
                                   open=is_dir and parent_id=="")
        self.item_map[node_id] = {'path': path, 'state': 'unchecked'}
        if is_dir:
            try:
                children = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
                for p in children:
                    self._populate_tree(node_id, p)
            except OSError: pass

    def _on_left_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id: return
        element = self.tree.identify_element(event.x, event.y)
        if 'image' in str(element):
            self._toggle_check(item_id)
        elif 'text' in str(element):
            data = self.item_map.get(item_id)
            if data and data['path'].is_dir():
                self.tree.item(item_id, open=not self.tree.item(item_id, 'open'))
            else:
                self.tree.focus(item_id)
                self.tree.selection_set(item_id)
        return "break"

    def _on_right_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id: return
        self.tree.focus(item_id)
        self.tree.selection_set(item_id)
        data = self.item_map.get(item_id)
        if data and data['path'].is_file():
            menu = tk.Menu(self, tearoff=0)
            relative_path = data['path'].relative_to(self.root_path)
            path_to_copy = relative_path.as_posix()
            menu.add_command(
                label="相対パスをコピー", 
                command=lambda: self._copy_to_clipboard(path_to_copy)
            )
            menu.post(event.x_root, event.y_root)

    def _copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def _toggle_check(self, item_id):
        current_state = self.item_map[item_id]['state']
        new_state = 'checked' if current_state != 'checked' else 'unchecked'
        self._update_children_state(item_id, new_state)
        self._update_parent_states(item_id)
        self._update_all_displays()

    def _update_children_state(self, item_id, state):
        self.item_map[item_id]['state'] = state
        for child_id in self.tree.get_children(item_id):
            self._update_children_state(child_id, state)
    
    def _update_parent_states(self, item_id):
        parent_id = self.tree.parent(item_id)
        if not parent_id: return
        if self.item_map[parent_id]['state'] == 'checked':
            current_item_state = self.item_map[item_id]['state']
            if current_item_state != 'checked': self.item_map[parent_id]['state'] = 'partial'
            else:
                all_children_checked = all(self.item_map[cid]['state'] == 'checked' for cid in self.tree.get_children(parent_id))
                if not all_children_checked: self.item_map[parent_id]['state'] = 'partial'
            self._update_parent_states(parent_id)
            return
        children_ids = self.tree.get_children(parent_id)
        if not children_ids: return
        has_any_selection = any(self.item_map[child_id]['state'] != 'unchecked' for child_id in children_ids)
        new_state = 'partial' if has_any_selection else 'unchecked'
        if self.item_map[parent_id]['state'] != new_state:
            self.item_map[parent_id]['state'] = new_state
            self._update_parent_states(parent_id)

    def _update_all_displays(self):
        for item_id in self.item_map:
            self._update_item_display(item_id)

    def _update_item_display(self, item_id):
        data = self.item_map.get(item_id)
        if not data: return
        state = data['state']
        self.tree.item(item_id, image=self.check_images[state])

    def save_cache(self):
        if not self.root_path:
            messagebox.showwarning("保存不可", "フォルダが読み込まれていません。")
            return
        paths_to_save = []
        for item_id, data in self.item_map.items():
            if data['state'] == 'checked':
                relative_path = data['path'].relative_to(self.root_path).as_posix()
                if data['path'].is_dir(): relative_path += '/'
                paths_to_save.append(relative_path)
        cache_file = self.root_path / ".gemini_packer_cache.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({"selected_paths": sorted(paths_to_save)}, f, indent=2)
            messagebox.showinfo("保存完了", f"選択状態を {cache_file.name} に保存しました。")
        except Exception as e:
            messagebox.showerror("保存エラー", f"キャッシュファイルの保存に失敗しました:\n{e}")

    def _load_cache(self):
        cache_file = self.root_path / ".gemini_packer_cache.json"
        if not cache_file.exists(): return
        try:
            with open(cache_file, 'r', encoding='utf-8') as f: data = json.load(f)
            cached_paths_str = set(data.get("selected_paths", []))
            path_map = {str(d['path'].relative_to(self.root_path).as_posix()): iid for iid, d in self.item_map.items()}
            dir_path_map = {str(d['path'].relative_to(self.root_path).as_posix()) + '/': iid for iid, d in self.item_map.items() if d['path'].is_dir()}
            path_map.update(dir_path_map)
            for path_str in cached_paths_str:
                item_id = path_map.get(path_str)
                if item_id: self._update_children_state(item_id, 'checked')
            all_items = list(self.item_map.keys())
            for item_id in reversed(all_items):
                if self.tree.parent(item_id): self._update_parent_states(item_id)
            self._update_all_displays()
        except Exception as e:
            messagebox.showwarning("キャッシュ読込エラー", f"キャッシュの読み込みに失敗しました:\n{e}")

    def process_packing(self):
        if not self.root_path:
            messagebox.showwarning("エラー", "フォルダが読み込まれていません。")
            return
        selected_files = {data['path'] for data in self.item_map.values() if data['state'] != 'unchecked' and data['path'].is_file()}
        if not selected_files:
            messagebox.showinfo("情報", "圧縮対象のファイルが選択されていません。")
            return
        output_dir = self.root_path / "gemini_files"
        if output_dir.exists(): shutil.rmtree(output_dir)
        output_dir.mkdir()
        files_per_zip = 10
        sorted_files = sorted(list(selected_files))
        num_zips = math.ceil(len(sorted_files) / files_per_zip)
        for i in range(num_zips):
            chunk = sorted_files[i*files_per_zip : (i+1)*files_per_zip]
            zip_path = output_dir / f"project_archive_{i+1}.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in chunk: zf.write(file_path, file_path.relative_to(self.root_path))
        prompt_file_path = output_dir / "prompts.txt"
        with open(prompt_file_path, 'w', encoding='utf-8') as f:
            initial_prompt = (f"これから【{num_zips}】回に分けてソースコードを渡します。\n"
                              f"すべてのファイルを渡し終えるまで、解析や分析は開始しないでください。\n")
            for i in range(num_zips):
                f.write(f"--- {i+1}/{num_zips}回目のプロンプト ---\n")
                f.write(initial_prompt)
                f.write(f"\nこれは【{i+1}/{num_zips}】回目のソースファイルです。\n\n")
        messagebox.showinfo("完了", f"'{output_dir.name}' フォルダに\n{num_zips}個のZIPとprompts.txtを作成しました。")

if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    app = GeminiPackerApp()
    # アプリのメインループが開始される前にウィンドウが破棄されていないかチェック
    if app.winfo_exists():
        app.mainloop()