import tkinter as tk
from tkinter import ttk, messagebox
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .schedule_reminder_page import ScheduleReminderPage


class ScheduleReminderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("日程提醒系统 - 数字化运营助手")
        self.root.geometry("800x600")
        
        # 创建主框架
        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建页面
        self.create_pages()
    
    def create_pages(self):
        """创建页面"""
        # 创建班级日程提醒页面
        self.schedule_page = ScheduleReminderPage(self.main_frame)
    
    def run(self):
        """运行应用"""
        self.root.mainloop()


def main():
    root = tk.Tk()
    app = ScheduleReminderApp(root)
    app.run()


if __name__ == "__main__":
    main()