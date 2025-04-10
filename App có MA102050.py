import streamlit as st
import pandas as pd
import numpy as np
import datetime, os, json
import plotly.express as px
import plotly.graph_objects as go
import streamlit.components.v1 as components


##############################################
# 1. Hàm tải dữ liệu chung từ file Excel
##############################################
def load_data_for_date(date_str):
    """
    Tải dữ liệu từ file Excel dựa trên chuỗi ngày đã nhập (YYYYMMDD).
    File được đọc từ dòng 8 đến dòng 27 (bỏ qua 7 dòng đầu, chỉ lấy 20 dòng).
    Dòng đầu (dòng 8) làm header, sau đó loại bỏ đuôi "L2" ở cột A nếu có.
    """
    file_path = f"Data GD/FiinTrade_Ngành-chuyên-sâu_Phân-Loại-Nhà-Đầu-Tư__1 NGÀY_{date_str}.xlsx"
    if not os.path.exists(file_path):
        st.error(f"File không tồn tại: {file_path}")
        return None
    try:
        df_temp = pd.read_excel(file_path, header=None, skiprows=7, nrows=20)
        df_temp.iloc[:, 0] = df_temp.iloc[:, 0].astype(str).str.replace(r'\s*L2$', '', regex=True)
        df_temp.columns = df_temp.iloc[0]
        df = df_temp[1:].reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Lỗi khi đọc file: {e}")
        return None


def get_offset_date_str(date_str, offset_days):
    """
    Trả về chuỗi ngày (YYYYMMDD) sau khi trừ đi offset_days.
    """
    date_obj = datetime.datetime.strptime(date_str, "%Y%m%d").date()
    new_date = date_obj - datetime.timedelta(days=offset_days)
    return new_date.strftime("%Y%m%d")


##############################################
# 2. Các hàm bổ trợ cho biểu đồ "Biều đồ về giá của từng cổ phiếu"
##############################################
def parse_mixed_date(date_str):
    """
    Thử parse chuỗi ngày với dayfirst=True (dd/mm/yyyy).
    Nếu lỗi, thử với dayfirst=False.
    Ưu tiên dd/mm.
    """
    try:
        return pd.to_datetime(date_str, dayfirst=True, errors='raise')
    except Exception:
        try:
            return pd.to_datetime(date_str, dayfirst=False, errors='raise')
        except Exception:
            return pd.NaT


def load_circle_packing_data(price_file, volume_file, start_date, end_date):
    """
    Đọc và xử lý dữ liệu từ file giá và volume trong khoảng thời gian được chọn.
    Trả về DataFrame gồm các cột: symbol, sector, volume, PriceChange.
    """
    df_price = pd.read_excel(price_file)
    df_price.columns = (
            ["symbol", "sector"] +
            pd.to_datetime(df_price.columns[2:], format="%d/%m/%Y", dayfirst=True, errors="coerce")
            .strftime("%Y-%m-%d").tolist()
    )
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    if start_date_str not in df_price.columns or end_date_str not in df_price.columns:
        raise ValueError(f"Ngày {start_date_str} hoặc {end_date_str} không có trong dữ liệu giá!")
    df_price = df_price[["symbol", "sector", start_date_str, end_date_str]].copy()
    df_price["PriceChange"] = ((df_price[end_date_str] - df_price[start_date_str]) / df_price[start_date_str] * 100)

    df_vol = pd.read_excel(volume_file)
    df_vol.columns = (
            ["symbol", "sector"] +
            pd.to_datetime(df_vol.columns[2:], format="%d/%m/%Y", dayfirst=True, errors="coerce")
            .strftime("%Y-%m-%d").tolist()
    )
    # Lấy các cột volume nằm trong khoảng [start_date_str, end_date_str]
    date_cols_vol = [c for c in df_vol.columns[2:] if start_date_str <= c <= end_date_str]
    if len(date_cols_vol) == 0:
        raise ValueError(f"Không có cột nào trong khoảng {start_date_str} đến {end_date_str} trong dữ liệu volume!")
    df_vol["volume"] = df_vol[date_cols_vol].sum(axis=1)
    df_vol = df_vol[["symbol", "sector", "volume"]]

    df_merged = pd.merge(df_price, df_vol, on=["symbol", "sector"], how="inner")
    df_final = df_merged[["symbol", "sector", "volume", "PriceChange"]]
    return df_final


def build_hierarchical_data(df_final):
    """
    Xây dựng dữ liệu phân cấp cho biểu đồ Circle Packing.
    Trả về dictionary với cấu trúc phân cấp: root -> sector -> cổ phiếu.
    """
    root = {"name": "Toàn thị trường", "children": []}
    unique_sectors = df_final["sector"].dropna().unique().tolist()
    for sec in unique_sectors:
        df_ind = df_final[df_final["sector"] == sec]
        children_stocks = []
        for _, row in df_ind.iterrows():
            children_stocks.append({
                "name": row["symbol"],
                "value": float(row["volume"]),
                "PriceChange": float(row["PriceChange"]) if not pd.isna(row["PriceChange"]) else 0
            })
        root["children"].append({
            "name": sec,
            "children": children_stocks
        })
    return root


