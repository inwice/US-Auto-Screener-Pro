import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# --- 1. SETTING UI ---
st.set_page_config(page_title="US Stock Scanner $1-$200", layout="wide")
st.title("🇺🇸 US-Stock Auto-Screener ($1 - $200)")
st.markdown("ระบบสแกนหุ้นสหรัฐฯ ราคาประหยัดถึงปานกลาง พร้อม Checklist **MACD + RSI + S/R**")

# --- 2. SIDEBAR CONFIGURATION ---
st.sidebar.header("🔍 Scan & Filter Settings")
market_choice = st.sidebar.selectbox(
    "เลือกกลุ่มหุ้นที่ต้องการสแกน",
    ("S&P 500", "Nasdaq 100", "Dow Jones")
)

# เพิ่มตัวเลือกช่วงราคาให้ปรับได้เองในอนาคต
min_p = st.sidebar.number_input("ราคาขั้นต่ำ ($)", value=1.0)
max_p = st.sidebar.number_input("ราคาสูงสุด ($)", value=200.0)

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
        else:
            url = 'https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average'
            return pd.read_html(url)[1]['Symbol'].tolist()
    except:
        return ["AAPL", "TSLA", "NVDA", "MSFT", "AMD", "META"]

# --- 4. SCANNING LOGIC ---
def run_advanced_scanner(ticker_list, rsi_low, min_price, max_price):
    results = []
    st.write("🔄 กำลังตรวจสอบช่วงราคา $1 - $200...")
    
    # Batch download ราคาปัจจุบัน
    data_batch = yf.download(ticker_list, period="1d", progress=False)['Close']
    
    if isinstance(data_batch, pd.Series):
        latest_price = data_batch.iloc[-1]
        valid_tickers = [ticker_list[0]] if min_price <= latest_price <= max_price else []
    else:
        latest_prices = data_batch.iloc[-1]
        # กรองหุ้นในช่วงราคาที่กำหนด
        valid_tickers = latest_prices[(latest_prices >= min_price) & (latest_prices <= max_price)].index.tolist()

    st.success(f"พบหุ้นตรงตามเกณฑ์ราคา {len(valid_tickers)} ตัว เริ่มสแกน 200 ตัวแรก...")
    
    progress_bar = st.progress(0)
    # จำกัดการสแกน 200 ตัวตามคำขอ
    scan_list = valid_tickers[:200] 
    
    for i, t in enumerate(scan_list):
        try:
            df = yf.download(t, start=datetime.now()-timedelta(days=days_back), progress=False, multi_level_index=False)
            if len(df) < 30: continue
            
            # คำนวณ Technical Indicators
            macd = ta.macd(df['Close'])
            df = pd.concat([df, macd], axis=1)
            df['RSI'] = ta.rsi(df['Close'])
            df['Sup'] = df['Low'].rolling(20).min()
            df['Res'] = df['High'].rolling(20).max()
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            m_l, m_s = macd.columns[0], macd.columns[2]

            # ตรวจเงื่อนไข Checklist
            c1 = last['Low'] <= (last['Sup'] * 1.02)
            c2 = (last['RSI'] < rsi_low) and (last['RSI'] > prev['RSI'])
            c3 = (last[m_l] > last[m_s]) and (prev[m_l] <= prev[m_s])

            if c1 or c2 or c3:
                results.append({
                    "Ticker": t,
                    "Price": round(last['Close'], 2),
                    "RSI": round(last['RSI'], 1),
                    "Support": "✅" if c1 else "❌",
                    "RSI_Up": "✅" if c2 else "❌",
                    "MACD_Cross": "✅" if c3 else "❌",
                    "Signal": "🟢 BUY" if (c1 and c2 and c3) else "⌛ Monitor",
                    "df": df
                })
        except:
            continue
        progress_bar.progress((i + 1) / len(scan_list))
    
    return results

# --- 5. EXECUTION ---
all_symbols = get_auto_tickers(market_choice)

if st.button(f"🚀 เริ่มสแกน {market_choice} (Limit 200)"):
    scan_output = run_advanced_scanner(all_symbols, rsi_limit, min_p, max_p)
    st.session_state['us_scan_results'] = scan_output

# --- 6. DISPLAY & DOWNLOAD ---
if 'us_scan_results' in st.session_state and st.session_state['us_scan_results']:
    res_df = pd.DataFrame(st.session_state['us_scan_results'])
    
    st.subheader(f"📊 ผลการสแกนหุ้นช่วง ${min_p} - ${max_p}")
    
    # ปุ่มดาวน์โหลด CSV
    csv_data = res_df[["Ticker", "Price", "Signal"]].to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Watchlist (CSV)",
        data=csv_data,
        file_name=f'us_watchlist_{datetime.now().strftime("%Y%m%d")}.csv',
        mime='text/csv',
    )

    st.dataframe(res_df.drop(columns=['df']), use_container_width=True, hide_index=True)

    # กราฟสำหรับ Deep Dive
    st.divider()
    choice = st.selectbox("🎯 เจาะลึกรายตัว:", [r['Ticker'] for r in st.session_state['us_scan_results']])
    
    plot_data = next(item for item in st.session_state['us_scan_results'] if item["Ticker"] == choice)
    df_plot = plot_data['df']
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
    fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], 
                                 low=df_plot['Low'], close=df_plot['Close'], name="Price"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Sup'], line=dict(color='green', dash='dot'), name='Support'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['Res'], line=dict(color='red', dash='dot'), name='Resistance'), row=1, col=1)
    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.info(f"ระบบจะสแกนหุ้นเฉพาะตัวที่มีราคา {min_p} - {max_p} ดอลลาร์")
