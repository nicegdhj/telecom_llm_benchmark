#!/usr/bin/env python3
"""
自动化分析脚本：遍历 benchmark/outputs 目录下所有模型实验结果，
适配新结构（根目录 -> Task -> Config -> summary），
新增智能体（Agent）类任务文件截断逻辑（仅读取第一行），
动态处理全军覆没场景：若仅有Baseline未劣化，自动捞取前两名劣化的模型加入雷达图，
新增实验组别名映射，
升级：Y轴通用能力采用业界推荐的“分层宏观平均(Hierarchical Macro-averaging)”算法。
"""
import textwrap
import argparse
import base64
import os
import sys
import glob
import contextlib
from io import BytesIO

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import logging
import datetime

def setup_logger(log_file_path="analysis_process.log"):
    logger = logging.getLogger("DashAnalysis")
    if not logger.handlers:
        logger.setLevel(logging.DEBUG) 
        fh = logging.FileHandler(log_file_path, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger

logger = setup_logger()

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'Microsoft YaHei', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

EXP_MAPPING = {}

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from compare_scores import (
        load_model_scores,
        compute_category_score,
        check_general_degradation,
        format_score,
        calculate_tele_exam_cmb_scores,
        get_all_config_model_scores,
        identify_models_in_dir
    )
except ImportError as e:
    print(f"[ERROR] 无法导入 compare_scores 模块: {e}", file=sys.stderr)
    sys.exit(1)
    
from compare_scores import CATEGORIES3 as CATEGORIES

def get_latest_report(base_path):
    all_subdirs = [
        os.path.join(base_path, d) 
        for d in os.listdir(base_path) 
        if os.path.isdir(os.path.join(base_path, d)) and d.startswith('agg')
    ]
    if not all_subdirs: return None
    latest_subdir = max(all_subdirs, key=os.path.getmtime)
    return latest_subdir

@contextlib.contextmanager
def patch_read_csv_nrows(nrows=1):
    original_read_csv = pd.read_csv
    def patched_read_csv(*args, **kwargs):
        kwargs['nrows'] = nrows
        return original_read_csv(*args, **kwargs)
    pd.read_csv = patched_read_csv
    try:
        yield
    finally:
        pd.read_csv = original_read_csv

def get_all_subcategories():
    subcats = []
    for cat in CATEGORIES:
        for subcat in cat.get("subcategories", []):
            subcats.append((subcat["name"], subcat["keywords"]))
    return subcats

def generate_dataset_winner_table(aggregated_scores, df_valid_configs) -> str:
    valid_configs = set(df_valid_configs['config_name'].values)
    columns_info = []
    
    for (c_name, m_name), scores in aggregated_scores.items():
        display_name = EXP_MAPPING.get(c_name, c_name)
        if display_name in valid_configs:
            columns_info.append((c_name, m_name, display_name))
            
    columns_info = sorted(columns_info, key=lambda x: x[2])
    
    all_keywords = []
    for cat in CATEGORIES:
        for kw in cat["keywords"]:
            if kw not in all_keywords:
                all_keywords.append(kw)
    
    html = ["<div class=\"summary-box\" style=\"overflow-x: auto;\">", 
            "<h2>🏆 各数据集表现对比 (热力图)</h2>", 
            "<table style=\"white-space: nowrap; font-size: 13px;\">"]
            
    header = ["<tr>", "<th>数据集 (Keyword)</th>"]
    for _, _, display_name in columns_info:
        header.append(f"<th>{display_name}</th>")
    header.append("</tr>")
    html.append("".join(header))
    
    for kw in all_keywords:
        row_scores = []
        for (c_name, m_name, _) in columns_info:
            scores = aggregated_scores.get((c_name, m_name), {})
            val = compute_category_score(kw, scores, [kw], silent=True)
            row_scores.append(val)
            
        valid_scores = [v for v in row_scores if v is not None]
        if not valid_scores:
            continue
            
        max_score = max(valid_scores)
        min_score = min(valid_scores)
        
        row_html = [f"<tr><td style=\"text-align: left; font-weight: bold;\">{kw}</td>"]
        
        for val in row_scores:
            if val is None:
                row_html.append("<td style=\"background-color: #f9f9f9; color: #ccc;\">-</td>")
            else:
                if max_score > min_score:
                    ratio = (val - min_score) / (max_score - min_score)
                    alpha = ratio * 0.6 + 0.1
                else:
                    alpha = 0.3
                bg_color = f"rgba(40, 167, 69, {alpha:.2f})"
                cell_text = format_score(val)
                if val == max_score:
                    cell_text = f"<strong>{cell_text}</strong> <span title='最高分'>🥇</span>"
                    bg_color = f"rgba(40, 167, 69, 0.85)"
                row_html.append(f"<td style=\"background-color: {bg_color};\">{cell_text}</td>")
        row_html.append("</tr>")
        html.append("".join(row_html))
        
    html.append("</table></div>")
    return "\n".join(html)

def parse_args():
    parser = argparse.ArgumentParser(description="自动化分析评估结果并生成报告")
    parser.add_argument("--outputs_dir", default="aggregated_reports_20260310_163540", help="评估输出根目录")
    parser.add_argument("--config", required=True, help="待评估配置文件夹名称（支持逗号分隔如 'set10,set11'，或填 'all' 自动遍历所有配置）")
    parser.add_argument("--baseline_folder", default="baseline", help="基线配置的文件夹名称（用于劣化检测）")
    parser.add_argument("--degradation_threshold", type=float, default=5.0, help="劣化阈值(%)")
    parser.add_argument("--report_out", default="analysis_report.html", help="生成的HTML报告路径")
    return parser.parse_args()

def plot_pareto_front(df_valid, baseline_folder, x_col, y_col, x_label, y_label, title) -> str:
    plt.figure(figsize=(10, 8))
    xs = np.array([float(v) if v is not None else 0.0 for v in df_valid[x_col]])
    ys = np.array([float(v) if v is not None else 0.0 for v in df_valid[y_col]])
    if len(xs) == 0 or len(ys) == 0:
        plt.close()
        return ""
    is_pareto = df_valid['is_pareto'].values
    labels = df_valid['config_name'].values
    raw_folders = df_valid.get('raw_folder', df_valid['config_name']).values
    is_baseline = (raw_folders == baseline_folder) | (labels == baseline_folder)
    
    idx_other = (~is_pareto) & (~is_baseline)
    if idx_other.any():
        plt.scatter(xs[idx_other], ys[idx_other], color='blue', alpha=0.5, label='其他配置 (被完全支配)')
    idx_base = (~is_pareto) & is_baseline
    if idx_base.any():
        plt.scatter(xs[idx_base], ys[idx_base], color='grey', marker='s', s=100, label='Baseline', zorder=4)
    idx_pareto_other = is_pareto & (~is_baseline)
    if idx_pareto_other.any():
        plt.scatter(xs[idx_pareto_other], ys[idx_pareto_other], color='red', s=100, label='2D 帕累托最优解', zorder=5)
    idx_pareto_base = is_pareto & is_baseline
    if idx_pareto_base.any():
        plt.scatter(xs[idx_pareto_base], ys[idx_pareto_base], color='red', edgecolors='grey', linewidth=3, s=150, label='Baseline (Pareto)', zorder=6)
    
    for i in range(len(df_valid)):
        if is_pareto[i]:
            plt.annotate(
                labels[i], (xs[i], ys[i]), xytext=(8, 8), textcoords='offset points',
                fontsize=10, color='darkred', weight='bold'
            )
            
    plt.xlabel(x_label, fontsize=12)
    plt.ylabel(y_label, fontsize=12)
    plt.title(title, fontsize=14)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend()
    plt.tight_layout()
    
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    plt.close()
    return base64.b64encode(buf.getvalue()).decode('utf-8')

def plot_radar_chart(df_top5, baseline_folder, out_path=None) -> str:
    subcats = get_all_subcategories()
    categories_labels = [sc[0] for sc in subcats]
    N = len(categories_labels)
    if N == 0: return ""
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=(14, 10), subplot_kw=dict(polar=True))
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories_labels, fontsize=14, fontweight='bold')
    plt.tick_params(pad=30)
    ax.set_rlabel_position(0)
    plt.yticks([20, 40, 60, 80, 100], ["20", "40", "60", "80", "100"], color="grey", size=8)
    plt.ylim(0, 100)
    colors = plt.cm.tab10(np.arange(len(df_top5)))
    for idx, row in df_top5.iterrows():
        values = row['subcat_scores']
        values = [v if v is not None else 0 for v in values]
        values += values[:1] 
        label_name = row['config_name']
        if row.get('is_degraded', False):
            label_name += " (劣化捞回)"
        wrapped_label = textwrap.fill(label_name, width=30)
        is_baseline = (str(row.get('raw_folder', '')) == baseline_folder or str(row.get('config_name', '')) == baseline_folder)
        if is_baseline:
            plot_color = 'gray'
            ls = '--'
            lw = 2.5
        else:
            plot_color = colors[idx]
            ls = 'solid'
            lw = 2
        ax.plot(angles, values, linewidth=lw, linestyle=ls, label=wrapped_label, color=plot_color)
        ax.fill(angles, values, color=plot_color, alpha=0.1)
    plt.legend(loc='center left', bbox_to_anchor=(1.15, 0.5), fontsize=10)
    plt.title("不同策略的全能力雷达图剖析", fontsize=15, y=1.18)
    plt.tight_layout(rect=[0, 0, 0.75, 1])
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close()
    return base64.b64encode(buf.getvalue()).decode('utf-8')

