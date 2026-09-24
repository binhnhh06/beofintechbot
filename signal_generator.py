import json
import time
from datetime import datetime

# 1. Khai báo danh sách mã (BẮT BỦC ĐẶT TRƯỚC DÒNG VÒNG LẶP FOR)
list_co_phieu = ["FPT", "SSI", "VPB", "CTG", "ACB", "HPG", "VHM"]

# 2. Vòng lặp chạy qua từng mã
for ticker in list_co_phieu:
    print(f"Đang tạo tín hiệu cho mã: {ticker}")
    # ... các dòng code xử lý phía dưới của bạn giữ nguyên ...