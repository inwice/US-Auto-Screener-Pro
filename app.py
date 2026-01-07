import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# --- 1. SETTING UI ---
st.set_page_config(page_title="US Stock Pro Scanner", layout="wide")
st.title("🇺🇸 US-Stock Scanner with Watchlist Export")
st.markdown("ระบบสแกนหุ้นอัตโนมัติ พร้อมฟังก์ชัน **ส่งออกรายชื่อหุ้น (CSV)**")

# --- 2. SIDEBAR CONFIGURATION ---
st.sidebar.header("🔍 Scan Settings")
market_choice = st.sidebar.selectbox(
    "เลือกกลุ่มหุ้นที่ต้องการสแกน",
    ("S&P 500", "Nasdaq 100", "Dow Jones")
)

days_back = st.sidebar.slider("ข้อมูลย้อนหลัง (วัน)", 60, 730, 365)
rsi_limit = st.sidebar.slider("RSI Buy Zone (<)", 20, 50, 45)

# --- 3. AUTO TICKER FETCHING ---
@st.cache_data(ttl=86400)
def get_auto_tickers(choice):
    try:
        if choice == "S&P 500":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            return pd.read_html(url)[0]['Symbol'].tolist()
        elif choice == "Nasdaq 100":
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100#Components'
            table = pd.read_html(url)
            return table[4]['Ticker'].tolist() if len(table) > 4 else table[3]['Ticker'].tolist()
        else: # Dow Jones
            url = 'https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average'
            return pd.read_html(url)[1]['Symbol'].tolist()
    except:
        return ["AAPL", "TSLA", "NVDA", "MSFT", "AMD", "META", "GOOGL"] # Fallback

# --- 4. SCANNING LOGIC ---
def run_scanner(ticker_list, rsi_low):
    results = []
    # ดึงราคาปัจจุบันเพื่อกรองหุ้น > $1
    st.write("🔄 กำลังตรวจสอบราคาพื้นฐาน...")
    data_batch = yf.download(ticker_list, period="1d", progress=False)['Close']
    
    if isinstance(data_batch, pd.Series):
        valid_tickers = [ticker_list[0]] if data_batch.iloc[-1] > 1 else []
    else:
        latest_prices = data_batch.iloc[-1]
        valid_tickers = latest_prices[latest_prices > 1].index.tolist()

    st.success(f"พบหุ้นราคา > $1 ทั้งหมด {len(valid_tickers)} ตัว เริ่มสแกนทางเทคนิค (จำกัด 50 ตัวล่าสุด)...")
    
    progress_bar = st.progress(0)
    # จำกัดจำนวนการสแกนเพื่อความรวดเร็วบน Streamlit
    limit = valid_tickers[:50] 
    
    for i, t in enumerate(limit):
        try:
            df = yf.download(t, start=datetime.now()-timedelta(days=days_back), progress=False, multi_level_index=False)
            if len(df) < 30: continue
            
            # คำนวณเทคนิค
            macd = ta.macd(df['Close'])
            df = pd.concat([df, macd], axis=1)
            df['RSI'] = ta.rsi(df['Close'])
            df['Sup'] = df['Low'].rolling(20).min()
            df['Res'] = df['High'].rolling(20).max()
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            m_l, m_s = macd.columns[0], macd.columns[2]

            # ตรวจ Checklist
            c1 = last['Low'] <= (last['Sup'] * 1.02)
            c2 = (last['RSI'] < rsi_low) and (last['RSI'] > prev['RSI'])
            c3 = (last[m_l] > last[m_s]) and (prev[m_l] <= prev[m_s])

            if c1 or c2 or c3:
                results.append({
                    "Ticker": t,
                    "Price": round(last['Close'], 2),
                    "RSI": round(last['RSI'], 1),
                    "At_Support": "✅" if c1 else "❌",
                    "RSI_Up": "✅" if c2 else "❌",
                    "MACD_Cross": "✅" if c3 else "❌",
                    "Status": "🟢 BUY" if (c1 and c2 and c3) else "⌛ Monitor",
                    "df": df
                })
        except:
            continue
        progress_bar.progress((i + 1) / len(limit))
    
    return results

# --- 5. EXECUTION ---
all_tickers = get_auto_tickers(market_choice)

if st.button(f"🚀 เริ่มสแกนหุ้นใน {market_choice}"):
    final_res = run_scanner(all_tickers, rsi_limit)
    st.session_state['scan_data'] = final_res

# --- 6. DISPLAY & EXPORT ---
if 'scan_data' in st.session_state and st.session_state['scan_data']:
    res_df = pd.DataFrame(st.session_state['scan_data'])
    
    # ส่วนการส่งออกข้อมูล
    st.subheader("📊 ผลการสแกน")
    
    col_a, col_b = st.columns([3, 1])
    with col_b:
        # ฟังก์ชันแปลงเป็น CSV
        csv = res_df[["Ticker", "Price", "Status"]].to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Watchlist (CSV)",
            data=csv,
            file_name=f'watchlist_{datetime.now().strftime("%Y%m%d")}.csv',
            mime='text/csv',
        )

    st.dataframe(res_df.drop(columns=['df']), use_container_width=True, hide_index=True)

    # กราฟรายละเอียด
    st.divider()
    choice = st.selectbox("🎯 เลือกหุ้นเพื่อดูแผนภาพ:", [r['Ticker'] for r in st.session_state['scan_data']])
    
    data_to_plot = next(item for item in st.session_state['scan_data'] if item["Ticker"] == choice)
    df_p = data_to_plot['df']
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
    fig.add_trace(go.Candlestick(x=df_p.index, open=df_p['Open'], high=df_p['High'], low=df_p['Low'], close=df_p['Close'], name="Price"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_p.index, y=df_p['Sup'], line=dict(color='green', dash='dot'), name='Support'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_p.index, y=df_p['Res'], line=dict(color='red', dash='dot'), name='Resistance'), row=1, col=1)
    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("กรุณากดปุ่มเพื่อเริ่มสแกนรายชื่อหุ้นอัตโนมัติ")