def build_html_block(df, top5_models, img_scatters, img_radar, num_pareto, title):
    if df.empty: return ""
    top5_list_items = []
    for _, row in top5_models.iterrows():
        status_tag = '<span class="warning-text">(⚠️ 已劣化)</span>' if row.get('is_degraded', False) else '(✅ 无劣化)'
        top5_list_items.append(f"<li><strong>{row['config_name']}</strong> {status_tag} - 综合得分: {row['total_score']:.2f} </li>")
    
    top5_html = "".join(top5_list_items)
    max_c_dom = df['c_dom_total'].max()
    max_c_pro = df['c_pro'].max()
    max_x = df['x_score'].max()
    max_y = df['y_score'].max()

    def render_cell(val, max_val, is_bold=False):
        base_text = format_score(val)
        is_max = False
        if val is not None and not pd.isna(val) and max_val is not None and not pd.isna(max_val):
            if val == max_val: is_max = True
        if is_max: base_text += " <span title='该维度全场最高分'>🥇</span>"
        if is_bold: return f"<strong>{base_text}</strong>"
        return base_text

    block_html = f"""
            <h1 style="color: #c9302c; border-bottom: 2px solid #c9302c; padding-bottom: 10px; margin-top: 50px;">{title}</h1>
            <div class="summary-box">
                <h2>🏆 雷达图对比配置池</h2>
                <ul>
                    {top5_html}
                </ul>
            </div>
            
            <h2>📍 2D 帕累托前沿多维分析</h2>
            <p style="color: #666; font-size: 14px; line-height: 1.6;">
                采用二维支配算法：仅当模型在【垂类知识（通信）、生产场景】两大维度上全面落后时才被判定为淘汰，保留各个领域的最优模型。<br>
                <strong>🎯 本次评测共识别出 <span style="color: darkred; font-size: 16px;">{num_pareto}</span> 个 2D 帕累托最优配置。</strong>
            </p>
            
            <div style="display: flex; justify-content: center; flex-wrap: wrap;">
                <div class="img-container" style="width: 60%; min-width: 500px;">
                    <img src="data:image/png;base64,{img_scatters.get('dom_vs_pro', '')}" alt="垂类知识（通信）vs生产场景"/>
                </div>
            </div>

            <h2>🕸️ 全能力多维评估 (雷达图)</h2>
            <div class="img-container">
                <img src="data:image/png;base64,{img_radar}" alt="Radar Chart"/>
            </div>
            
            <h2>📋 详细数据表</h2>
            <table>
                <tr>
                    <th>实验配置名称 (别名)</th>
                    <th>垂类知识（通信）</th>
                    <th>生产场景</th>
                    <th>X轴 (业务均分)</th>
                    <th>Y轴 (通用均分)</th>
                    <th>综合总分</th>
                    <th>2D 帕累托最优</th>
                    <th>是否劣化</th>
                </tr>
    """
    
    for _, row in df.iterrows():
        pareto_class = "pareto" if row.get('is_pareto', False) else ""
        deg_class = "degraded" if row.get('is_degraded', False) else ""
        
        display_html = f"{row['config_name']}"
        if row['raw_folder'] != row['config_name']:
             display_html += f"<span class='folder-hint'>[{row['raw_folder']}]</span>"

        row_html = f"""
                <tr class="{pareto_class} {deg_class}">
                    <td style="text-align: left;">{display_html}</td>
                    <td>{render_cell(row.get('c_dom_total'), max_c_dom)}</td>
                    <td>{render_cell(row.get('c_pro'), max_c_pro)}</td>
                    <td>{render_cell(row.get('x_score'), max_x, is_bold=True)}</td>
                    <td>{render_cell(row.get('y_score'), max_y, is_bold=True)}</td>
                    <td><strong style="color:#0056b3;">{format_score(row['total_score'])}</strong></td>
                    <td>{'✅' if row.get('is_pareto', False) else '-'}</td>
                    <td>{'⚠️是' if row.get('is_degraded', False) else '-'}</td>
                </tr>
        """
        block_html += row_html
    block_html += "</table>"
    return block_html

