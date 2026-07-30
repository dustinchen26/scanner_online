import subprocess
import sys
import os

# ========== 自動安裝套件機制 ==========
def install_dependencies():
    """檢查並安裝缺少的套件"""
    required_packages = {
        "cv2": "opencv-python",
        "numpy": "numpy",
        "PIL": "Pillow"
    }
    
    for module_name, pip_name in required_packages.items():
        try:
            __import__(module_name)
        except ImportError:
            print(f"正在偵測到缺少套件: {pip_name}，準備自動安裝...")
            try:
                # 呼叫系統 pip 進行安裝
                subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
                print(f"套件 {pip_name} 安裝成功！")
            except Exception as e:
                print(f"安裝 {pip_name} 失敗，請手動執行 'pip install {pip_name}'")
                print(f"錯誤訊息: {e}")

# 在匯入主要邏輯前先檢查環境
install_dependencies()

# ========== 匯入主要函式庫 ==========
import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

class FinalUltimateScanner:
    def __init__(self, root):
        self.root = root
        self.root.title("AI 彩色掃描器 - 自動環境配置版")
        self.root.geometry("1000x800")
        
        self.orig_image = None
        self.display_image = None
        self.input_filename = ""
        self.ratio = 1.0
        self.points = []
        self.selected_point_idx = None

        # ----- UI 佈局 -----
        self.canvas = tk.Canvas(root, bg="#1a1a1a", cursor="hand2")
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.status_label = tk.Label(root, text="請載入圖片", bg="#333", fg="cyan")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        btn_frame = tk.Frame(root, bg="#333", pady=8)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X)

        tk.Button(btn_frame, text=" 📂 開啟照片 ", command=self.load_image).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text=" 🔍 自動偵測 ", command=self.re_auto_detect).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text=" 🔄 全畫面 ", command=self.reset_to_full).pack(side=tk.LEFT)
        
        self.filter_var = tk.BooleanVar(value=False)
        tk.Checkbutton(btn_frame, text="套用彩色優化 (保留插圖細節)", variable=self.filter_var, 
                       bg="#333", fg="white", selectcolor="#444").pack(side=tk.LEFT, padx=20)

        tk.Button(btn_frame, text=" ✅ 轉正並存檔 ", command=self.process_scan, bg="#28a745", fg="white",
                  font=("Arial", 10, "bold")).pack(side=tk.RIGHT, padx=10)

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        self._resize_after_id = None

    # ========== 彩色濾鏡 (保留原色質感版) ==========
    def apply_color_perfect_filter(self, img):
        # 轉成灰階來製作「文字遮罩」
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 步驟 1: 使用自適應門檻提取文字筆畫
        text_mask = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                          cv2.THRESH_BINARY, 25, 10)
        
        # 步驟 2: 雙邊濾波保留邊緣但抹除雜點
        smooth = cv2.bilateralFilter(img, 9, 75, 75)
        
        # 步驟 3: 強化色彩飽和度
        hsv = cv2.cvtColor(smooth, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        s = cv2.multiply(s, 1.25) 
        v = cv2.multiply(v, 1.1)  
        enhanced_img = cv2.merge((h, s, v))
        enhanced_img = cv2.cvtColor(enhanced_img, cv2.COLOR_HSV2BGR)
        
        # 步驟 4: 將「文字遮罩」與「強化後的原圖」疊加
        text_mask_rgb = cv2.cvtColor(text_mask, cv2.COLOR_GRAY2BGR)
        res = cv2.bitwise_and(enhanced_img, text_mask_rgb)
        
        # 步驟 5: 最後微調對比
        final = cv2.convertScaleAbs(res, alpha=1.1, beta=-10)
        return final
        
    # ========== UI 與 變換邏輯 ==========
    def fit_image_to_canvas(self):
        if self.orig_image is None: return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 10 or ch < 10: return
        h, w = self.orig_image.shape[:2]
        scale = min(cw / w, ch / h)
        self.display_image = cv2.resize(self.orig_image, (int(w * scale), int(h * scale)))
        self.ratio = h / self.display_image.shape[0]

    def on_canvas_resize(self, event):
        if self._resize_after_id: self.root.after_cancel(self._resize_after_id)
        self._resize_after_id = self.root.after(100, self._handle_resize)

    def _handle_resize(self):
        if self.orig_image is None: return
        old_ratio, old_points = self.ratio, self.points.copy()
        self.fit_image_to_canvas()
        if old_points and old_ratio > 0:
            self.points = [[(p[0] * old_ratio) / self.ratio, (p[1] * old_ratio) / self.ratio] for p in old_points]
        self.redraw()

    def smart_auto_detect(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 30, 100)
        cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]
        for c in cnts:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4: return self.sort_points([tuple(p[0]) for p in approx])
        return None

    def sort_points(self, pts):
        pts = np.array(pts, dtype="float32")
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0], rect[2] = pts[np.argmin(s)], pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1], rect[3] = pts[np.argmin(diff)], pts[np.argmax(diff)]
        return [list(p) for p in rect]

    def load_image(self):
        path = filedialog.askopenfilename(filetypes=[("圖片檔案", "*.jpg *.jpeg *.png")])
        if not path: return
        # 支援中文路徑讀取
        img_array = np.fromfile(path, np.uint8)
        self.orig_image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        self.input_filename = os.path.splitext(os.path.basename(path))[0]
        self.fit_image_to_canvas()
        self.re_auto_detect()

    def re_auto_detect(self):
        if self.display_image is None: return
        auto_pts = self.smart_auto_detect(self.display_image)
        if auto_pts: self.points = auto_pts
        else: self.reset_to_full()
        self.redraw()

    def reset_to_full(self):
        if self.display_image is not None:
            h, w = self.display_image.shape[:2]
            self.points = [[20, 20], [w-20, 20], [w-20, h-20], [20, h-20]]
            self.redraw()

    def on_press(self, event):
        for i, p in enumerate(self.points):
            if np.sqrt((event.x - p[0])**2 + (event.y - p[1])**2) < 25:
                self.selected_point_idx = i; break

    def on_drag(self, event):
        if self.selected_point_idx is not None:
            self.points[self.selected_point_idx] = [event.x, event.y]
            self.redraw()

    def on_release(self, event): self.selected_point_idx = None

    def redraw(self):
        if self.display_image is None: return
        img_rgb = cv2.cvtColor(self.display_image, cv2.COLOR_BGR2RGB)
        self.img_tk = ImageTk.PhotoImage(Image.fromarray(img_rgb))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.img_tk)
        if len(self.points) == 4:
            pts_flat = [c for p in self.points for c in p]
            self.canvas.create_polygon(pts_flat, outline="#00ff00", fill="#00ff00", stipple="gray25", width=2)
            for p in self.points: self.canvas.create_oval(p[0]-8, p[1]-8, p[0]+8, p[1]+8, fill="#0078d4", outline="white")

    def process_scan(self):
        if not self.points: return
        pts = np.array(self.points, dtype="float32") * self.ratio
        max_w = max(int(np.linalg.norm(pts[1]-pts[0])), int(np.linalg.norm(pts[2]-pts[3])))
        max_h = max(int(np.linalg.norm(pts[1]-pts[2])), int(np.linalg.norm(pts[0]-pts[3])))
        dst = np.array([[0, 0], [max_w-1, 0], [max_w-1, max_h-1], [0, max_h-1]], dtype="float32")
        M = cv2.getPerspectiveTransform(pts, dst)
        warped = cv2.warpPerspective(self.orig_image, M, (max_w, max_h))
        
        if self.filter_var.get():
            warped = self.apply_color_perfect_filter(warped)
        
        save_path = f"{self.input_filename}_scanner.jpg"
        # 支援中文路徑儲存
        _, encoded_img = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 95])
        encoded_img.tofile(save_path)
        messagebox.showinfo("成功", f"存檔成功：\n{save_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FinalUltimateScanner(root)
    root.mainloop()