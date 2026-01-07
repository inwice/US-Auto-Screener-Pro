import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from yahoo_fin import stock_info as si

# --- 1. SETTING UI ---
st.set_page_config(page_title="US Market Scanner Pro", layout="wide")
st.title("🇺🇸 US-Stock Broad Market Scanner ($1 - $200)")
st.markdown("ดึงรายชื่อหุ้นสดใหม่จาก **yahoo_fin** | กรองราคา $1 - $200 | สแกน 200 ตัวแรก")

# --- 2. SIDEBAR CONFIGURATION ---
st.sidebar.header("🔍 Market Selection")

# เลือกตลาดที่ต้องการดึงรายชื่อ
market_source = st.sidebar.selectbox(
    "เลือกกลุ่มหุ้นที่ต้องการสแกน",
    ("NASDAQ (หุ้นไอที/นวัตกรรม)", "S&P 500 (หุ้นใหญ่)", "Others (รวม NYSE/AMEX)")
)

st.sidebar.divider()
st.sidebar.header("🛡️ Risk & Strategy")
min_p = st.sidebar.number_input("ราคาขั้นต่ำ ($)", value=1.0)
max_p = st.sidebar.number_input("ราคาสูงสุด ($)", value=200.0)
rsi_limit = st.sidebar.slider("RSI Buy Zone (<)", 20, 50, 45)
days_back = st.sidebar.slider("ข้อมูลย้อนหลัง (วัน)", 60, 730, 365)

# --- 3. DYNAMIC TICKER FETCHING (Using yahoo_fin) ---
@st.cache_data(ttl=86400)
def get_tickers_via_yfin(source):
    try:
        if source == "NASDAQ (หุ้นไอที/นวัตกรรม)":
            return si.tickers_nasdaq()
        elif source == "S&P 500 (หุ้นใหญ่)":
            return si.tickers_sp500()
        else: # Others - ครอบคลุม NYSE, AMEX
            return si.tickers_others()
    except Exception as e:
        st.error(f"ไม่สามารถดึงรายชื่อได้: {e}")
        return ["AAPL", "TSLA", "NVDA", "AMD", "MSFT"]

# --- 4. SCANNING LOGIC ---
def run_market_scanner(tickers, rsi_low, p_min, p_max):
    results = []
    st.write(f"🔄 กำลังดึงรายชื่อหุ้นจากตลาด... (พบทั้งหมด {len(tickers)} ตัว)")
    
    # 4.1 กรองราคาเบื้องต้นด้วย Batch Download (ประมวลผลทีละ 100 ตัวเพื่อป้องกัน Error)
    st.write("🔍 กำลังกรองหุ้นในช่วงราคาที่ต้องการ...")
    chunk_size = 100
    valid_tickers = []
    
    # สแกนหาหุ้นที่ราคาตรงเกณฑ์จนกว่าจะได้ครบ 200 หรือหมด List
    for i in range(0, len(tickers), chunk_size):
        if len(valid_tickers) >= 200: break
        
        chunk = tickers[i:i+chunk_size]
        try:
            batch_prices = yf.download(chunk, period="1d", progress=False, multi_level_index=False)['Close']
            if isinstance(batch_prices, pd.Series):
                if p_min <= batch_prices.iloc[-1] <= p_max:
                    valid_tickers.append(chunk[0])
            else:
                last_p = batch_prices.iloc[-1]
                v = last_p[(last_p >= p_min) & (last_p <= p_max)].index.tolist()
                valid_tickers.extend(v)
        except:
            continue

    valid_tickers = valid_tickers[:200]
    st.success(f"พบหุ้นตรงเกณฑ์ $1-$200 ทั้งหมด {len(valid_tickers)} ตัว เริ่มวิเคราะห์ทางเทคนิค...")

    # 4.2 วิเคราะห์รายตัว
    progress_bar = st.progress(0)
    for i, t in enumerate(valid_tickers):
        try:
            df = yf.download(t, start=datetime.now()-timedelta(days=days_back), progress=False, multi_level_index=False)
            if len(df) < 30: continue
            
            macd = ta.macd(df['Close'])
            df = pd.concat([df, macd], axis=1)
            df['RSI'] = ta.rsi(df['Close'])
            df['Sup'] = df['Low'].rolling(20).min()
            df['Res'] = df['High'].rolling(20).max()
            
            last, prev = df.iloc[-1], df.iloc[-2]
            m_l, m_s = macd.columns[0], macd.columns[2]

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
                    "Signal": "🟢 BUY" if (c1 and c2 and c3) else "⌛ Wait",
                    "df": df
                })
        except: continue
        progress_bar.progress((i + 1) / len(valid_tickers))
    return results

# --- 5. EXECUTION ---
ticker_pool = get_tickers_via_yfin(market_source)

if st.button(f"🚀 เริ่มสแกน {market_source} (จำกัด 200 ตัวที่ผ่านเกณฑ์ราคา)"):
    final_output = run_market_scanner(ticker_pool, rsi_limit, min_p, max_p)
    st.session_state['yfin_results'] = final_output

# --- 6. DISPLAY & CSV ---
if 'yfin_results' in st.session_state and st.session_state['yfin_results']:
    res_df = pd.DataFrame(st.session_state['yfin_results'])
    
    st.subheader(f"📊 ผลการสแกนล่าสุด ({len(res_df)} หุ้นติดสัญญาณ)")
    
    # Download Button
    csv = res_df[["Ticker", "Price", "Signal"]].to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Watchlist (CSV)", csv, f"watchlist_{market_source}.csv", "text/csv")

    st.dataframe(res_df.drop(columns=['df']), use_container_width=True, hide_index=True)

    # Deep Dive
    target = st.selectbox("🎯 เลือกหุ้นเพื่อดูแผนภูมิ:", [r['Ticker'] for r in st.session_state['yfin_results']])
    target_df = next(item for item in st.session_state['yfin_results'] if item["Ticker"] == target)['df']
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
    fig.add_trace(go.Candlestick(x=target_df.index, open=target_df['Open'], high=target_df['High'], 
                                 low=target_df['Low'], close=target_df['Close'], name="Price"), row=1, col=1)
    fig.add_trace(go.Scatter(x=target_df.index, y=target_df['Sup'], line=dict(color='green', dash='dot'), name='Support'), row=1, col=1)
    fig.add_trace(go.Scatter(x=target_df.index, y=target_df['Res'], line=dict(color='red', dash='dot'), name='Resistance'), row=1, col=1)
    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("ระบบพร้อมสแกนหุ้นจากฐานข้อมูล yahoo_fin แล้ว!")
