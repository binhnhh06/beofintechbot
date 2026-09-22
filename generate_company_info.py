import json
import os
import ssl
import urllib.request

print("Đang quét toàn bộ 1.600+ mã chứng khoán Việt Nam...")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

company_dict = {}

# Quét từ VNDirect (chứa full 1.600+ mã HOSE, HNX, UPCoM)
try:
    url = "https://finfo-api.vndirect.com.vn/v4/stocks?q=type:stock,ETF~status:LISTED&size=3000"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=ctx, timeout=15) as res:
        data = json.loads(res.read().decode("utf-8"))
        for item in data.get("data", []):
            ticker = str(item.get("code", "")).strip().upper()
            if ticker and len(ticker) == 3:
                company_dict[ticker] = {
                    "name": item.get("companyName") or f"Công ty Cổ phần {ticker}",
                    "sector": item.get("industryName") or "Cổ phiếu niêm yết"
                }
    print(f" Quét thành công {len(company_dict)} mã từ VNDirect!")
except Exception as e:
    print(f" Nguồn VNDirect gặp lỗi: {e}")

if len(company_dict) > 100:
    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", "company_info.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(company_dict, f, ensure_ascii=False, indent=2)
    print(f" THÀNH CÔNG! Đã lưu {len(company_dict)} mã vào data/company_info.json")
else:
    print(" Chưa lấy được 1600 mã. Vui lòng kiểm tra lại kết nối mạng!")