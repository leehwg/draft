import datetime as dt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# Load the dataset once
DATA_FILE = "finland.csv"

@st.cache_data
def load_data(file_path):
    df = pd.read_csv(file_path, parse_dates=["Date"])
    df.sort_values(by=["Ticker", "Date"], inplace=True)
    return df

# Helper functions for indicators
def calculate_macd(df):
    short_ema = df["Price Close"].ewm(span=12, adjust=False).mean()
    long_ema = df["Price Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = short_ema - long_ema
    df["Signal Line"] = df["MACD"].ewm(span=9, adjust=False).mean()
    return df

def calculate_rsi(df, period=14):
    delta = df["Price Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))
    return df

# Initialize the Streamlit app
st.markdown('''
# Financial Dashboard Application

An interactive dashboard for visualizing stock prices and technical indicators using local data.

---

''')

# Sidebar for user input
st.sidebar.header("Query Parameters")
data = load_data(DATA_FILE)
tickers = data["Ticker"].unique()

ticker = st.sidebar.selectbox("Select Ticker:", options=tickers)
today = dt.datetime.today()

start_date = st.sidebar.date_input(
    "Start Date:",
    today - dt.timedelta(days=365),
    min_value=data["Date"].min(),
    max_value=today,
)

end_date = st.sidebar.date_input(
    "End Date:",
    today,
    min_value=start_date,
    max_value=data["Date"].max(),
)

# Filter data based on user input
filtered_data = data[(data["Ticker"] == ticker) & (data["Date"] >= pd.Timestamp(start_date)) & (data["Date"] <= pd.Timestamp(end_date))]

if filtered_data.empty:
    st.error("No data available for the selected parameters. Please adjust the date range or ticker.")
else:
    # Display filtered data
    st.markdown(f"## {ticker} - Price Data")
    st.dataframe(filtered_data)

    # Add technical indicators
    filtered_data = calculate_macd(filtered_data)
    filtered_data = calculate_rsi(filtered_data)

    # Create subplots
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        subplot_titles=("Candlestick Chart", "MACD", "RSI", "Volume"),
        row_width=[0.2, 0.2, 0.2, 0.6],
    )

    # Candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=filtered_data["Date"],
            open=filtered_data["Price Open"],
            high=filtered_data["Price High"],
            low=filtered_data["Price Low"],
            close=filtered_data["Price Close"],
            name="Candlestick",
        ),
        row=1,
        col=1,
    )

    # MACD
    fig.add_trace(
        go.Scatter(
            x=filtered_data["Date"],
            y=filtered_data["MACD"],
            line=dict(color="blue", width=1),
            name="MACD",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=filtered_data["Date"],
            y=filtered_data["Signal Line"],
            line=dict(color="red", width=1),
            name="Signal Line",
        ),
        row=2,
        col=1,
    )

    # RSI
    fig.add_trace(
        go.Scatter(
            x=filtered_data["Date"],
            y=filtered_data["RSI"],
            line=dict(color="purple", width=1),
            name="RSI",
        ),
        row=3,
        col=1,
    )

    # Volume
    fig.add_trace(
        go.Bar(
            x=filtered_data["Date"],
            y=filtered_data["Volume"],
            name="Volume",
        ),
        row=4,
        col=1,
    )

    # Update layout
    fig.update_layout(
        height=800,
        width=1000,
        title=f"{ticker} - Interactive Dashboard",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
    )

    # Render the chart
    st.plotly_chart(fig)

    st.write("**Disclaimer:** This dashboard is for educational purposes only and does not constitute financial advice.")
