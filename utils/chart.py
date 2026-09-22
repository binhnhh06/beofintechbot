import io
import matplotlib.pyplot as plt


def generate_stock_chart(df, symbol):
    """
    Vẽ biểu đồ Dark Mode chuẩn 2 khung (Price/EMA20 + RSI)
    df cần chứa các cột: 'close', 'ema20', 'rsi'
    """
    # Cấu hình phong cách Dark Mode
    plt.style.use("dark_background")
    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(8, 6),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )
    fig.patch.set_facecolor("#181818")

    # --- Khung 1: Giá đóng cửa & EMA20 ---
    ax1.set_facecolor("#181818")
    ax1.plot(
        df.index,
        df["close"],
        color="#00FF7F",
        label="Giá đóng cửa",
        linewidth=1.5,
    )
    ax1.plot(
        df.index,
        df["ema20"],
        color="#FF8C00",
        linestyle="--",
        label="EMA20",
        linewidth=1.2,
    )
    ax1.set_title(
        f"Biểu đồ Phân tích Kỹ thuật #{symbol}",
        color="white",
        fontsize=12,
        pad=10,
    )
    ax1.legend(
        loc="upper left",
        frameon=True,
        facecolor="#252525",
        edgecolor="none",
        fontsize=9,
    )
    ax1.grid(True, linestyle=":", alpha=0.2, color="#888888")

    # --- Khung 2: Chỉ báo RSI(14) ---
    ax2.set_facecolor("#181818")
    ax2.plot(df.index, df["rsi"], color="#1E90FF", linewidth=1.5)
    ax2.axhline(70, color="#FF4500", linestyle="--", alpha=0.6, linewidth=1)
    ax2.axhline(30, color="#00FA9A", linestyle="--", alpha=0.6, linewidth=1)
    ax2.set_ylabel("RSI(14)", color="white", fontsize=9)
    ax2.set_ylim(0, 100)
    ax2.grid(True, linestyle=":", alpha=0.2, color="#888888")

    plt.tight_layout()

    # Xuất biểu đồ ra bộ nhớ đệm Buffer (không lưu đĩa)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor="#181818")
    buf.seek(0)
    plt.close(fig)
    return buf