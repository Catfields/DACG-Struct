"""
生成原图、真实掩膜和预测掩膜的对比图
生成3张图：原图、黑白真实掩膜、黑白预测掩膜
"""

import os
import torch
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt

from config import *
from unet_model import get_model
from data_loader import create_data_loaders

plt.rcParams['font.family'] = 'DejaVu Sans'


def load_model(model_path='models/unet_model/best_model.pth'):
    """加载训练好的模型"""
    device = torch.device(DEVICE)
    
    # 加载模型权重
    checkpoint = torch.load(model_path, map_location=device)
    model_type = checkpoint.get('model_type', 'unet')
    model = get_model(model_type).to(device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    print(f"模型加载成功: {model_path} (model_type={model_type})")
    return model, device


def mask_to_binary(mask):
    """将多分类掩膜转换为二值掩膜（黑白）"""
    # 背景为0，所有前景类别合并为1
    binary_mask = (mask > 0).astype(np.uint8) * 255
    return binary_mask


def denormalize_image(image_tensor):
    """反归一化图像"""
    mean = np.array([0.485, 0.456, 0.406])
    std = np.array([0.229, 0.224, 0.225])
    
    image = image_tensor.cpu().numpy()
    image = image * std[:, None, None] + mean[:, None, None]
    image = np.clip(image, 0, 1)
    image = image.transpose(1, 2, 0)
    return image


def generate_comparison_images(model, device, test_loader, save_dir='results', sample_idx=0):
    """
    生成对比图像
    
    Args:
        model: 训练好的模型
        device: 设备
        test_loader: 测试数据加载器
        save_dir: 保存目录
        sample_idx: 要可视化的样本索引
    """
    os.makedirs(save_dir, exist_ok=True)
    
    # 获取指定样本
    count = 0
    with torch.no_grad():
        for batch_idx, (images, masks) in enumerate(test_loader):
            batch_size = images.shape[0]
            
            for i in range(batch_size):
                if count == sample_idx:
                    # 获取单个样本
                    image = images[i:i+1].to(device)
                    mask = masks[i]
                    
                    # 预测
                    output = model(image)
                    probs = torch.softmax(output, dim=1)
                    pred = torch.argmax(probs, dim=1)[0].cpu().numpy()
                    
                    # 反归一化原图
                    original_image = denormalize_image(images[i])
                    
                    # 转换为uint8
                    original_image_uint8 = (original_image * 255).astype(np.uint8)
                    
                    # 转换掩膜为黑白
                    mask_np = mask.cpu().numpy()
                    binary_gt_mask = mask_to_binary(mask_np)
                    binary_pred_mask = mask_to_binary(pred)
                    
                    # 保存原图
                    original_img_pil = Image.fromarray(original_image_uint8)
                    original_path = os.path.join(save_dir, f'original_image_{sample_idx}.png')
                    original_img_pil.save(original_path)
                    print(f"原图已保存: {original_path}")
                    
                    # 保存真实掩膜（黑白）
                    gt_mask_pil = Image.fromarray(binary_gt_mask, mode='L')
                    gt_path = os.path.join(save_dir, f'ground_truth_mask_{sample_idx}.png')
                    gt_mask_pil.save(gt_path)
                    print(f"真实掩膜已保存: {gt_path}")
                    
                    # 保存预测掩膜（黑白）
                    pred_mask_pil = Image.fromarray(binary_pred_mask, mode='L')
                    pred_path = os.path.join(save_dir, f'predicted_mask_{sample_idx}.png')
                    pred_mask_pil.save(pred_path)
                    print(f"预测掩膜已保存: {pred_path}")
                    
                    return original_path, gt_path, pred_path
                
                count += 1
    
    print(f"样本索引 {sample_idx} 超出范围，总样本数: {count}")
    return None, None, None


def generate_combined_comparison(model, device, test_loader, save_path='results/mask_comparison.png', sample_idx=0):
    """
    生成组合对比图（3张图并排显示）
    
    Args:
        model: 训练好的模型
        device: 设备
        test_loader: 测试数据加载器
        save_path: 保存路径
        sample_idx: 要可视化的样本索引
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
    # 获取指定样本
    count = 0
    with torch.no_grad():
        for batch_idx, (images, masks) in enumerate(test_loader):
            batch_size = images.shape[0]
            
            for i in range(batch_size):
                if count == sample_idx:
                    # 获取单个样本
                    image = images[i:i+1].to(device)
                    mask = masks[i]
                    
                    # 预测
                    output = model(image)
                    probs = torch.softmax(output, dim=1)
                    pred = torch.argmax(probs, dim=1)[0].cpu().numpy()
                    
                    # 反归一化原图
                    original_image = denormalize_image(images[i])
                    
                    # 转换为uint8
                    original_image_uint8 = (original_image * 255).astype(np.uint8)
                    
                    # 转换掩膜为黑白
                    mask_np = mask.cpu().numpy()
                    binary_gt_mask = mask_to_binary(mask_np)
                    binary_pred_mask = mask_to_binary(pred)
                    
                    # 创建对比图
                    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
                    
                    # 原图
                    axes[0].imshow(original_image_uint8)
                    axes[0].set_title('Original Image', fontsize=14, fontweight='bold')
                    axes[0].axis('off')
                    
                    # 真实掩膜（黑白）
                    axes[1].imshow(binary_gt_mask, cmap='gray')
                    axes[1].set_title('Ground Truth Mask', fontsize=14, fontweight='bold')
                    axes[1].axis('off')
                    
                    # 预测掩膜（黑白）
                    axes[2].imshow(binary_pred_mask, cmap='gray')
                    axes[2].set_title('Predicted Mask', fontsize=14, fontweight='bold')
                    axes[2].axis('off')
                    
                    plt.tight_layout()
                    plt.savefig(save_path, dpi=300, bbox_inches='tight')
                    plt.close()
                    
                    print(f"组合对比图已保存: {save_path}")
                    return save_path
                
                count += 1
    
    print(f"样本索引 {sample_idx} 超出范围，总样本数: {count}")
    return None


def main():
    """主函数"""
    print("开始生成掩膜对比图...")
    
    # 加载模型
    model_path = 'models/unet_model/best_model.pth'
    model, device = load_model(model_path)
    
    # 创建测试数据加载器
    _, _, test_loader = create_data_loaders(batch_size=1, num_workers=0, pin_memory=False)
    
    # 设置保存目录
    save_dir = 'results'
    
    # 生成单独的3张图
    print("\n生成单独的3张图...")
    original_path, gt_path, pred_path = generate_comparison_images(
        model, device, test_loader, save_dir=save_dir, sample_idx=0
    )
    
    # 生成组合对比图
    print("\n生成组合对比图...")
    combined_path = generate_combined_comparison(
        model, device, test_loader, save_path='results/mask_comparison_combined.png', sample_idx=0
    )
    
    print("\n生成完成！")
    if original_path and gt_path and pred_path:
        print(f"- 原图: {original_path}")
        print(f"- 真实掩膜: {gt_path}")
        print(f"- 预测掩膜: {pred_path}")
    if combined_path:
        print(f"- 组合对比图: {combined_path}")


if __name__ == "__main__":
    main()
