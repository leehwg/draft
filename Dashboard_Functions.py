import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Load data from the local file
def load_data(filepath):
    """Load stock data from a local CSV file."""
    df = pd.read_csv(filepath)
    # Ensure Date is in datetime format
    df['Date'] = pd.to_datetime(df['Date'])
    return df

def get_closed_dates(df):
    """Return a list containing all dates on which the stock market was closed."""
    timeline = pd.date_range(start=df['Date'].iloc[0], end=df['Date'].iloc[-1])
    df_dates = [day.strftime('%Y-%m-%d') for day in pd.to_datetime(df['Date'])]
    closed_dates = [
        day for day in timeline.strftime('%Y-%m-%d').tolist()
        if day not in df_dates
    ]
    return closed_dates

def get_MACD(df, column='Price Close'):
    """Return a DataFrame with the MACD indicator and related information."""
    df['EMA-12'] = df[column].ewm(span=12, adjust=False).mean()
    df['EMA-26'] = df[column].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA-12'] - df['EMA-26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Histogram'] = df['MACD'] - df['Signal']
    return df

def get_RSI(df, column='Price Close', time_window=14):
    """Return a DataFrame with the RSI indicator for the specified time window."""
    diff = df[column].diff(1)
    up_chg = np.where(diff > 0, diff, 0)
    down_chg = np.where(diff < 0, -diff, 0)
    up_chg_avg = pd.Series(up_chg).ewm(com=time_window - 1, min_periods=time_window).mean()
    down_chg_avg = pd.Series(down_chg).ewm(com=time_window - 1, min_periods=time_window).mean()
    RS = up_chg_avg / down_chg_avg
    df['RSI'] = 100 - 100 / (1 + RS)
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
    for level, color, text in [(70, 'red', 'Overbought'), (30, 'green', 'Oversold')]:
        fig.add_hline(y=level, line=dict(color=color))
        fig.add_annotation(x=df['Date'].iloc[-1], y=level, text=text, showarrow=False, font=dict(color=color))
    fig.update_yaxes(title_text='RSI', row=row, col=column)
    return fig

# Main script
if __name__ == "__main__":
    data_filepath = "finland.csv"  # Replace with the path to your local file
    data = load_data(data_filepath)

    # Process the data
    data = get_MACD(data)
    data = get_RSI(data)
    data = get_trading_strategy(data)

    # Plot the data
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, subplot_titles=("Candlestick Chart", "MACD", "RSI", "Volume"))
    fig = plot_candlestick_chart(fig, data, row=1)
    fig = plot_MACD(fig, data, row=2)
    fig = plot_RSI(fig, data, row=3)
    fig.add_trace(go.Bar(x=data['Date'], y=data['Volume'], name='Volume'), row=4, col=1)
    fig.update_layout(title="Stock Analysis", showlegend=True, height=800)
    fig.show()
