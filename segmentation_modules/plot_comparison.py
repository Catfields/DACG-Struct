"""
Plot comparison curves for three models
"""

import json
import os
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.font_manager as fm

# 设置思源宋体确保中文正常显示
font_path = '/data/home/zyx/.local/share/fonts/SourceHanSerif/SourceHanSerifCN-Regular.ttf'
zh_font = fm.FontProperties(fname=font_path)

# Set font for Chinese
plt.rcParams['font.family'] = zh_font.get_name()
plt.rcParams['axes.unicode_minus'] = False

# Define model configurations
MODELS = [
    {
        'name': 'U-Net',
        'json_path': 'results/unet_results/training_info.json',
        'color': '#1f77b4',  # blue
        'train_loss_key': 'train_losses',
        'val_loss_key': 'val_losses',
        'train_dice_key': 'train_dices',
        'val_dice_key': 'val_dices'
    },
    {
        'name': 'Attention U-Net',
        'json_path': 'results/attention_unet_results/training_info.json',
        'color': '#d62728',  # red
        'train_loss_key': 'train_losses',
        'val_loss_key': 'val_losses',
        'train_dice_key': 'train_dices',
        'val_dice_key': 'val_dices'
    },
    {
        'name': 'U-Net++',
        'json_path': 'results/upp_results/training_info.json',
        'color': '#2ca02c',  # green
        'train_loss_key': 'train_losses',
        'val_loss_key': 'val_losses',
        'train_dice_key': 'train_dices',
        'val_dice_key': 'val_dices'
    }
]

def load_training_data(json_path):
    """Load training data"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def plot_loss_comparison(models_data, save_path):
    """Plot loss comparison"""
    fig, ax = plt.subplots(figsize=(12, 6))
    
    for model in MODELS:
        data = models_data[model['name']]
        train_losses = data[model['train_loss_key']]
        val_losses = data[model['val_loss_key']]
        epochs = range(1, len(train_losses) + 1)
        
        # Plot training loss - 图例改为中文
        ax.plot(epochs, train_losses, 
                color=model['color'], 
                linestyle='-', 
                linewidth=2,
                alpha=0.7,
                label=f'{model["name"]} (训练)')
        
        # Plot validation loss
        ax.plot(epochs, val_losses, 
                color=model['color'], 
                linestyle='--', 
                linewidth=2,
                label=f'{model["name"]} (验证)')
    
    # 标签和标题改为中文，去掉加粗
    ax.set_xlabel('训练轮次', fontsize=12)
    ax.set_ylabel('损失值', fontsize=12)
    ax.set_title('训练与验证损失值对比', fontsize=14, fontweight='normal')
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Loss comparison plot saved: {save_path}")

def plot_dice_comparison(models_data, save_path):
    """Plot Dice comparison"""
    fig, ax = plt.subplots(figsize=(12, 6))
    
    for model in MODELS:
        data = models_data[model['name']]
        train_dices = data[model['train_dice_key']]
        val_dices = data[model['val_dice_key']]
        epochs = range(1, len(train_dices) + 1)
        
        # Plot training Dice - 图例改为中文
        ax.plot(epochs, train_dices, 
                color=model['color'], 
                linestyle='-', 
                linewidth=2,
                alpha=0.7,
                label=f'{model["name"]} (训练)')
        
        # Plot validation Dice
        ax.plot(epochs, val_dices, 
                color=model['color'], 
                linestyle='--', 
                linewidth=2,
                label=f'{model["name"]} (验证)')
    
    # 标签和标题改为中文，去掉加粗
    ax.set_xlabel('训练轮次', fontsize=12)
    ax.set_ylabel('Dice系数', fontsize=12)
    ax.set_title('训练与验证Dice系数对比', fontsize=14, fontweight='normal')
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Dice comparison plot saved: {save_path}")

def main():
    """Main function"""
    # Get script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Load training data for all models
    models_data = {}
    for model in MODELS:
        json_path = os.path.join(script_dir, model['json_path'])
        if not os.path.exists(json_path):
            print(f"Warning: File not found {json_path}")
            continue
        data = load_training_data(json_path)
        models_data[model['name']] = data
        print(f"Loaded training data for {model['name']}")
    
    if not models_data:
        print("Error: No training data files found")
        return
    
    # Set output path
    output_dir = os.path.join(script_dir, 'results')
    os.makedirs(output_dir, exist_ok=True)
    
    loss_plot_path = os.path.join(output_dir, 'comparison_loss.png')
    dice_plot_path = os.path.join(output_dir, 'comparison_dice.png')
    
    # Plot comparison charts
    plot_loss_comparison(models_data, loss_plot_path)
    plot_dice_comparison(models_data, dice_plot_path)
    
    print("\nComparison plots generated successfully!")

if __name__ == "__main__":
    main()