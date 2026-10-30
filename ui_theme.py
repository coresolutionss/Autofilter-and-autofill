"""Presentation only: AMB navy, champagne and ivory. No remote assets."""
import streamlit as st


def apply_theme():
    st.html('''<style>
    :root {--st-primary-color:#14243B;--st-link-color:#29476B;}
    .stApp {background:#F7F8FA;color:#14243B;font-family:"Segoe UI",Arial,sans-serif;}
    [data-testid="stMainBlockContainer"] {max-width:1660px;padding:4.5rem 2.5rem 4rem;}
    [data-testid="stHeader"] {background:#F7F8FAee;}
    [data-testid="stToolbar"] [data-testid="stAppDeployButton"] {display:none;}
    h1,h2,h3 {color:#14243B;letter-spacing:-.025em;}
    h3 {font-size:1.35rem!important;font-weight:650!important;}
    p {line-height:1.6;}
    [data-testid="stCaptionContainer"] {color:#64748B;}
    [data-testid="stSidebar"] {background:#14243B;border-right:1px solid #24364F;}
    [data-testid="stSidebarUserContent"] {padding:1.5rem 1.15rem;}
    [data-testid="stSidebar"] label p,
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] p {color:#CBD5E1!important;}
    [data-testid="stSidebar"] [data-testid="stMetric"] {
        background:#203149;border:1px solid #34445D;border-radius:14px;padding:16px 18px;margin:12px 0;}
    [data-testid="stSidebar"] [data-testid="stMetricValue"] {color:#F5E5C2;font-size:1.9rem;}
    [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
        color:#F8FAFC;background:transparent;border:1px solid #718098;}
    [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
        background:#243951;border-color:#B89446;color:#F5E5C2;}
    .amb-brand {padding:0 0 28px;border-bottom:1px solid #ffffff24;margin-bottom:24px;}
    .amb-brand-name {color:#D8B76A;font:bold 42px Georgia,serif;letter-spacing:-3px;line-height:1;}
    .amb-brand-sub {color:#E3E8EF;font-size:10px;letter-spacing:2.8px;text-transform:uppercase;margin-top:9px;}
    .amb-header {display:flex;align-items:center;justify-content:space-between;gap:20px;
        border-bottom:1px solid #E3E8EF;padding:0 0 24px;margin-bottom:12px;}
    .amb-eyebrow {font-size:10px;font-weight:700;letter-spacing:2.2px;color:#8A692D;text-transform:uppercase;}
    .amb-header h1 {font-size:29px;line-height:1.2;font-weight:650;margin:7px 0 9px;padding:0;}
    .amb-header p {font-size:14px;color:#64748B;margin:0;}
    .amb-header-mark {font:bold 31px Georgia,serif;color:#B89446;letter-spacing:-2px;}
    [role="tablist"] {gap:8px;background:#EDEFF3;border-radius:13px;padding:6px;
        margin:8px 0 18px;min-height:54px;border-bottom:0!important;}
    [role="tab"] {border-radius:9px!important;padding:10px 18px!important;
        color:#526175!important;min-height:40px;white-space:nowrap;border-bottom:0!important;}
    [role="tab"] p {font-size:13px;font-weight:600;}
    [role="tab"][aria-selected="true"] {background:#14243B!important;color:white!important;box-shadow:0 2px 5px #14243B18;}
    [data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {display:none;}
    [data-testid="stBaseButton-primary"] {
        background:#14243B!important;border:1px solid #14243B!important;color:white!important;}
    [data-testid="stBaseButton-primary"]:hover {background:#243F60!important;border-color:#243F60!important;}
    [data-testid="stBaseButton-secondary"] {background:#fff;color:#14243B;border:1px solid #D7DEE7;}
    [data-testid="stBaseButton-secondary"]:hover {border-color:#B89446;color:#14243B;background:#FCFAF5;}
    button[kind="primary"],button[kind="secondary"] {border-radius:10px;min-height:42px;font-weight:600;}
    button:disabled {opacity:.45;}
    [data-baseweb="select"] > div, [data-baseweb="input"],
    [data-testid="stTextArea"] textarea {background:#F8FAFC;border-color:#DEE4ED;border-radius:9px;}
    [data-baseweb="select"]:focus-within > div, [data-baseweb="input"]:focus-within {
        border-color:#B89446;box-shadow:0 0 0 2px #B894461c;}
    input,textarea {accent-color:#14243B;}
    .st-key-document-intake-panel {background:white;border:1px solid #E1E6ED;border-radius:18px;
        padding:24px;box-shadow:0 3px 12px #14243B04;}
    [data-testid="stFileUploaderDropzone"] {background:#F8FAFC;border:1.5px dashed #C6D0DD;
        border-radius:13px;padding:20px;}
    [data-testid="stExpander"] {background:white;border:1px solid #E1E6ED;border-radius:12px;overflow:hidden;}
    [data-testid="stExpander"] summary {padding:14px 16px;}
    [data-testid="stAlert"] {border-radius:11px;border:1px solid #DFE7EF;background:#EEF3F8;color:#29405D;}
    .st-key-review-comparison {background:white;border:1px solid #E1E6ED;border-top:3px solid #B89446;
        border-radius:14px;padding:20px;box-shadow:0 3px 12px #14243B05;}
    .st-key-review-comparison [data-testid="stMarkdownContainer"] strong {font-size:15px;}
    .st-key-review-comparison [data-testid="stImage"] {border-radius:9px;overflow:hidden;}
    @media(max-width:850px) {
        [data-testid="stMainBlockContainer"] {padding:4rem 1rem 3rem;}
        .amb-header h1 {font-size:24px;}.amb-header-mark {display:none;}
        .st-key-document-intake-panel {padding:16px;}
        [role="tablist"] {gap:2px;overflow-x:auto;}
        [role="tab"] {padding:8px 10px!important;}
    }
    </style>''')


def render_brand():
    st.sidebar.html('''<div class="amb-brand"><div class="amb-brand-name">AMB</div>
        <div class="amb-brand-sub">Gold &amp; Diamond</div></div>''')
    st.html('''<header class="amb-header"><div><div class="amb-eyebrow">Application workspace</div>
        <h1>Document intake</h1><p>Add documents, review your details, and prepare your application.</p>
        </div><div class="amb-header-mark" aria-hidden="true">AMB</div></header>''')
