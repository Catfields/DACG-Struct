import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.font_manager as fm

# 直接指定思源宋体的字体文件路径
font_path = '/data/home/zyx/.local/share/fonts/SourceHanSerif/SourceHanSerifCN-Regular.ttf'
zh_font = fm.FontProperties(fname=font_path)

# 使用字体文件路径设置全局字体（注意：这里设置的是 font.family，不是 font.serif）
plt.rcParams['font.family'] = 'sans-serif'  # 设置为 sans-serif 族
plt.rcParams['font.sans-serif'] = [zh_font.get_name()]  # 将思源宋体设为 sans-serif 的首选
plt.rcParams['axes.unicode_minus'] = False

# 可选：设置默认字体大小
plt.rcParams['font.size'] = 15

# Read the CSV files
train_df = pd.read_csv('logs_v1/v1_train_loss.csv')
val_df = pd.read_csv('logs_v1/v1_val_loss.csv')

# Extract epoch and loss values using explicit column names
train_steps = train_df['epoch']
train_loss = train_df['train_loss']

val_steps = val_df['epoch']
val_loss = val_df['val_loss']

# Create the plot with wide-short canvas
fig, ax = plt.subplots(figsize=(12, 6))

# Plot curves without markers
ax.plot(train_steps, train_loss, linewidth=2.5, color='#1f77b4', label='训练损失')
ax.plot(val_steps, val_loss, linewidth=2.5, color='#ff7f0e', label='验证损失')

# Labels and title (使用 fontproperties 参数确保中文显示)
ax.set_xlabel('Epoch', fontsize=14)  # 英文标签不需要中文字体
ax.set_ylabel('Loss', fontsize=14)
ax.set_title('Model v1 Training and Validation Loss', fontsize=16, fontweight='bold')

# 如果你想添加中文标题或标签，需要使用 fontproperties 参数
ax.set_title('模型v1训练与验证损失', fontproperties=zh_font, fontsize=16, fontweight='bold')
ax.set_xlabel('训练轮次', fontproperties=zh_font, fontsize=14)
ax.set_ylabel('损失值', fontproperties=zh_font, fontsize=14)

# Legend and grid (图例也需要指定中文字体)
ax.legend(fontsize=12, loc='upper right', framealpha=0.9, prop=zh_font)
ax.grid(True, linestyle='--', alpha=0.4)

# Dynamic axis limits with padding
all_loss = pd.concat([train_loss, val_loss])
ymin, ymax = all_loss.min(), all_loss.max()
padding = (ymax - ymin) * 0.1 if ymax != ymin else 0.2
ax.set_ylim(ymin - padding, ymax + padding)
ax.set_xlim(train_steps.min() - 1, train_steps.max() + 1)

# Integer ticks
ax.set_xticks(np.arange(0, train_steps.max() + 1, 5))
ax.tick_params(axis='both', labelsize=11)

# Tight layout and save
plt.tight_layout()
plt.savefig('logs_v1/v1_loss_curve.png', dpi=300, bbox_inches='tight')
print('Loss curve saved to logs_v1/v1_loss_curve.png')

# 验证当前使用的字体
print(f"当前使用的中文字体: {zh_font.get_name()}")
print(f"字体文件路径: {zh_font.get_file()}")