import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.font_manager as fm

# 设置思源宋体（确保中文正常显示）
font_path = '/data/home/zyx/.local/share/fonts/SourceHanSerif/SourceHanSerifCN-Regular.ttf'
zh_font = fm.FontProperties(fname=font_path)

# 全局字体配置
plt.rcParams['font.family'] = zh_font.get_name()
plt.rcParams['axes.unicode_minus'] = False

# Read the CSV files
v1_df = pd.read_csv('logs_v2/v1_S-score.csv')
v2_df = pd.read_csv('logs_v2/v2_S-score.csv')

# Extract step and S-score values using explicit column names
v1_steps = v1_df['step']
v1_score = v1_df['bs32-lr1e-04-ep50-val/s_score_step']

v2_steps = v2_df['step']
v2_score = v2_df['dacg_structured_20251208_210105-val/s_score_step']

# Create the plot with wide-short canvas
fig, ax = plt.subplots(figsize=(12, 6))

# Plot curves without markers - 图例改为中文
ax.plot(v1_steps, v1_score, linewidth=2.5, color='#1f77b4', label='模型v1 S-Score')
ax.plot(v2_steps, v2_score, linewidth=2.5, color='#ff7f0e', label='模型v2 S-Score')

# Labels and title - 标题改为中文
ax.set_xlabel('训练轮次', fontsize=14)
ax.set_ylabel('S-scores', fontsize=14)
ax.set_title('模型v1与v2验证集S-Score曲线', fontsize=16)

# Legend and grid - 图例位置保持右下角
ax.legend(fontsize=12, loc='lower right', framealpha=0.9)
ax.grid(True, linestyle='--', alpha=0.4)

# Dynamic axis limits with padding
all_score = pd.concat([v1_score, v2_score])
ymin, ymax = all_score.min(), all_score.max()
padding = (ymax - ymin) * 0.1 if ymax != ymin else 0.2
ax.set_ylim(ymin - padding, ymax + padding)
ax.set_xlim(v1_steps.min() - 1, v1_steps.max() + 1)

# Integer ticks
ax.set_xticks(np.arange(0, v1_steps.max() + 1, 5))
ax.tick_params(axis='both', labelsize=11)

# Tight layout and save
plt.tight_layout()
plt.savefig('logs_v2/v2_sscore_curve.png', dpi=300, bbox_inches='tight')
print('S-score curve saved to logs_v2/v2_sscore_curve.png')