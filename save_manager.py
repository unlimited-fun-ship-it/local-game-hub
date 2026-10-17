import os
import json
import time
import tkinter as tk
from tkinter import messagebox, simpledialog

SAVE_DIR = "saves"

def get_game_dir(game_id):
    path = os.path.join(SAVE_DIR, game_id)
    os.makedirs(path, exist_ok=True)
    return path

def list_saves(game_id):
    game_dir = get_game_dir(game_id)
    return sorted([f for f in os.listdir(game_dir) if f.endswith(".json")], reverse=True)

def load_game(game_id, filename):
    game_dir = get_game_dir(game_id)
    filepath = os.path.join(game_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def delete_save(game_id, filename):
    game_dir = get_game_dir(game_id)
    filepath = os.path.join(game_dir, filename)
    if os.path.exists(filepath):
        os.remove(filepath)

def prompt_save(parent, game_id, data):
    name = simpledialog.askstring(
        "Save Game", "Enter a name for this save:",
        initialvalue=f"save_{int(time.time())}", parent=parent
    )
    if not name:
        return False
    # Sanitize filename
    name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
    if not name:
        name = f"save_{int(time.time())}"
    filename = name + ".json"
    
    game_dir = get_game_dir(game_id)
    filepath = os.path.join(game_dir, filename)
    
    if os.path.exists(filepath):
        if not messagebox.askyesno("Overwrite?", f"'{filename}' already exists. Overwrite?", parent=parent):
            return False
            
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    messagebox.showinfo("Saved", f"Game saved to {filename}", parent=parent)
    return True

def prompt_load(parent, game_id):
    saves = list_saves(game_id)
    if not saves:
        messagebox.showinfo("No Saves", "No save files found for this game.", parent=parent)
        return None
    
    dlg = tk.Toplevel(parent)
    dlg.title("Load Game")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(False, False)
    
    tk.Label(dlg, text="Select a save file to load:").pack(padx=10, pady=5)
    
    lb = tk.Listbox(dlg, width=40, height=10)
    lb.pack(padx=10, pady=5)
    for s in saves:
        lb.insert(tk.END, s)
    lb.selection_set(0)
    
    result = [None]
    
    def on_load():
        sel = lb.curselection()
        if sel:
            result[0] = saves[sel[0]]
        dlg.destroy()
        
    def on_delete():
        sel = lb.curselection()
        if sel:
            fname = saves[sel[0]]
            if messagebox.askyesno("Delete", f"Delete '{fname}'?", parent=dlg):
                delete_save(game_id, fname)
                lb.delete(sel[0])
                if lb.size() == 0:
                    dlg.destroy()
                    
    btn_frame = tk.Frame(dlg)
    btn_frame.pack(pady=10)
    tk.Button(btn_frame, text="Load", command=on_load).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Delete", command=on_delete).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side="left", padx=5)
    
    dlg.wait_window()
    return result[0]