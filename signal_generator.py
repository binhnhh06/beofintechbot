import time  # <--- Thêm ở dòng đầu tiên

# ... các đoạn code import và cấu hình khác của bạn ...

# Vòng lặp thực tế đang có sẵn trong code của bạn:
for ticker in list_co_phieu:
    # Hàm lấy giá thực tế của bạn, nhớ thêm source="VND"
    df = stock_historical_data(
        symbol=ticker,
        start_date="2026-09-01",
        end_date="2026-09-24",
        source="VND",  # <--- Thêm source để tránh bị chặn IP
    )

    # ... đoạn phân tích MA, RSI, phát tín hiệu của bạn ...

    time.sleep(1)  # <--- Thêm dòng này ở cuối vòng lặp for