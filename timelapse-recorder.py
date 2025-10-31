import cv2
import time
import threading
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
from datetime import datetime
import mss
import numpy as np
from pathlib import Path
import sys
import os

# Platform-specific window detection
if sys.platform == 'win32':
    import win32gui
    import win32con
elif sys.platform == 'darwin':
    # macOS - would need pyobjc or similar
    pass
else:
    # Linux - would need Xlib or similar
    pass

recording = False
selected_window = None  # None means entire screen

# Get the correct directory for config file (works with PyInstaller)
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    SCRIPT_DIR = Path(sys.executable).parent.resolve()
else:
    # Running as script
    SCRIPT_DIR = Path(__file__).parent.resolve()

CONFIG_FILE = SCRIPT_DIR / "config.txt"

def load_config():
    """Load saved configuration or return defaults"""
    defaults = {
        'path': SCRIPT_DIR,
        'fps': 30.0,
        'interval': 1.0,
        'window': 'Entire Screen'
    }
    
    if CONFIG_FILE.exists():
        try:
            lines = CONFIG_FILE.read_text().strip().split('\n')
            config = {}
            for line in lines:
                if '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
            
            return {
                'path': Path(config.get('path', SCRIPT_DIR)),
                'fps': float(config.get('fps', 30.0)),
                'interval': float(config.get('interval', 1.0)),
                'window': config.get('window', 'Entire Screen')
            }
        except:
            pass
    
    return defaults

def save_config(path: Path, fps: float, interval: float, window: str):
    """Save configuration to file"""
    config_text = f"path={path}\nfps={fps}\ninterval={interval}\nwindow={window}"
    CONFIG_FILE.write_text(config_text)

# Load previous settings or defaults
config = load_config()
output_folder = config['path']

def get_window_list():
    """Get list of all visible windows (Windows only for now)"""
    windows = [("Entire Screen", None)]
    
    if sys.platform == 'win32':
        def callback(hwnd, windows_list):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    windows_list.append((title, hwnd))
        
        win32gui.EnumWindows(callback, windows)
    
    return windows

def refresh_windows():
    """Refresh the window selection dropdown"""
    windows = get_window_list()
    window_names = [name for name, _ in windows]
    window_combo['values'] = window_names
    
    # Set to saved window if it exists, otherwise default to "Entire Screen"
    saved_window = config.get('window', 'Entire Screen')
    if saved_window in window_names:
        window_combo.set(saved_window)
    else:
        window_combo.set('Entire Screen')

def get_window_rect(hwnd):
    """Get window rectangle (Windows only)"""
    if sys.platform == 'win32':
        rect = win32gui.GetWindowRect(hwnd)
        return {
            'left': rect[0],
            'top': rect[1],
            'width': rect[2] - rect[0],
            'height': rect[3] - rect[1]
        }
    return None

def browse_folder():
    global output_folder
    folder = filedialog.askdirectory()
    if folder:
        output_folder = Path(folder)
        path_entry.delete(0, tk.END)
        path_entry.insert(0, str(folder))
        # Save all settings when folder changes
        try:
            fps = float(fps_entry.get())
            interval = float(interval_entry.get())
            window = window_combo.get()
            save_config(output_folder, fps, interval, window)
        except:
            pass

