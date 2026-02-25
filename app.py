import streamlit as st

st.set_page_config(
    page_title="Gold Reserves Vista",
    page_icon="🥇",
    layout="wide",
)

pg = st.navigation([
    st.Page(
        "pages/1_WGC_Historical_Data.py",
        title="WGC Historical Data",
        icon="📊",
        default=True,
    ),
    st.Page(
        "pages/2_HF_Central_Bank_Monitor.py",
        title="HF Central Bank Monitor",
        icon="🏦",
    ),
])

pg.run()
