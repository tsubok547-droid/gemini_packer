import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import zipfile
from pathlib import Path
import math
import shutil
import sys

from tkinterdnd2 import DND_FILES, TkinterDnD

def resource_path(relative_path):
    """ .exeにバンドルされたアセットへのパスを取得する """
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(__file__).resolve().parent
    return base_path / relative_path


class GeminiPackerApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gemini Packer")
        self.geometry("700x800")
        self.root_path = None
        self.item_map = {}

        try:
            image_paths = {
                'unchecked': resource_path('assets/unchecked.gif'),
                'checked': resource_path('assets/checked.gif'),
                'partial': resource_path('assets/partial.gif')
            }
            
            self.check_images = {}
            for name, path in image_paths.items():
                if not path.exists():
                    raise FileNotFoundError(f"画像ファイルが見つかりません: {path}")
                self.check_images[name] = tk.PhotoImage(file=str(path))

        except Exception as e:
            messagebox.showerror(
                "リソース読み込みエラー",
                f"画像の読み込みに失敗しました。\n\n{e}\n\n'assets'フォルダと中のGIFファイルが正しい場所にあるか確認してください。"
            )
            self.quit()
            return

        self._setup_ui()
        self.tree.bind("<Button-1>", self._on_left_click)
        self.tree.bind("<Button-3>", self._on_right_click)

    def _setup_ui(self):
        # メインのボタンフレーム
        main_button_frame = ttk.Frame(self)
        main_button_frame.pack(fill="x", padx=10, pady=5)
        
        self.pack_button = ttk.Button(main_button_frame, text="✅ 選択したファイルをZIP化", command=self.process_packing)
        self.pack_button.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.structure_button = ttk.Button(main_button_frame, text="📜 構成ファイル生成", command=self.create_directory_structure_file)
        self.structure_button.pack(side="left", expand=True, fill="x", padx=5)
        self.save_cache_button = ttk.Button(main_button_frame, text="💾 現在の選択を保存", command=self.save_cache)
        self.save_cache_button.pack(side="left", expand=True, fill="x", padx=(5, 0))

        # 設定用フレーム (ZIPあたりのファイル数)
        settings_frame = ttk.Frame(self)
        settings_frame.pack(fill="x", padx=10, pady=(0, 5))
        
        settings_label = ttk.Label(settings_frame, text="1ZIPあたりのファイル数:")
        settings_label.pack(side="left", padx=(0, 5))
        
        self.files_per_zip_var = tk.StringVar(value="10")
        self.files_per_zip_spinbox = ttk.Spinbox(settings_frame, from_=1, to=1000, textvariable=self.files_per_zip_var, width=5)
        self.files_per_zip_spinbox.pack(side="left")

        # ツリーフレーム
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

    def create_directory_structure_file(self):
        if not self.root_path:
            messagebox.showwarning("エラー", "フォルダが読み込まれていません。")
            return
        is_anything_selected = any(d['state'] != 'unchecked' for d in self.item_map.values())
        if not is_anything_selected:
            messagebox.showinfo("情報", "構成ファイルに含めるアイテムが選択されていません。")
            return
        output_filename = self.root_path / "directory_structure.txt"
        try:
            root_items = self.tree.get_children('')
            if not root_items: return
            tree_lines = self._generate_tree_for_selection(root_items[0])
            with open(output_filename, 'w', encoding='utf-8') as f:
                root_text = self.tree.item(root_items[0], 'text').strip()
                f.write(f"{root_text}/\n")
                f.write("\n".join(tree_lines))
            messagebox.showinfo("完了", f"選択されたアイテムの構成ファイルを\n'{output_filename.name}' として作成しました。")
        except Exception as e:
            messagebox.showerror("エラー", f"構成ファイルの作成に失敗しました:\n{e}")

    def _generate_tree_for_selection(self, item_id, prefix=""):
        output_lines = []
        children_ids = self.tree.get_children(item_id)
        selected_children = [cid for cid in children_ids if self.item_map.get(cid) and self.item_map[cid]['state'] != 'unchecked']
        for i, child_id in enumerate(selected_children):
            is_last = (i == len(selected_children) - 1)
            connector = '└── ' if is_last else '├── '
            item_data = self.item_map[child_id]
            item_text = self.tree.item(child_id, 'text').strip()
            if item_data['path'].is_dir():
                output_lines.append(f"{prefix}{connector}{item_text}/")
                if item_data['state'] in ('partial', 'checked'):
                    new_prefix = prefix + ('    ' if is_last else '│   ')
                    output_lines.extend(self._generate_tree_for_selection(child_id, new_prefix))
            else:
                output_lines.append(f"{prefix}{connector}{item_text}")
        return output_lines

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
        
        # ▼▼▼ 追加: .gitignore の自動更新 ▼▼▼
        self._update_gitignore()

    def _update_gitignore(self):
        """プロジェクトの.gitignoreを確認し、必要ならGemini Packerの除外設定を追記する"""
        if not self.root_path:
            return
            
        gitignore_path = self.root_path / ".gitignore"
        
        ignore_entries = [
            "\n# Gemini Packer\n",
            ".gemini_packer_cache.json\n",
            "gemini_files/\n"
        ]

        if gitignore_path.exists():
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 既に記述があるかチェック（冪等性の担保）
            if ".gemini_packer_cache.json" in content or "gemini_files/" in content:
                return  # 既に設定済みなら何もしない
                
            # ファイル末尾が改行で終わっていない場合のケア
            if content and not content.endswith('\n'):
                ignore_entries.insert(0, "\n")
                
            with open(gitignore_path, 'a', encoding='utf-8') as f:
                f.writelines(ignore_entries)
        else:
            # .gitignoreが存在しない場合は新規作成
            with open(gitignore_path, 'w', encoding='utf-8') as f:
                f.writelines([e.lstrip('\n') for e in ignore_entries])

    def _populate_tree(self, parent_id, path):
        is_dir = path.is_dir()
        node_id = self.tree.insert(parent_id, "end", text=f" {path.name}", image=self.check_images['unchecked'], open=is_dir and parent_id=="")
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
            menu.add_command(label="相対パスをコピー", command=lambda: self._copy_to_clipboard(path_to_copy))
            menu.post(event.x_root, event.y_root)

    def _copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def _toggle_check(self, item_id):
        current_state = self.item_map[item_id]['state']
        new_state = 'checked' if current_state != 'checked' else 'unchecked'
        
        self.item_map[item_id]['state'] = new_state
        
        if self.item_map[item_id]['path'].is_dir():
            self._update_children_state(item_id, new_state)
        
        self._update_parent_states(item_id)
        self._update_all_displays()

    def _update_children_state(self, item_id, state):
        for child_id in self.tree.get_children(item_id):
            self.item_map[child_id]['state'] = state
            if self.item_map[child_id]['path'].is_dir():
                self._update_children_state(child_id, state)
    
    def _update_parent_states(self, item_id):
        parent_id = self.tree.parent(item_id)
        if not parent_id: return

        # 親がユーザーによって直接'checked'にされている場合は、子の状態に応じて'partial'に降格させるだけ
        if self.item_map[parent_id]['state'] == 'checked':
            child_states_for_checked_parent = {self.item_map[cid]['state'] for cid in self.tree.get_children(parent_id)}
            if 'unchecked' in child_states_for_checked_parent or 'partial' in child_states_for_checked_parent:
                self.item_map[parent_id]['state'] = 'partial'
                self._update_parent_states(parent_id)
            return

        # 親が'checked'でない場合、子の状態から新しい状態を決定する
        children_ids = self.tree.get_children(parent_id)
        if not children_ids: return
        child_states = {self.item_map[cid]['state'] for cid in children_ids}
        
        new_state = 'unchecked'
        if all(s == 'checked' for s in child_states):
             new_state = 'partial' # 子がすべてチェックされても親はpartial
        elif any(s in ('checked', 'partial') for s in child_states):
            new_state = 'partial'
        
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
        # ツリーの表示順（≒親子関係が保たれやすい順）でアイテムを処理
        for item_id in self.tree.get_children(''):
            self._collect_paths_to_save(item_id, paths_to_save)

        cache_file = self.root_path / ".gemini_packer_cache.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({"selected_paths": sorted(paths_to_save)}, f, indent=2)
            messagebox.showinfo("保存完了", f"選択状態を {cache_file.name} に保存しました。")
        except Exception as e:
            messagebox.showerror("保存エラー", f"キャッシュファイルの保存に失敗しました:\n{e}")
            
    def _collect_paths_to_save(self, item_id, paths_to_save):
        """save_cacheのためのヘルパー関数"""
        data = self.item_map[item_id]
        
        # アイテムが'checked'の場合のみが保存対象
        if data['state'] == 'checked':
            relative_path = data['path'].relative_to(self.root_path).as_posix()
            if data['path'].is_dir():
                relative_path += '/'
            paths_to_save.append(relative_path)
            # フォルダが'checked'なら、その子についてはもう処理しない（これが重要）
            return
            
        # アイテムが'partial'の場合、子を再帰的にチェック
        if data['state'] == 'partial' and data['path'].is_dir():
            for child_id in self.tree.get_children(item_id):
                self._collect_paths_to_save(child_id, paths_to_save)

    def _load_cache(self):
        cache_file = self.root_path / ".gemini_packer_cache.json"
        if not cache_file.exists(): return
        try:
            with open(cache_file, 'r', encoding='utf-8') as f: data = json.load(f)
            cached_paths = set(data.get("selected_paths", []))
            
            for item_id in self.item_map: self.item_map[item_id]['state'] = 'unchecked'
            path_map = {d['path'].relative_to(self.root_path).as_posix(): iid for iid, d in self.item_map.items()}
            
            for path_str in cached_paths:
                is_dir = path_str.endswith('/')
                clean_path_str = path_str.rstrip('/')
                item_id = path_map.get(clean_path_str)

                if item_id:
                    self.item_map[item_id]['state'] = 'checked'
                    if is_dir:
                        self._update_children_state(item_id, 'checked')
            
            all_items = list(self.item_map.keys())
            for item_id in reversed(all_items):
                if self.tree.parent(item_id):
                    self._update_parent_states(item_id)
            
            self._update_all_displays()
        except Exception as e:
            messagebox.showwarning("キャッシュ読込エラー", f"キャッシュの読み込みに失敗しました:\n{e}")

    def process_packing(self):
        if not self.root_path:
            messagebox.showwarning("エラー", "フォルダが読み込まれていません。")
            return
            
        try:
            # UIからファイル数を取得
            files_per_zip = int(self.files_per_zip_var.get())
            if files_per_zip < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("入力エラー", "1ZIPあたりのファイル数は1以上の整数を入力してください。")
            return
        
        selected_files = { data['path'] for data in self.item_map.values() if data['state'] != 'unchecked' and data['path'].is_file() }
        
        if not selected_files:
            messagebox.showinfo("情報", "圧縮対象のファイルが選択されていません。")
            return
        
        # ▼▼▼ 変更: 優しい初期化 (不要な全削除をやめる) ▼▼▼
        output_dir = self.root_path / "gemini_files"
        
        if not output_dir.exists():
            output_dir.mkdir()
        else:
            # フォルダ内の過去のZIPファイルだけを削除
            for old_zip in output_dir.glob("*.zip"):
                old_zip.unlink()
            
            # 過去の prompts.txt があれば削除
            old_prompt = output_dir / "prompts.txt"
            if old_prompt.exists():
                old_prompt.unlink()
        # ▲▲▲ 変更ここまで ▲▲▲
        
        sorted_files = sorted(list(selected_files))
        num_zips = math.ceil(len(sorted_files) / files_per_zip)
        
        for i in range(num_zips):
            chunk = sorted_files[i*files_per_zip : (i+1)*files_per_zip]
            zip_path = output_dir / f"project_archive_{i+1}.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in chunk: zf.write(file_path, file_path.relative_to(self.root_path))

        prompt_file_path = output_dir / "prompts.txt"
        with open(prompt_file_path, 'w', encoding='utf-8') as f:
            base_instruction = (
                f"これからプロジェクトのソースコードを【{num_zips}】回に分けてお送りします。\n"
                "すべてのファイルを受け取るまで、分析やレビューは開始しないでください。\n"
                "このプロンプトに対しては、「承知しました。次のファイルを待っています。」とだけ返信してください。"
            )
            for i in range(num_zips):
                f.write(f"--- プロンプト {i+1}/{num_zips} ---\n\n")
                f.write(f"これは【{i+1}/{num_zips}】番目のファイル群です。\n")
                f.write(base_instruction)
                f.write("\n\n---------------------\n\n")
            final_prompt = (
                "すべてのファイルをお送りしました。\n"
                "お送りしたすべてのソースコードを基に、具体的な解析を依頼してください。"
            )
            f.write(f"--- 最終プロンプト (すべてのファイルを送信した後) ---\n\n")
            f.write(final_prompt)
            f.write("\n\n---------------------\n\n")
        
        messagebox.showinfo("完了", f"'{output_dir.name}' フォルダに\n{num_zips}個のZIPとprompts.txtを作成しました。")


if __name__ == "__main__":
    # DPI設定をコメントアウトして、Windowsに拡大を任せる
    # try:
    #     from ctypes import windll
    #     windll.shcore.SetProcessDpiAwareness(1)
    # except: pass
    
    app = GeminiPackerApp()
    if app.winfo_exists():
        app.mainloop()