def generate_circle_packing_html(hierarchical_data_json):
    """
    Tạo HTML với D3.js để hiển thị biểu đồ Circle Packing với tooltip và nền trong suốt.
    """
    html_code = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <script src="https://d3js.org/d3.v7.min.js"></script>
        <style>
            body {{
                margin: 0;
                padding: 0;
                background: transparent;
                font-family: Arial, sans-serif;
            }}
            #chart {{
                margin: auto;
            }}
            text {{
                font-size: 12px;
                fill: #333;
                text-anchor: middle;
                pointer-events: none;
            }}
            .tooltip {{
                position: absolute;
                visibility: hidden;
                background: rgba(255, 255, 255, 0.9);
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
                font-size: 12px;
                color: #000;
            }}
        </style>
    </head>
    <body>
        <div id="chart"></div>
        <div class="tooltip" id="tooltip"></div>
        <script>
            var data = {hierarchical_data_json};

            var width = 600, height = 600;
            var pack = d3.pack().size([width, height]).padding(3);
            var root = d3.hierarchy(data).sum(function(d) {{ return d.value; }});
            var svg = d3.select("#chart").append("svg")
                        .attr("width", width)
                        .attr("height", height)
                        .style("background", "none");
            var nodes = pack(root).descendants();
            var tooltip = d3.select("#tooltip");

            var node = svg.selectAll("g")
                          .data(nodes)
                          .enter().append("g")
                          .attr("transform", function(d) {{ return "translate(" + d.x + "," + d.y + ")"; }});

            node.append("circle")
                .attr("r", function(d) {{ return d.r; }})
                .attr("fill", function(d) {{
                    if(d.depth === 0) return "#f0f0f0";
                    else if(d.depth === 1) return "#add8e6";
                    else return (d.data.PriceChange >= 0) ? "#2ecc71" : "#e74c3c";
                }})
                .attr("stroke", "#999")
                .attr("stroke-width", 1)
                .on("mouseover", function(event, d) {{
                    var name = d.data.name || "";
                    var pc = d.data.PriceChange != null ? d.data.PriceChange.toFixed(2) + "%" : "N/A";
                    tooltip.html("<b>" + name + "</b><br/>%Thay đổi giá: " + pc)
                           .style("visibility", "visible");
                }})
                .on("mousemove", function(event) {{
                    tooltip.style("left", (event.pageX + 10) + "px")
                           .style("top", (event.pageY + 10) + "px");
                }})
                .on("mouseout", function() {{
                    tooltip.style("visibility", "hidden");
                }});

            node.append("text")
                .text(function(d) {{ return d.data.name; }})
                .attr("dy", "0.3em")
                .style("fill-opacity", function(d) {{ return d.r > 15 ? 1 : 0; }});
        </script>
    </body>
    </html>
    """
    return html_code


##############################################
# 3. Main ứng dụng Streamlit
##############################################
def main():
    st.title("Stock Dashboard")
    st.markdown("*Dashboard này cung cấp thông tin tổng quan về thị trường chứng khoán theo ngày bạn chọn!*")

    dashboard_option = st.sidebar.selectbox(
        "Chọn dashboard bạn muốn xem:",
        (
            "Phân loại ngành",
            "Thống kê giao dịch trong và ngoài nước",
            "Vốn hóa của cổ phiếu và thị trường",
            "Biều đồ về giá của từng cổ phiếu",
            "Thống kê dòng tiền giao dịch"
        )
    )

    ##################################
    # Dashboard: Phân loại ngành
    ##################################
    if dashboard_option == "Phân loại ngành":
        st.markdown("### Hiển thị thống kê các ngành trong thị trường chứng khoán")
        file_path = "Phan_loai_nganh.xlsx"
        df = pd.read_excel(file_path)
        if "STT" in df.columns:
            df = df.drop("STT", axis=1)

        filter_ma = st.sidebar.text_input("Lọc theo Mã cổ phiếu:")
        filter_san = st.sidebar.multiselect("Lọc theo Sàn:",
                                            options=df["Sàn"].dropna().unique()) if "Sàn" in df.columns else []
        icb1_options = st.sidebar.multiselect("Lọc theo Ngành ICB - cấp 1:",
                                              options=df["Ngành ICB - cấp 1"].dropna().unique())
        icb2_options = st.sidebar.multiselect("Lọc theo Ngành ICB - cấp 2:",
                                              options=df["Ngành ICB - cấp 2"].dropna().unique())
        icb3_options = st.sidebar.multiselect("Lọc theo Ngành ICB - cấp 3:",
                                              options=df["Ngành ICB - cấp 3"].dropna().unique())
        icb4_options = st.sidebar.multiselect("Lọc theo Ngành ICB - cấp 4:",
                                              options=df["Ngành ICB - cấp 4"].dropna().unique())

        filtered_df = df.copy()
        if filter_ma:
            filtered_df = filtered_df[filtered_df['Mã'].astype(str).str.contains(filter_ma, case=False)]
        if filter_san:
            filtered_df = filtered_df[filtered_df['Sàn'].isin(filter_san)]
        if icb1_options:
            filtered_df = filtered_df[filtered_df["Ngành ICB - cấp 1"].isin(icb1_options)]
        if icb2_options:
            filtered_df = filtered_df[filtered_df["Ngành ICB - cấp 2"].isin(icb2_options)]
        if icb3_options:
            filtered_df = filtered_df[filtered_df["Ngành ICB - cấp 3"].isin(icb3_options)]
        if icb4_options:
            filtered_df = filtered_df[filtered_df["Ngành ICB - cấp 4"].isin(icb4_options)]

        st.dataframe(filtered_df)
        st.subheader("Biểu đồ phân bố dữ liệu")
        chart_layout = dict(width=350, height=350, margin=dict(l=20, r=20, t=40, b=20))

        if "Sàn" in filtered_df.columns:
            counts = filtered_df["Sàn"].value_counts()
            fig = px.bar(
                x=counts.index,
                y=counts.values,
                title="Số lượng mã cổ phiếu thuộc từng sàn",
                labels={"x": "Sàn giao dịch", "y": "Số lượng cổ phiếu tại các sàn"},
                color=counts.index,
                color_discrete_sequence=px.colors.qualitative.Plotly
            )
            fig.update_layout(width=700, height=350, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)

        icb_chart_columns = [
            ("Ngành ICB - cấp 1", "Tỷ lệ Ngành ICB - cấp 1"),
            ("Ngành ICB - cấp 2", "Tỷ lệ Ngành ICB - cấp 2"),
            ("Ngành ICB - cấp 3", "Tỷ lệ Ngành ICB - cấp 3"),
            ("Ngành ICB - cấp 4", "Tỷ lệ Ngành ICB - cấp 4")
        ]
        for i in range(0, len(icb_chart_columns), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(icb_chart_columns):
                    col_field, title = icb_chart_columns[i + j]
                    if col_field in filtered_df.columns:
                        if col_field in ["Ngành ICB - cấp 3", "Ngành ICB - cấp 4"]:
                            counts = filtered_df[col_field].value_counts()
                            total = counts.sum()
                            large = counts[counts / total * 100 >= 3]
                            small = counts[counts / total * 100 < 3]
                            if small.sum() > 0:
                                large["Khác"] = small.sum()
                            final_counts = large
                            fig = px.pie(values=final_counts.values, names=final_counts.index, title=title, hole=0.3)
                        else:
                            counts = filtered_df[col_field].value_counts()
                            fig = px.pie(values=counts.values, names=counts.index, title=title, hole=0.3)
                        fig.update_layout(**chart_layout)
                        cols[j].plotly_chart(fig, use_container_width=True)

    ##################################
    # Dashboard: Vốn hóa của cổ phiếu và thị trường
    ##################################
    elif dashboard_option == "Vốn hóa của cổ phiếu và thị trường":
        st.write("Hiển thị sự tăng trưởng vốn hóa của từng cổ phiếu và mức độ phân bổ vốn hóa của thị trường.")
        file_path = "Vietnam_Marketcap(Final).xlsx"
        df_marketcap = pd.read_excel(file_path)
        st.dataframe(df_marketcap)
        st.subheader("Biểu đồ Line: Thay đổi vốn hóa của cổ phiếu")
        stock_input = st.text_input("Nhập mã cổ phiếu:")
        start_date = pd.to_datetime("04/03/2019", dayfirst=True).date()
        end_date = pd.to_datetime("04/04/2025", dayfirst=True).date()
        date_range = st.slider("Chọn khoảng thời gian:", min_value=start_date, max_value=end_date,
                               value=(start_date, end_date), format="DD/MM/YYYY")
        if stock_input:
            row = df_marketcap[df_marketcap["symbol"].astype(str).str.upper() == stock_input.upper()]
            if not row.empty:
                row_melt = row.melt(id_vars=["symbol"], var_name="Date", value_name="Marketcap")
                row_melt["Date"] = pd.to_datetime(row_melt["Date"], dayfirst=True, errors="coerce")
                mask = (row_melt["Date"] >= pd.to_datetime(date_range[0])) & (
                            row_melt["Date"] <= pd.to_datetime(date_range[1]))
                row_filtered = row_melt[mask]
                if not row_filtered.empty:
                    fig_line = px.line(row_filtered, x="Date", y="Marketcap",
                                       title=f"Thay đổi vốn hóa cho {stock_input}")
                    st.plotly_chart(fig_line, use_container_width=True)
                else:
                    st.warning("Không có dữ liệu trong khoảng thời gian chọn.")
            else:
                st.error("Không tìm thấy mã cổ phiếu.")
        date_columns = df_marketcap.columns[1:]
        date_list = pd.to_datetime(date_columns, format="%d/%m/%Y", errors="coerce")
        start_date_market = date_list.min()
        end_date_market = date_list.max()
        st.subheader("📊 Biểu đồ Treemap: Vốn hóa của các cổ phiếu theo ngày")
        selected_date = st.date_input("📅 Chọn ngày để xem biểu đồ Treemap", value=start_date_market,
                                      min_value=start_date_market, max_value=end_date_market)
        selected_date_str = selected_date.strftime("%d/%m/%Y")
        if selected_date_str in df_marketcap.columns:
            df_treemap = df_marketcap[["symbol", selected_date_str]].rename(columns={selected_date_str: "Marketcap"})
            df_treemap = df_treemap.dropna(subset=["Marketcap"])
            df_treemap["Marketcap"] = pd.to_numeric(df_treemap["Marketcap"], errors="coerce")
            df_treemap = df_treemap.dropna(subset=["Marketcap"])
            fig_treemap = px.treemap(df_treemap, path=["symbol"], values="Marketcap", color="Marketcap",
                                     color_continuous_scale="Blues",
                                     title=f"Vốn hóa thị trường ngày {selected_date.strftime('%d/%m/%Y')}")
            st.plotly_chart(fig_treemap, use_container_width=True)
            st.markdown(f"Dữ liệu vốn hoá ngày {selected_date.strftime('%d/%m/%Y')}")
            st.dataframe(df_treemap)
        else:
            st.warning(f"⚠️ Không có dữ liệu cho ngày {selected_date.strftime('%d/%m/%Y')}.")

    ##################################
    # Dashboard: Thống kê giao dịch trong và ngoài nước (Heatmap + Pie Charts)
    ##################################
    elif dashboard_option == "Thống kê giao dịch trong và ngoài nước":
        st.markdown("### Hiển thị thống kê giao dịch trong và ngoài nước để đánh giá xu hướng thị trường")
        date_str = st.sidebar.text_input("Nhập ngày (ví dụ: 20220520):", value="20220520", key="txn_date")
        try:
            current_date = datetime.datetime.strptime(date_str, "%Y%m%d").date()
        except Exception:
            st.error("Ngày nhập không hợp lệ! Vui lòng nhập theo định dạng YYYYMMDD.")
            return

        df_today = load_data_for_date(date_str)
        df_d1 = load_data_for_date(get_offset_date_str(date_str, 1))
        df_d2 = load_data_for_date(get_offset_date_str(date_str, 2))
        df_d3 = load_data_for_date(get_offset_date_str(date_str, 3))
        df_d4 = load_data_for_date(get_offset_date_str(date_str, 4))

        if df_today is not None and df_d1 is not None and df_d2 is not None and df_d3 is not None and df_d4 is not None:
            # --- Heatmap cho "Nước ngoài Tổng GT Ròng" ---
            result = pd.DataFrame()
            result["Ngành"] = df_today["Ngành"].values
            result["D-1"] = df_today["Nước ngoài Tổng GT Ròng"].astype(float) - df_d1["Nước ngoài Tổng GT Ròng"].astype(
                float)
            result["D-2"] = df_today["Nước ngoài Tổng GT Ròng"].astype(float) - df_d2["Nước ngoài Tổng GT Ròng"].astype(
                float)
            result["D-3"] = df_today["Nước ngoài Tổng GT Ròng"].astype(float) - df_d3["Nước ngoài Tổng GT Ròng"].astype(
                float)
            result["D-4"] = df_today["Nước ngoài Tổng GT Ròng"].astype(float) - df_d4["Nước ngoài Tổng GT Ròng"].astype(
                float)
            df_heatmap = result.set_index("Ngành")[["D-1", "D-2", "D-3", "D-4"]]
            z = df_heatmap.values
            limit = max(abs(z.min()), abs(z.max()))
            colorscale = [
                [0.0, "rgba(255,0,0,0.7)"],
                [0.5, "rgba(255,255,255,0.7)"],
                [1.0, "rgba(0,255,0,0.7)"]
            ]
            heatmap = go.Heatmap(
                z=df_heatmap.values,
                x=df_heatmap.columns,
                y=df_heatmap.index,
                colorscale=colorscale,
                zmin=-limit,
                zmax=limit,
                hoverongaps=False,
                text=df_heatmap.values,
                texttemplate="%{text:.2f}",
                textfont={"size": 12}
            )
            fig = go.Figure(data=[heatmap])
            date_obj = datetime.datetime.strptime(date_str, "%Y%m%d").date()
            date_final = date_obj.strftime("%d/%m/%y")
            fig.update_layout(
                title={
                    'text': f"Tổng hợp sự thay đổi về dòng vốn nước ngoài tại thời điểm {date_final}",
                    'x': 0.5,
                    'xanchor': 'center'
                },
                xaxis_title="<b>Sự thay đổi về giá so với từng thời điểm</b>",
                yaxis_title="<b>Ngành</b>",
                margin=dict(l=40, r=40, t=50, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white")
            )
            fig.update_xaxes(tickangle=0, automargin=True)
            fig.update_yaxes(automargin=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.plotly_chart(fig, use_container_width=True)

            # --- Heatmap cho "Tự doanh Tổng GT Ròng" ---
            st.markdown("### Heatmap: Thay đổi về Tự doanh Tổng GT Ròng")
            result_td = pd.DataFrame()
            result_td["Ngành"] = df_today["Ngành"].values
            result_td["D-1"] = df_today["Tự doanh Tổng GT Ròng"].astype(float) - df_d1["Tự doanh Tổng GT Ròng"].astype(
                float)
            result_td["D-2"] = df_today["Tự doanh Tổng GT Ròng"].astype(float) - df_d2["Tự doanh Tổng GT Ròng"].astype(
                float)
            result_td["D-3"] = df_today["Tự doanh Tổng GT Ròng"].astype(float) - df_d3["Tự doanh Tổng GT Ròng"].astype(
                float)
            result_td["D-4"] = df_today["Tự doanh Tổng GT Ròng"].astype(float) - df_d4["Tự doanh Tổng GT Ròng"].astype(
                float)
            df_heatmap_td = result_td.set_index("Ngành")[["D-1", "D-2", "D-3", "D-4"]]
            z_td = df_heatmap_td.values
            limit_td = max(abs(z_td.min()), abs(z_td.max()))
            heatmap_td = go.Heatmap(
                z=df_heatmap_td.values,
                x=df_heatmap_td.columns,
                y=df_heatmap_td.index,
                colorscale=colorscale,
                zmin=-limit_td,
                zmax=limit_td,
                hoverongaps=False,
                text=df_heatmap_td.values,
                texttemplate="%{text:.2f}",
                textfont={"size": 12}
            )
            fig_td = go.Figure(data=[heatmap_td])
            fig_td.update_layout(
                title={
                    'text': f"Tổng hợp sự thay đổi về dòng vốn tự doanh tại thời điểm {date_final}",
                    'x': 0.5,
                    'xanchor': 'center'
                },
                xaxis_title="<b>Sự thay đổi về giá so với từng thời điểm</b>",
                yaxis_title="<b>Ngành</b>",
                margin=dict(l=40, r=40, t=50, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white")
            )
            fig_td.update_xaxes(tickangle=0, automargin=True)
            fig_td.update_yaxes(automargin=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.plotly_chart(fig_td, use_container_width=True)

            # --- Heatmap cho "Tổ chức trong nước Tổng GT Ròng" ---
            st.markdown("### Heatmap: Thay đổi về Tổ chức trong nước Tổng GT Ròng")
            result_org = pd.DataFrame()
            result_org["Ngành"] = df_today["Ngành"].values
            result_org["D-1"] = df_today["Tổ chức trong nước Tổng GT Ròng"].astype(float) - df_d1[
                "Tổ chức trong nước Tổng GT Ròng"].astype(float)
            result_org["D-2"] = df_today["Tổ chức trong nước Tổng GT Ròng"].astype(float) - df_d2[
                "Tổ chức trong nước Tổng GT Ròng"].astype(float)
            result_org["D-3"] = df_today["Tổ chức trong nước Tổng GT Ròng"].astype(float) - df_d3[
                "Tổ chức trong nước Tổng GT Ròng"].astype(float)
            result_org["D-4"] = df_today["Tổ chức trong nước Tổng GT Ròng"].astype(float) - df_d4[
                "Tổ chức trong nước Tổng GT Ròng"].astype(float)
            df_heatmap_org = result_org.set_index("Ngành")[["D-1", "D-2", "D-3", "D-4"]]
            z_org = df_heatmap_org.values
            limit_org = max(abs(z_org.min()), abs(z_org.max()))
            heatmap_org = go.Heatmap(
                z=df_heatmap_org.values,
                x=df_heatmap_org.columns,
                y=df_heatmap_org.index,
                colorscale=colorscale,
                zmin=-limit_org,
                zmax=limit_org,
                hoverongaps=False,
                text=df_heatmap_org.values,
                texttemplate="%{text:.2f}",
                textfont={"size": 12}
            )
            fig_org = go.Figure(data=[heatmap_org])
            fig_org.update_layout(
                title={
                    'text': f"Tổng hợp sự thay đổi về Tổ chức trong nước Tổng GT Ròng tại thời điểm {date_final}",
                    'x': 0.5,
                    'xanchor': 'center'
                },
                xaxis_title="<b>Sự thay đổi về giá so với từng thời điểm</b>",
                yaxis_title="<b>Ngành</b>",
                margin=dict(l=40, r=40, t=50, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white")
            )
            fig_org.update_xaxes(tickangle=0, automargin=True)
            fig_org.update_yaxes(automargin=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.plotly_chart(fig_org, use_container_width=True)

            # --- Heatmap cho "Cá nhân Tổng GT Ròng" ---
            st.markdown("### Heatmap: Thay đổi về Cá nhân Tổng GT Ròng")
            result_ind = pd.DataFrame()
            result_ind["Ngành"] = df_today["Ngành"].values
            result_ind["D-1"] = df_today["Cá nhân Tổng GT Ròng"].astype(float) - df_d1["Cá nhân Tổng GT Ròng"].astype(
                float)
            result_ind["D-2"] = df_today["Cá nhân Tổng GT Ròng"].astype(float) - df_d2["Cá nhân Tổng GT Ròng"].astype(
                float)
            result_ind["D-3"] = df_today["Cá nhân Tổng GT Ròng"].astype(float) - df_d3["Cá nhân Tổng GT Ròng"].astype(
                float)
            result_ind["D-4"] = df_today["Cá nhân Tổng GT Ròng"].astype(float) - df_d4["Cá nhân Tổng GT Ròng"].astype(
                float)
            df_heatmap_ind = result_ind.set_index("Ngành")[["D-1", "D-2", "D-3", "D-4"]]
            z_ind = df_heatmap_ind.values
            limit_ind = max(abs(z_ind.min()), abs(z_ind.max()))
            heatmap_ind = go.Heatmap(
                z=df_heatmap_ind.values,
                x=df_heatmap_ind.columns,
                y=df_heatmap_ind.index,
                colorscale=colorscale,
                zmin=-limit_ind,
                zmax=limit_ind,
                hoverongaps=False,
                text=df_heatmap_ind.values,
                texttemplate="%{text:.2f}",
                textfont={"size": 12}
            )
            fig_ind = go.Figure(data=[heatmap_ind])
            fig_ind.update_layout(
                title={
                    'text': f"Tổng hợp sự thay đổi về Cá nhân Tổng GT Ròng tại thời điểm {date_final}",
                    'x': 0.5,
                    'xanchor': 'center'
                },
                xaxis_title="<b>Sự thay đổi về giá so với từng thời điểm</b>",
                yaxis_title="<b>Ngành</b>",
                margin=dict(l=40, r=40, t=50, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white")
            )
            fig_ind.update_xaxes(tickangle=0, automargin=True)
            fig_ind.update_yaxes(automargin=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.plotly_chart(fig_ind, use_container_width=True)

            # --- Pie chart: Nước ngoài Khớp Ròng vs Nước ngoài Thỏa thuận Ròng ---
            total_nuocngoai = abs(df_today["Nước ngoài Tổng GT Ròng"].astype(float).sum())
            total_nuocngoai_khop = abs(df_today["Nước ngoài Khớp Ròng"].astype(float).sum())
            total_nuocngoai_thoa = abs(df_today["Nước ngoài Thỏa thuận Ròng"].astype(float).sum())
            perc_nuocngoai_khop = (total_nuocngoai_khop / total_nuocngoai) * 100 if total_nuocngoai != 0 else 0
            perc_nuocngoai_thoa = (total_nuocngoai_thoa / total_nuocngoai) * 100 if total_nuocngoai != 0 else 0
            data_pie_nuocngoai = {
                "Loại": ["Nước ngoài Khớp Ròng", "Nước ngoài Thỏa thuận Ròng"],
                "Tỷ lệ (%)": [perc_nuocngoai_khop, perc_nuocngoai_thoa]
            }
            fig_pie_nuocngoai = px.pie(data_pie_nuocngoai, values="Tỷ lệ (%)", names="Loại",
                                       title="Tỷ lệ % giữa Nước ngoài Khớp Ròng và Nước ngoài Thỏa thuận Ròng",
                                       hole=0.3)

            # --- Pie chart: Tự doanh Khớp Ròng vs Tự doanh Thỏa thuận Ròng ---
            total_tudn = abs(df_today["Tự doanh Tổng GT Ròng"].astype(float).sum())
            total_tudn_khop = abs(df_today["Tự doanh Khớp Ròng"].astype(float).sum())
            total_tudn_thoa = abs(df_today["Tự doanh Thỏa thuận Ròng"].astype(float).sum())
            perc_tudn_khop = (total_tudn_khop / total_tudn) * 100 if total_tudn != 0 else 0
            perc_tudn_thoa = (total_tudn_thoa / total_tudn) * 100 if total_tudn != 0 else 0
            data_pie_tudn = {
                "Loại": ["Tự doanh Khớp Ròng", "Tự doanh Thỏa thuận Ròng"],
                "Tỷ lệ (%)": [perc_tudn_khop, perc_tudn_thoa]
            }
            fig_pie_tudn = px.pie(data_pie_tudn, values="Tỷ lệ (%)", names="Loại",
                                  title="Tỷ lệ % giữa Tự doanh Khớp Ròng và Tự doanh Thỏa thuận Ròng", hole=0.3)

            # Sắp xếp hai biểu đồ pie chart đầu tiên trên cùng 1 hàng
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(fig_pie_nuocngoai, use_container_width=True)
            with col2:
                st.plotly_chart(fig_pie_tudn, use_container_width=True)

            # --- Pie chart: Cá nhân Khớp Ròng vs Cá nhân Thỏa thuận Ròng ---
            total_canhan = abs(df_today["Cá nhân Tổng GT Ròng"].astype(float).sum())
            total_canhan_khop = abs(df_today["Cá nhân Khớp Ròng"].astype(float).sum())
            total_canhan_thoa = abs(df_today["Cá nhân Thỏa thuận Ròng"].astype(float).sum())
            perc_canhan_khop = (total_canhan_khop / total_canhan) * 100 if total_canhan != 0 else 0
            perc_canhan_thoa = (total_canhan_thoa / total_canhan) * 100 if total_canhan != 0 else 0
            data_pie_canhan = {
                "Loại": ["Cá nhân Khớp Ròng", "Cá nhân Thỏa thuận Ròng"],
                "Tỷ lệ (%)": [perc_canhan_khop, perc_canhan_thoa]
            }
            fig_pie_canhan = px.pie(data_pie_canhan, values="Tỷ lệ (%)", names="Loại",
                                    title="Tỷ lệ % giữa Cá nhân Khớp Ròng và Cá nhân Thỏa thuận Ròng", hole=0.3)

            # --- Pie chart: Tổ chức trong nước Khớp Ròng vs Tổ chức trong nước Thỏa thuận Ròng ---
            total_tochuc = abs(df_today["Tổ chức trong nước Tổng GT Ròng"].astype(float).sum())
            total_tochuc_khop = abs(df_today["Tổ chức trong nước Khớp Ròng"].astype(float).sum())
            total_tochuc_thoa = abs(df_today["Tổ chức trong nước Thỏa thuận Ròng"].astype(float).sum())
            perc_tochuc_khop = (total_tochuc_khop / total_tochuc) * 100 if total_tochuc != 0 else 0
            perc_tochuc_thoa = (total_tochuc_thoa / total_tochuc) * 100 if total_tochuc != 0 else 0
            data_pie_tochuc = {
                "Loại": ["Tổ chức trong nước Khớp Ròng", "Tổ chức trong nước Thỏa thuận Ròng"],
                "Tỷ lệ (%)": [perc_tochuc_khop, perc_tochuc_thoa]
            }
            fig_pie_tochuc = px.pie(data_pie_tochuc, values="Tỷ lệ (%)", names="Loại",
                                    title="Tỷ lệ % giữa Tổ chức trong nước Khớp Ròng và Tổ chức trong nước Thỏa thuận Ròng",
                                    hole=0.3)

            # Sắp xếp hai biểu đồ pie chart tiếp theo trên cùng 1 hàng
            col3, col4 = st.columns(2)
            with col3:
                st.plotly_chart(fig_pie_canhan, use_container_width=True)
            with col4:
                st.plotly_chart(fig_pie_tochuc, use_container_width=True)
        else:
            st.error("Không đủ dữ liệu để tính toán hiệu số.")

    ##################################
    # Dashboard: Biều đồ về giá của từng cổ phiếu
    ##################################
    elif dashboard_option == "Biều đồ về giá của từng cổ phiếu":
        st.markdown(
            """
            <style>
            div[data-testid="stTabs"] {
                margin-bottom: 10px; 
            }
            div[data-testid="stTabs"] button {
                margin-right: 8px !important;
                border: none !important;
                border-radius: 6px !important;
                background: #fafafa !important;
                color: #444 !important;
                font-weight: 500 !important;
                transition: background 0.2s;
                cursor: pointer;
            }
            div[data-testid="stTabs"] button:hover {
                background: #f0f0f0 !important; 
            }
            div[data-testid="stTabs"] button[aria-selected="true"] {
                background: #1976d2 !important;
                color: #FFF !important;
                border: none !important;
            }
            div[data-testid="stTabs"] button div[data-testid="stMarkdownContainer"] p {
                padding: 6px 12px !important;
                margin: 0 !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        tab1, tab2 = st.tabs([
            "⚙️  Toàn cảnh thị trường",
            "📈  Biến động giá"
        ])

        with tab1:
            st.subheader("Toàn cảnh thị trường")
            price_file = "Vietnam_Price(Final).xlsx"
            volume_file = "Vietnam_volume(Final).xlsx"
            df_temp = pd.read_excel(price_file)
            date_cols_raw = df_temp.columns[2:]
            date_cols_parsed = pd.to_datetime(date_cols_raw, format="%d/%m/%Y", dayfirst=True, errors="coerce")
            valid_mask = ~date_cols_parsed.isna()
            valid_date_cols = date_cols_parsed[valid_mask]
            if len(valid_date_cols) == 0:
                st.error("Không tìm thấy cột ngày hợp lệ trong file giá!")
            else:
                min_date = valid_date_cols.min()
                max_date = valid_date_cols.max()
                c1, c2 = st.columns(2)
                with c1:
                    start_date_tc = st.date_input("Chọn ngày bắt đầu:", min_date.date(), format="DD/MM/YYYY",
                                                  min_value=min_date.date(), max_value=max_date.date())
                with c2:
                    end_date_tc = st.date_input("Chọn ngày kết thúc:", max_date.date(), format="DD/MM/YYYY",
                                                min_value=min_date.date(), max_value=max_date.date())
                if start_date_tc > end_date_tc:
                    st.error("Lỗi: Ngày bắt đầu phải trước ngày kết thúc!")
                else:
                    start_dt_tc = pd.to_datetime(start_date_tc)
                    end_dt_tc = pd.to_datetime(end_date_tc)
                    try:
                        df_final = load_circle_packing_data(price_file, volume_file, start_dt_tc, end_dt_tc)
                        df_final = df_final.sort_values(by=["sector", "volume", "PriceChange"],
                                                        ascending=[False, False, False])
                        root_dict = build_hierarchical_data(df_final)
                        json_data = json.dumps(root_dict, ensure_ascii=False)
                        html_code = generate_circle_packing_html(json_data)
                        components.html(html_code, height=650)
                        st.write("Dữ liệu hợp nhất:", df_final)
                    except Exception as e:
                        st.error(f"Lỗi: {str(e)}")

            st.subheader("Tỷ suất sinh lời trung bình theo ngành")
            df_ret = pd.read_excel(price_file)
            df_ret.columns = (
                    ["symbol", "sector"]
                    + pd.to_datetime(df_ret.columns[2:], format="%d/%m/%Y", dayfirst=True, errors="coerce").strftime(
                "%Y-%m-%d").tolist()
            )
            start_date_str = start_dt_tc.strftime("%Y-%m-%d")
            end_date_str = end_dt_tc.strftime("%Y-%m-%d")
            if start_date_str not in df_ret.columns or end_date_str not in df_ret.columns:
                st.warning(
                    f"Không tìm thấy cột {start_date_str} hoặc {end_date_str} trong file giá => không tính Return.")
            else:
                df_ret["Return"] = (df_ret[end_date_str] - df_ret[start_date_str]) / df_ret[start_date_str]
                sector_returns = df_ret.groupby("sector")["Return"].mean().reset_index()
                sector_returns["ReturnSign"] = np.where(sector_returns["Return"] >= 0, "Tỷ suất dương", "Tỷ suất âm")
                fig_ret = px.bar(
                    sector_returns,
                    x="sector",
                    y="Return",
                    color="ReturnSign",
                    title=" ",
                    color_discrete_map={
                        "Tỷ suất dương": "#169BD7",
                        "Tỷ suất âm": "#F7B600"
                    }
                )
                fig_ret.update_layout(
                    xaxis=dict(
                        categoryorder="category ascending",
                        tickangle=-90,
                    )
                )
                st.plotly_chart(fig_ret, use_container_width=True)

                #----------------------------------LINE CHART & VOLUME CHART------------------------

        with tab2:
            col_checkbox1, col_checkbox2 = st.columns(2)
            with col_checkbox1:
                show_line_chart = st.checkbox("Hiển thị Line Chart", value=True)
            with col_checkbox2:
                show_volume_chart = st.checkbox("Hiển thị Volume Chart", value=False)

            if show_line_chart:
                st.subheader("Biến động giá cổ phiếu")

                file_price = "Vietnam_Price(Final).xlsx"
                df_price = pd.read_excel(file_price)

                # Parse cột ngày
                parsed_dates = [parse_mixed_date(str(c)) for c in df_price.columns[2:]]
                df_price.columns = list(df_price.columns[:2]) + parsed_dates

                # Chuyển sang long format
                df_price_melted = df_price.melt(
                    id_vars=["symbol", "sector"],
                    var_name="date",
                    value_name="price"
                )

                stock_list = df_price["symbol"].unique()
                selected_stocks = st.multiselect("Chọn mã cổ phiếu:", options=stock_list)

                valid_dates = df_price_melted["date"].dropna()
                if valid_dates.empty:
                    st.error("Không có ngày hợp lệ trong file giá!")
                else:
                    min_d = valid_dates.min()
                    max_d = valid_dates.max()

                    col1, col2 = st.columns(2)
                    with col1:
                        start_date_line = st.date_input("Bắt đầu từ:",
                                                        min_d.date(),
                                                        format="DD/MM/YYYY",
                                                        min_value=min_d.date(),
                                                        max_value=max_d.date())
                    with col2:
                        end_date_line = st.date_input("Kết thúc vào:",
                                                      max_d.date(),
                                                      format="DD/MM/YYYY",
                                                      min_value=min_d.date(),
                                                      max_value=max_d.date())

                    start_dt_line = pd.to_datetime(start_date_line)
                    end_dt_line = pd.to_datetime(end_date_line)

                    # Lọc data
                    df_filtered = df_price_melted[
                        (df_price_melted["symbol"].isin(selected_stocks)) &
                        (df_price_melted["date"] >= start_dt_line) &
                        (df_price_melted["date"] <= end_dt_line)
                        ]

                    if selected_stocks and not df_filtered.empty:
                        st.write(
                            f"Dữ liệu từ **{start_dt_line.strftime('%d/%m/%Y')}** "
                            f"đến **{end_dt_line.strftime('%d/%m/%Y')}**"
                        )

                        df_filtered = df_filtered.sort_values(["symbol", "date"])
                        df_filtered["Base Price"] = df_filtered.groupby("symbol")["price"].transform("first")
                        df_filtered["% Change"] = (
                                (df_filtered["price"] - df_filtered["Base Price"]) /
                                df_filtered["Base Price"] * 100
                        )

                        # Biểu đồ line chung cho các cổ phiếu
                        fig_price = px.line(
                            df_filtered,
                            x="date",
                            y="price",
                            color="symbol",
                            title="Biến động giá (Nhiều cổ phiếu chung)"
                        )
                        fig_price.update_layout(yaxis_title="Giá cổ phiếu", xaxis_title="Ngày", height=400)
                        st.plotly_chart(fig_price, use_container_width=True)

                        # Thêm tính năng so sánh riêng
                        compare_separately = st.checkbox("So sánh riêng từng cổ phiếu", value=False)
                        if compare_separately:
                            st.subheader("Biểu đồ riêng cho từng cổ phiếu")

                            # Đặt 3 checkbox MA10, MA20, MA50 cùng trên 1 hàng
                            col_ma10, col_ma20, col_ma50 = st.columns(3)
                            with col_ma10:
                                show_ma10 = st.checkbox("MA10", value=False)
                            with col_ma20:
                                show_ma20 = st.checkbox("MA20", value=False)
                            with col_ma50:
                                show_ma50 = st.checkbox("MA50", value=False)

                            # Lần lượt vẽ chart riêng cho mỗi cổ phiếu
                            for stock in selected_stocks:
                                sub = df_filtered[df_filtered["symbol"] == stock].copy()
                                sub = sub.sort_values("date")

                                # Tính MA nếu có check
                                if show_ma10:
                                    sub["MA10"] = sub["price"].rolling(window=10).mean()
                                if show_ma20:
                                    sub["MA20"] = sub["price"].rolling(window=20).mean()
                                if show_ma50:
                                    sub["MA50"] = sub["price"].rolling(window=50).mean()

                                # Cột y cần vẽ
                                y_cols = ["price"]  # Luôn có cột giá
                                col_labels = ["Giá"]  # Nhãn hiển thị

                                if show_ma10:
                                    y_cols.append("MA10")
                                    col_labels.append("MA10")
                                if show_ma20:
                                    y_cols.append("MA20")
                                    col_labels.append("MA20")
                                if show_ma50:
                                    y_cols.append("MA50")
                                    col_labels.append("MA50")

                                # Vẽ line
                                fig_single = px.line(
                                    sub,
                                    x="date",
                                    y=y_cols,
                                    title=f"[{stock}] Biểu đồ giá & MA (nếu có)"
                                )

                                color_map_ma = {
                                    "price": "#0072B2",  # xanh
                                    "MA10": "#FF0000",  # đỏ
                                    "MA20": "#00A600",  # xanh lá
                                    "MA50": "#8B00FF"  # tím
                                }

                                # Đổi tên legend + chỉnh màu
                                for i, trace_name in enumerate(y_cols):
                                    fig_single.data[i].name = col_labels[i]
                                    # set màu
                                    if trace_name in color_map_ma:
                                        fig_single.data[i].line.color = color_map_ma[trace_name]

                                fig_single.update_layout(
                                    xaxis_title="Ngày",
                                    yaxis_title="Giá cổ phiếu",
                                    height=300
                                )
                                st.plotly_chart(fig_single, use_container_width=True)

                    else:
                        st.warning("Vui lòng chọn mã cổ phiếu (hoặc không có dữ liệu trong khoảng này).")

            if show_volume_chart:
                st.subheader("Khối lượng giao dịch")
                file_volume = "Vietnam_volume(Final).xlsx"
                df_volume = pd.read_excel(file_volume)
                parsed_dates_vol = [parse_mixed_date(str(c)) for c in df_volume.columns[2:]]
                df_volume.columns = list(df_volume.columns[:2]) + parsed_dates_vol
                df_volume_melted = df_volume.melt(id_vars=["symbol", "sector"], var_name="Date", value_name="Volume")
                stock_list_vol = df_volume["symbol"].unique()
                valid_dates_vol = df_volume_melted["Date"].dropna()
                if valid_dates_vol.empty:
                    st.error("Không có ngày hợp lệ trong file volume!")
                else:
                    min_v = valid_dates_vol.min()
                    max_v = valid_dates_vol.max()
                    col_vol1, col_vol2, col_vol3 = st.columns([1, 1, 2])
                    with col_vol1:
                        selected_stock_vol = st.selectbox("Chọn mã:", stock_list_vol)
                    with col_vol2:
                        start_vol = st.date_input("Bắt đầu từ:", min_v.date(), format="DD/MM/YYYY",
                                                  min_value=min_v.date(), max_value=max_v.date())
                    with col_vol3:
                        end_vol = st.date_input("Kết thúc vào:", max_v.date(), format="DD/MM/YYYY",
                                                min_value=min_v.date(), max_value=max_v.date())
                    start_vol_dt = pd.to_datetime(start_vol)
                    end_vol_dt = pd.to_datetime(end_vol)
                    df_selected_vol = df_volume_melted[
                        (df_volume_melted["symbol"] == selected_stock_vol) &
                        (df_volume_melted["Date"] >= start_vol_dt) &
                        (df_volume_melted["Date"] <= end_vol_dt)
                        ]
                    st.write(
                        f"Dữ liệu từ **{start_vol_dt.strftime('%d/%m/%Y')}** đến **{end_vol_dt.strftime('%d/%m/%Y')}**")
                    fig_volume = px.bar(df_selected_vol, x="Date", y="Volume",
                                        title=f"Khối lượng giao dịch của {selected_stock_vol}")
                    fig_volume.update_layout(yaxis_title="Khối lượng giao dịch", xaxis_title="Ngày")
                    st.plotly_chart(fig_volume, use_container_width=True)

    ##################################
    # Dashboard: Thống kê chi tiết về dòng tiền giao dịch
    ##################################
    elif dashboard_option == "Thống kê dòng tiền giao dịch":
        st.write("Thể hiện chi tiết thống kê về dòng tiền giao dịch trong thời gian được chọn.")

        excel_file = "Thong_ke_gia_Phan_loai_NDT__VNINDEX(Final).xlsx"
        df_ca_nhan_trong_nuoc = pd.read_excel(excel_file, sheet_name="Cá nhân trong nước (Ròng)")
        df_ca_nhan_nuoc_ngoai = pd.read_excel(excel_file, sheet_name="Cá nhân nước ngoài (Ròng)")
        df_to_chuc_trong_nuoc = pd.read_excel(excel_file, sheet_name="Tổ chức trong nước (Ròng)")
        df_to_chuc_nuoc_ngoai = pd.read_excel(excel_file, sheet_name="Tổ chức nước ngoài (Ròng)")

        # Giả sử mỗi sheet có cột:
        #   Ngày, GT ròng khớp lệnh (nghìn VND), GT ròng thỏa thuận (nghìn VND)

        # ============ 1) Chuẩn bị từng sheet: chỉ lấy 3 cột, rồi rename ============
        df_ca_nhan_trong_nuoc = df_ca_nhan_trong_nuoc[["Ngày",
                                                       "GT ròng khớp lệnh (nghìn VND)",
                                                       "GT ròng thỏa thuận (nghìn VND)"]]
        df_ca_nhan_trong_nuoc = df_ca_nhan_trong_nuoc.rename(columns={
            "GT ròng khớp lệnh (nghìn VND)": "Cá nhân trong nước - Khớp",
            "GT ròng thỏa thuận (nghìn VND)": "Cá nhân trong nước - Thỏa thuận"
        })

        df_ca_nhan_nuoc_ngoai = df_ca_nhan_nuoc_ngoai[["Ngày",
                                                       "GT ròng khớp lệnh (nghìn VND)",
                                                       "GT ròng thỏa thuận (nghìn VND)"]]
        df_ca_nhan_nuoc_ngoai = df_ca_nhan_nuoc_ngoai.rename(columns={
            "GT ròng khớp lệnh (nghìn VND)": "Cá nhân nước ngoài - Khớp",
            "GT ròng thỏa thuận (nghìn VND)": "Cá nhân nước ngoài - Thỏa thuận"
        })

        df_to_chuc_trong_nuoc = df_to_chuc_trong_nuoc[["Ngày",
                                                       "GT ròng khớp lệnh (nghìn VND)",
                                                       "GT ròng thỏa thuận (nghìn VND)"]]
        df_to_chuc_trong_nuoc = df_to_chuc_trong_nuoc.rename(columns={
            "GT ròng khớp lệnh (nghìn VND)": "Tổ chức trong nước - Khớp",
            "GT ròng thỏa thuận (nghìn VND)": "Tổ chức trong nước - Thỏa thuận"
        })

        df_to_chuc_nuoc_ngoai = df_to_chuc_nuoc_ngoai[["Ngày",
                                                       "GT ròng khớp lệnh (nghìn VND)",
                                                       "GT ròng thỏa thuận (nghìn VND)"]]
        df_to_chuc_nuoc_ngoai = df_to_chuc_nuoc_ngoai.rename(columns={
            "GT ròng khớp lệnh (nghìn VND)": "Tổ chức nước ngoài - Khớp",
            "GT ròng thỏa thuận (nghìn VND)": "Tổ chức nước ngoài - Thỏa thuận"
        })

        # ============ 2) Gộp 4 sheet thành 1 DF wide-format theo cột "Ngày" ============
        wide_df = pd.merge(df_ca_nhan_trong_nuoc, df_ca_nhan_nuoc_ngoai, on="Ngày", how="outer")
        wide_df = pd.merge(wide_df, df_to_chuc_trong_nuoc, on="Ngày", how="outer")
        wide_df = pd.merge(wide_df, df_to_chuc_nuoc_ngoai, on="Ngày", how="outer")

        # Chuyển cột "Ngày" thành datetime, sắp xếp
        wide_df["Ngày"] = pd.to_datetime(wide_df["Ngày"], errors="coerce")
        wide_df = wide_df.sort_values("Ngày")

        # ============ 3) Cho user chọn khoảng thời gian (nằm ở phần chính, không phải sidebar) ============
        min_date = wide_df["Ngày"].min()
        max_date = wide_df["Ngày"].max()

        col_date1, col_date2 = st.columns(2)
        with col_date1:
            start_date = st.date_input("Chọn ngày bắt đầu:", value=min_date,
                                       min_value=min_date, max_value=max_date)
        with col_date2:
            end_date = st.date_input("Chọn ngày kết thúc:", value=max_date,
                                     min_value=min_date, max_value=max_date)

        if start_date > end_date:
            st.error("Ngày bắt đầu phải <= ngày kết thúc!")
            return

        # Lọc wide_df theo khoảng thời gian
        mask = (wide_df["Ngày"] >= pd.to_datetime(start_date)) & (wide_df["Ngày"] <= pd.to_datetime(end_date))
        filtered_df = wide_df[mask].copy()
        if filtered_df.empty:
            st.warning("Không có dữ liệu trong khoảng thời gian này!")
            return

        # ============ 4) Chuyển sang long_df ============
        value_vars = [c for c in filtered_df.columns if c != "Ngày"]
        long_df = filtered_df.melt(
            id_vars="Ngày",
            value_vars=value_vars,
            var_name="variable",
            value_name="value"
        )

        # Tách "variable" => 2 cột: "Nhà đầu tư" và "Loại"
        def parse_variable(var):
            splitted = var.split(" - ")
            if len(splitted) == 2:
                investor, order_type = splitted
            else:
                investor, order_type = (var, "Unknown")
            return investor, order_type

        long_df[["Nhà đầu tư", "Loại"]] = long_df["variable"].apply(lambda x: pd.Series(parse_variable(x)))
        long_df.drop(columns="variable", inplace=True)

        # Convert value sang float, NaN => 0
        long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce").fillna(0)

        # ============ 5) Tách thành 2 DF: Khớp & Thỏa thuận, rồi vẽ 2 biểu đồ riêng ============

        df_khop = long_df[long_df["Loại"] == "Khớp"]
        df_thoathuan = long_df[long_df["Loại"] == "Thỏa thuận"]

        color_map = {
            "Cá nhân trong nước": "#0072B2",
            "Cá nhân nước ngoài": "#D55E00",
            "Tổ chức trong nước": "#009E73",
            "Tổ chức nước ngoài": "#CC79A7"
        }

        # Biểu đồ Thỏa thuận
        fig_thoathuan = px.bar(
            df_thoathuan,
            x="Ngày",
            y="value",
            color="Nhà đầu tư",
            barmode="relative",
            color_discrete_map=color_map,
            title="GT ròng Thỏa thuận (nghìn VND)"
        )
        fig_thoathuan.update_xaxes(tickangle=-45)
        fig_thoathuan.update_layout(
            legend_title_text="Nhà đầu tư",
            xaxis_title="Ngày",
            yaxis_title="GT ròng (nghìn VND)"
        )

        # Biểu đồ Khớp
        fig_khop = px.bar(
            df_khop,
            x="Ngày",
            y="value",
            color="Nhà đầu tư",
            barmode="relative",
            color_discrete_map=color_map,
            title="GT ròng Khớp lệnh (nghìn VND)"
        )
        fig_khop.update_xaxes(tickangle=-45)
        fig_khop.update_layout(
            legend_title_text="Nhà đầu tư",
            xaxis_title="Ngày",
            yaxis_title="GT ròng (nghìn VND)"
        )

        # Cập nhật layout biểu đồ với chiều rộng tăng lên (ví dụ: 1200 pixel)
        fig_thoathuan.update_layout(width=1200)
        fig_khop.update_layout(width=1200)

        # Hiển thị biểu đồ Thỏa thuận trên dòng đầu tiên
        st.plotly_chart(fig_thoathuan, use_container_width=True)

        # Hiển thị biểu đồ Khớp lệnh trên dòng tiếp theo
        st.plotly_chart(fig_khop, use_container_width=True)

        # ---------------------------
        # Đọc nguồn dữ liệu thứ 2
        # ---------------------------
        excel_file2 = "Thong_ke_gia_Phan_loai_NDT__VNINDEX.xlsx"
        # Nếu file có các dòng header phụ (như “Tổng”, “Trung bình”), bạn có thể cần bỏ qua bằng skiprows, ví dụ: skiprows=2
        df_source2 = pd.read_excel(excel_file2, skiprows=2)

        # Chuyển cột "Ngày" sang kiểu datetime và loại bỏ các dòng không hợp lệ
        df_source2["Ngày"] = pd.to_datetime(df_source2["Ngày"], errors="coerce")
        df_source2 = df_source2.dropna(subset=["Ngày"])
        df_source2 = df_source2.sort_values("Ngày")

        # -----------------------------------------------------------
        # 1. Biểu đồ đường (Line Chart): Xu hướng các chỉ số theo thời gian
        # -----------------------------------------------------------
        # Giả sử nguồn dữ liệu thứ 2 có các cột cho 4 nhóm đối tượng với các chỉ số sau:
        #   - "Tổng KL mua (CP)" và "Tổng GT mua (nghìn VND)"
        #   - "Tổng KL bán (CP)" và "Tổng GT bán (nghìn VND)"
        #
        # Ta sẽ xây dựng một mapping cho 4 nhóm đối tượng.
        col_map = {
            "Cá nhân trong nước": {
                "KL mua": "Tổng KL mua (CP)",
                "GT mua": "Tổng GT mua (nghìn VND)",
                "KL bán": "Tổng KL bán (CP)",
                "GT bán": "Tổng GT bán (nghìn VND)"
            },
            "Cá nhân nước ngoài": {
                # Bạn cần điều chỉnh tên cột cho phù hợp nếu có trùng lặp
                "KL mua": "Tổng KL mua (CP)_CN_NN",
                "GT mua": "Tổng GT mua (nghìn VND)_CN_NN",
                "KL bán": "Tổng KL bán (CP)_CN_NN",
                "GT bán": "Tổng GT bán (nghìn VND)_CN_NN"
            },
            "Tổ chức trong nước": {
                "KL mua": "Tổng KL mua (CP)_TC_TN",
                "GT mua": "Tổng GT mua (nghìn VND)_TC_TN",
                "KL bán": "Tổng KL bán (CP)_TC_TN",
                "GT bán": "Tổng GT bán (nghìn VND)_TC_TN"
            },
            "Tổ chức nước ngoài": {
                "KL mua": "Tổng KL mua (CP)_TC_NN",
                "GT mua": "Tổng GT mua (nghìn VND)_TC_NN",
                "KL bán": "Tổng KL bán (CP)_TC_NN",
                "GT bán": "Tổng GT bán (nghìn VND)_TC_NN"
            }
        }

        # Xây dựng DataFrame cho biểu đồ đường theo định dạng long
        df_line = pd.DataFrame()
        for group, metrics in col_map.items():
            temp = df_source2[["Ngày"]].copy()
            temp["Nhóm"] = group
            for metric_label, col_name in metrics.items():
                temp[metric_label] = df_source2[col_name]
            df_line = pd.concat([df_line, temp], ignore_index=True)

        # Chuyển sang dạng long: mỗi dòng chứa 1 chỉ số
        df_line_melted = df_line.melt(
            id_vars=["Ngày", "Nhóm"],
            value_vars=["KL mua", "KL bán", "GT mua", "GT bán"],
            var_name="Chỉ số",
            value_name="Giá trị"
        )

        # Vẽ biểu đồ đường: có thể dùng facet (chia cột theo Nhóm) hoặc dùng line_group
        fig_line = px.line(
            df_line_melted,
            x="Ngày",
            y="Giá trị",
            color="Chỉ số",
            line_group="Nhóm",  # hoặc dùng facet_col="Nhóm" nếu muốn chia cột riêng cho mỗi nhóm
            title="Xu hướng các chỉ số theo thời gian cho từng nhóm đối tượng"
        )
        fig_line.update_layout(width=1200)
        st.plotly_chart(fig_line, use_container_width=True)


if __name__ == '__main__':
    main()