def start_recording():
    global recording, output_folder, selected_window
    if recording:
        return
    
    try:
        fps = float(fps_entry.get())
        interval = float(interval_entry.get())
        filename = filename_entry.get().strip() or f"timelapse_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    except:
        messagebox.showerror("Error", "Invalid numeric input")
        return
    
    if fps <= 0 or interval <= 0:
        messagebox.showerror("Error", "FPS and Interval must be > 0")
        return
    
    # Ensure filename has .mp4 extension
    if not filename.lower().endswith('.mp4'):
        filename += '.mp4'
    
    # Get selected window
    window_name = window_combo.get()
    windows = get_window_list()
    selected_window = None
    for name, hwnd in windows:
        if name == window_name:
            selected_window = hwnd
            break
    
    # Save user's chosen output directory and settings
    chosen_path = Path(path_entry.get()).resolve()
    save_config(chosen_path, fps, interval, window_name)
    output_folder = chosen_path
    
    save_file = output_folder / filename
    
    recording = True
    start_button.config(state="disabled")
    stop_button.config(state="normal")
    window_combo.config(state="disabled")
    refresh_button.config(state="disabled")
    
    def record():
        global recording
        with mss.mss() as sct:
            # Determine capture region
            if selected_window is None:
                # Entire screen
                monitor = sct.monitors[1]
            else:
                # Specific window (Windows only)
                if sys.platform == 'win32':
                    rect = get_window_rect(selected_window)
                    if rect is None:
                        messagebox.showerror("Error", "Could not get window dimensions")
                        recording = False
                        start_button.config(state="normal")
                        stop_button.config(state="disabled")
                        window_combo.config(state="normal")
                        refresh_button.config(state="normal")
                        return
                    monitor = rect
                else:
                    monitor = sct.monitors[1]
            
            # Capture first frame to get dimensions
            frame = np.array(sct.grab(monitor))
            height, width = frame.shape[:2]
            
            # Use H264 codec for proper MP4 format
            fourcc = cv2.VideoWriter_fourcc(*"avc1")  # H.264 codec
            out = cv2.VideoWriter(str(save_file), fourcc, fps, (width, height))
            
            if not out.isOpened():
                # Fallback to mp4v if avc1 fails
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                out = cv2.VideoWriter(str(save_file), fourcc, fps, (width, height))
            
            window_info = f" ({window_name})" if selected_window else " (Entire Screen)"
            messagebox.showinfo("Recording Started", f"Recording{window_info}\nSaving to:\n{save_file}")
            
            while recording:
                # Update monitor region each frame in case window moves
                if selected_window is not None and sys.platform == 'win32':
                    rect = get_window_rect(selected_window)
                    if rect:
                        monitor = rect
                
                img = np.array(sct.grab(monitor))
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                
                # Resize if window dimensions changed
                if img.shape[1] != width or img.shape[0] != height:
                    img = cv2.resize(img, (width, height))
                
                out.write(img)
                time.sleep(interval)
            
            out.release()
            messagebox.showinfo("Recording Finished", f"✅ Timelapse saved to:\n{save_file}")
        
        start_button.config(state="normal")
        stop_button.config(state="disabled")
        window_combo.config(state="normal")
        refresh_button.config(state="normal")
    
    threading.Thread(target=record, daemon=True).start()

def stop_recording():
    global recording
    recording = False

# ----------------- UI -----------------
root = tk.Tk()
root.title("Screen Timelapse Recorder")
root.geometry("380x340")

tk.Label(root, text="Output Folder").pack()
path_entry = tk.Entry(root, width=40)
path_entry.pack()
path_entry.insert(0, str(output_folder))
tk.Button(root, text="Browse", command=browse_folder).pack(pady=3)

# Window selection
window_frame = tk.Frame(root)
window_frame.pack(pady=5)
tk.Label(window_frame, text="Capture Window").pack()

window_select_frame = tk.Frame(window_frame)
window_select_frame.pack()

window_combo = ttk.Combobox(window_select_frame, width=35, state="readonly")
window_combo.pack(side=tk.LEFT, padx=(0, 5))

refresh_button = tk.Button(window_select_frame, text="↻", command=refresh_windows, width=3)
refresh_button.pack(side=tk.LEFT)

# Initialize window list
refresh_windows()

tk.Label(root, text="Output FPS").pack()
fps_entry = tk.Entry(root)
fps_entry.insert(0, str(config['fps']))
fps_entry.pack()

tk.Label(root, text="Capture every N seconds").pack()
interval_entry = tk.Entry(root)
interval_entry.insert(0, str(config['interval']))
interval_entry.pack()

tk.Label(root, text="Output filename").pack()
filename_entry = tk.Entry(root)
filename_entry.insert(0, "timelapse.mp4")
filename_entry.pack()

start_button = tk.Button(root, text="Start Recording", command=start_recording)
start_button.pack(pady=5)

stop_button = tk.Button(root, text="Stop Recording", command=stop_recording, state="disabled")
stop_button.pack(pady=5)

root.mainloop()