def generate_html_report(df_total, top5_total, scatters_total, radar_total, num_pareto_total, 
                         df_think, top5_think, scatters_think, radar_think, num_pareto_think, 
                         df_nothink, top5_nothink, scatters_nothink, radar_nothink, num_pareto_nothink, 
                         winner_table_html, out_path: str):
    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>Benchmark 自动化分析报告</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 40px; color: #333; }}
            h1, h2, h3 {{ color: #0056b3; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; font-size: 14px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: center; }}
            th {{ background-color: #f4f4f4; font-weight: bold; }}
            tr:nth-child(even) {{ background-color: #fdfdfd; }}
            tr:hover {{ background-color: #f1f1f1; }}
            .pareto {{ background-color: #ffeaea !important; font-weight: bold; color: darkred; }}
            .degraded {{ color: #999; text-decoration: line-through; }}
            .container {{ max-width: 1200px; margin: auto; }}
            .img-container {{ text-align: center; margin: 15px 0; }}
            img {{ max-width: 100%; height: auto; box-shadow: 0 4px 8px rgba(0,0,0,0.1); border-radius: 8px; }}
            .summary-box {{ background-color: #e9f5ff; padding: 20px; border-left: 5px solid #0056b3; margin-bottom: 30px; }}
            .warning-text {{ color: #d9534f; font-weight: bold; }}
            .folder-hint {{ font-size: 12px; color: #777; display: block; margin-top: 4px; font-weight: normal; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 大模型后训练：不同实验评估报告</h1>
    """
    
    html_template += build_html_block(df_total, top5_total, scatters_total, radar_total, num_pareto_total, "Part 1: 全量模型对比 (Total View)")
    if not df_think.empty:
        html_template += build_html_block(df_think, top5_think, scatters_think, radar_think, num_pareto_think, "Part 2: Think 模型内部对比")
    if not df_nothink.empty:
        html_template += build_html_block(df_nothink, top5_nothink, scatters_nothink, radar_nothink, num_pareto_nothink, "Part 3: No-think 模型内部对比")
    html_template += f"""
            <div style="margin-top: 50px;">
                {winner_table_html}
            </div>
        </div>
    </body>
    </html>
    """
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    if 'logger' in globals():
        logger.info(f"报告已生成并保存至: {out_path}")
    else:
        print(f"[INFO] 报告已生成并保存至: {out_path}")

def process_group(df_subset, baseline_folder, group_name=""):
    logger.info(f"========== 【阶段 4：帕累托前沿算法与雷达图序列筛选 - {group_name}】 ==========")
    df_valid = df_subset[(df_subset['valid'] == True) & (df_subset['is_degraded'] == False)].copy()
    df_radar_pool = df_valid.copy()
    
    if len(df_valid) == 1:
        df_degraded = df_subset[(df_subset['valid'] == True) & (df_subset['is_degraded'] == True)].copy()
        if not df_degraded.empty:
            df_added = df_degraded.sort_values(by="total_score", ascending=False).head(2)
            df_radar_pool = pd.concat([df_radar_pool, df_added])
    elif df_valid.empty:
        df_valid = df_subset[df_subset['valid'] == True].copy()
        df_radar_pool = df_valid.copy()
        
    df_top5 = df_radar_pool.sort_values(by="total_score", ascending=False).head(5)
    baseline_df = df_subset[df_subset['raw_folder'] == baseline_folder] if 'raw_folder' in df_subset.columns else df_subset[df_subset['config_name'] == baseline_folder] 
    if not baseline_df.empty:
        key_to_check = 'raw_folder' if 'raw_folder' in df_top5.columns else 'config_name'
        if baseline_folder not in df_top5[key_to_check].values:
            df_top5 = pd.concat([df_top5, baseline_df])
    df_top5 = df_top5.reset_index(drop=True)

    v_dom = np.array([float(v) if v is not None else 0.0 for v in df_valid['c_dom_total']])
    v_pro = np.array([float(v) if v is not None else 0.0 for v in df_valid['c_pro']])
    is_pareto = []
    for i in range(len(df_valid)):
        dominated = False
        for j in range(len(df_valid)):
            if i == j: continue
            better_or_eq = (v_dom[j] >= v_dom[i]) and (v_pro[j] >= v_pro[i])
            strict_better = (v_dom[j] > v_dom[i]) or (v_pro[j] > v_pro[i])
            if better_or_eq and strict_better:
                dominated = True; break
        is_pareto.append(not dominated)
        
    df_valid['is_pareto'] = is_pareto
    df_subset_out = df_subset.copy()
    if not df_valid.empty:
        df_subset_out['is_pareto'] = df_subset_out['config_name'].isin(df_valid[df_valid['is_pareto']]['config_name'])
    else:
        df_subset_out['is_pareto'] = False
        
    num_pareto = sum(is_pareto)
    
    logger.info(f"========== 【阶段 5：图表渲染 - {group_name}】 ==========")
    img_scatters = {}
    img_scatters['dom_vs_pro'] = plot_pareto_front(df_valid, baseline_folder, 'c_dom_total', 'c_pro', "垂类知识（通信）", "生产场景得分", "垂类知识（通信） vs 生产场景")
    
    img_radar = plot_radar_chart(df_top5, baseline_folder)
    return df_subset_out, df_top5, img_scatters, img_radar, num_pareto


def main():
    args = parse_args()
    logger.info("========== 【阶段 1：环境与参数初始化】 ==========")
    if not os.path.exists(args.outputs_dir):
        print(f"[ERROR] 找不到输出根目录: {args.outputs_dir}")
        sys.exit(1)
    path_val = get_latest_report(args.outputs_dir)    
    logger.info("========== 【阶段 2：底层数据穿透扫描与聚合】 ==========")
    aggregated_scores = get_all_config_model_scores(path_val)
    if args.config.lower() != "all":
        filtered_scores = {}
        for (c_name, m_name), scores in aggregated_scores.items():
            if c_name == args.baseline_folder or args.config in c_name:
                filtered_scores[(c_name, m_name)] = scores
        aggregated_scores = filtered_scores
    if not aggregated_scores:
        print("[ERROR] 未找到任何有效的模型评分数据！请检查目录结构。")
        sys.exit(1)

    baseline_scores = {}
    for (c_name, m_name), scores in aggregated_scores.items():
        if c_name == args.baseline_folder:
            baseline_scores = scores
            break

    records = []
    subcats_list = get_all_subcategories()
    logger.info("========== 【阶段 3：模型总分与能力维度的校验计算】 ==========")
    for (config_name, model_name), scores in aggregated_scores.items():
        display_name = EXP_MAPPING.get(config_name, config_name)
        is_degraded = False
        if baseline_scores and config_name != args.baseline_folder:
            deg_res = check_general_degradation(scores, baseline_scores, args.degradation_threshold)
            if deg_res.get("degraded", 0) > 0:
                is_degraded = True
                
        sub_scores = []
        subcat_cache = {}
        for sc_name, sc_kws in subcats_list:
            s = compute_category_score(sc_name, scores, sc_kws)
            sub_scores.append(s)
            subcat_cache[sc_name] = s
            
        c_dom_total = compute_category_score(CATEGORIES[1]["name"], scores, CATEGORIES[1]["keywords"])
        c_pro = compute_category_score(CATEGORIES[2]["name"], scores, CATEGORIES[2]["keywords"])
        x_vals = [v for v in (c_dom_total, c_pro) if v is not None]
        x_score = sum(x_vals) / len(x_vals) if x_vals else 0.0
            
        general_subcats = CATEGORIES[0].get("subcategories", [])
        general_sub_scores = []
        for subcat in general_subcats:
            sub_s = subcat_cache.get(subcat["name"])
            if sub_s is not None:
                general_sub_scores.append(sub_s)
        y_score = sum(general_sub_scores) / len(general_sub_scores) if general_sub_scores else 0.0

        records.append({
            "raw_folder": config_name,
            "config_name": display_name,
            "c_dom_total": c_dom_total,       
            "c_pro": c_pro,      
            "x_score": x_score,
            "y_score": y_score,
            "total_score": x_score + y_score,
            "is_degraded": is_degraded,
            "subcat_scores": sub_scores,
            "valid": (x_score > 0 or y_score > 0)
        })

    df = pd.DataFrame(records)
    
    df_valid_all = df[(df['valid'] == True) & (df['is_degraded'] == False)].copy()
    winner_table_html = generate_dataset_winner_table(aggregated_scores, df_valid_all)

    df_total, df_top5_total, scatters_total, radar_total, num_pareto_total = process_group(df, args.baseline_folder, "全量模型")
    
    df_think = df[df['config_name'].str.contains('think', case=False, regex=True) & ~df['config_name'].str.contains('nothink', case=False, regex=True)].copy()
    if not df_think.empty:
        df_think_out, df_top5_think, scatters_think, radar_think, num_pareto_think = process_group(df_think, args.baseline_folder, "Think 模型内部对比")
    else:
        df_think_out, df_top5_think, scatters_think, radar_think, num_pareto_think = (df_think, df_think, {}, "", 0)

    df_nothink = df[df['config_name'].str.contains('nothink', case=False, regex=True)].copy()
    if not df_nothink.empty:
        df_nothink_out, df_top5_nothink, scatters_nothink, radar_nothink, num_pareto_nothink = process_group(df_nothink, args.baseline_folder, "No-think 模型内部对比")
    else:
        df_nothink_out, df_top5_nothink, scatters_nothink, radar_nothink, num_pareto_nothink = (df_nothink, df_nothink, {}, "", 0)

    generate_html_report(
        df_total.sort_values(by=["is_pareto", "total_score"], ascending=[False, False]), df_top5_total, scatters_total, radar_total, num_pareto_total,
        df_think_out.sort_values(by=["is_pareto", "total_score"], ascending=[False, False]) if not df_think_out.empty else df_think_out, df_top5_think, scatters_think, radar_think, num_pareto_think,
        df_nothink_out.sort_values(by=["is_pareto", "total_score"], ascending=[False, False]) if not df_nothink_out.empty else df_nothink_out, df_top5_nothink, scatters_nothink, radar_nothink, num_pareto_nothink,
        winner_table_html, args.report_out
    )

if __name__ == "__main__":
    sys.argv = [
        "dash_3d.py",
        "--outputs_dir", "0410",
        "--config", "all", 
        "--baseline_folder", "qwen3_32b_nothink",
        "--degradation_threshold", "100",
        "--report_out", "0410/analysis_report_3d.html"
    ]
    main()