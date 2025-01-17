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

def get_trading_strategy(df, column='Price Close'):
    """Return Buy/Sell signals based on the MACD strategy."""
    buy_list, sell_list = [], []
    flag = False
    for i in range(len(df)):
        if df['MACD'].iloc[i] > df['Signal'].iloc[i] and not flag:
            buy_list.append(df[column].iloc[i])
            sell_list.append(np.nan)
            flag = True
        elif df['MACD'].iloc[i] < df['Signal'].iloc[i] and flag:
            buy_list.append(np.nan)
            sell_list.append(df[column].iloc[i])
            flag = False
        else:
            buy_list.append(np.nan)
            sell_list.append(np.nan)
    df['Buy'] = buy_list
    df['Sell'] = sell_list
    return df

def plot_candlestick_chart(fig, df, row, column=1, plot_EMAs=True, plot_strategy=True):
    """Return a Candlestick chart."""
    fig.add_trace(go.Candlestick(x=df['Date'],
                                 open=df['Price Open'],
                                 high=df['Price High'],
                                 low=df['Price Low'],
                                 close=df['Price Close'],
                                 name='Candlestick Chart'),
                  row=row, col=column)
    if plot_EMAs:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['EMA-12'], name='12-period EMA', line=dict(color='blue')), row=row, col=column)
        fig.add_trace(go.Scatter(x=df['Date'], y=df['EMA-26'], name='26-period EMA', line=dict(color='red')), row=row, col=column)
    if plot_strategy:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Buy'], name='Buy Signal', mode='markers', marker=dict(color='green', symbol='triangle-up', size=10)), row=row, col=column)
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Sell'], name='Sell Signal', mode='markers', marker=dict(color='red', symbol='triangle-down', size=10)), row=row, col=column)
    fig.update_yaxes(title_text='Price', row=row, col=column)
    return fig

def plot_MACD(fig, df, row, column=1):
    """Return a MACD chart."""
    df['Hist-Color'] = np.where(df['Histogram'] < 0, 'red', 'green')
    fig.add_trace(go.Bar(x=df['Date'], y=df['Histogram'], marker_color=df['Hist-Color'], name='Histogram'), row=row, col=column)
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MACD'], name='MACD', line=dict(color='orange')), row=row, col=column)
    fig.add_trace(go.Scatter(x=df['Date'], y=df['Signal'], name='Signal', line=dict(color='blue')), row=row, col=column)
    fig.update_yaxes(title_text='MACD', row=row, col=column)
    return fig

def plot_RSI(fig, df, row, column=1):
    """Return an RSI chart."""
    fig.add_trace(go.Scatter(x=df['Date'], y=df['RSI'], name='RSI', line=dict(color='gold')), row=row, col=column)
    for level, color, text in [(70, 'red', 'Overbought'), (30, 'green', 'Oversold')] :
        fig.add_hline(y=level, line=dict(color=color))
        fig.add_annotation(x=df['Date'].iloc[-1], y=level, text=text, showarrow=False, font=dict(color=color))
    fig.update_yaxes(title_text='RSI', row=row, col=column)
    return fig

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
    filtered_data = get_trading_strategy(filtered_data)

    # Create subplots
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        subplot_titles=("Candlestick Chart", "MACD", "RSI", "Volume"),
        row_width=[0.2, 0.2, 0.2, 0.6],
    )

    # Plot Candlestick chart
    fig = plot_candlestick_chart(fig, filtered_data, row=1)
    # Plot MACD
    fig = plot_MACD(fig, filtered_data, row=2)
    # Plot RSI
    fig = plot_RSI(fig, filtered_data, row=3)

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
