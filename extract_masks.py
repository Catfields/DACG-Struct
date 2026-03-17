#!/usr/bin/env python3
"""
MIMIC-CXR-A 掩膜提取脚本
使用 UNet++ 模型对图像进行器官分割（右肺、左肺、心脏）
"""

import os
import json
import argparse
from pathlib import Path
from tqdm import tqdm
import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F
from torchvision import transforms
import torchvision.transforms.functional as TF

# 添加项目路径
import sys
sys.path.insert(0, '/home/y530/handsome/DACG')

from segmentation_modules.upp_model import NestedUNet, get_model
from segmentation_modules.config import (
    IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS, NUM_CLASSES,
    CLASS_NAMES, CLASS_COLOR_MAP, DEVICE
)


class MaskExtractor:
    """掩膜提取器类"""
    
    def __init__(self, model_path, device=None):
        """
        初始化掩膜提取器
        
        Args:
            model_path: 模型权重文件路径
            device: 计算设备（cuda/cpu）
        """
        self.device = device if device else torch.device(DEVICE)
        self.model = self._load_model(model_path)
        self.model.eval()
        
    def _load_model(self, model_path):
        """加载预训练模型"""
        print(f"正在加载模型: {model_path}")
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"模型文件不存在: {model_path}")
        
        # 创建模型实例
        model = get_model('unet++', deep_supervision=False)
        
        # 加载权重
        checkpoint = torch.load(model_path, map_location='cpu')
        
        # 处理不同的 checkpoint 格式
        if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            model.load_state_dict(checkpoint['model_state_dict'])
            print("检测到 'model_state_dict' 格式，已加载")
        elif isinstance(checkpoint, dict) and 'state_dict' in checkpoint:
            model.load_state_dict(checkpoint['state_dict'])
            print("检测到 'state_dict' 格式，已加载")
        else:
            # 直接加载整个 checkpoint
            model.load_state_dict(checkpoint)
            print("直接加载模型权重")
        
        model = model.to(self.device)
        print(f"模型加载完成，参数数量: {sum(p.numel() for p in model.parameters()):,}")
        return model
    
    def _get_image_transform(self):
        """获取图像预处理变换"""
        return transforms.Compose([
            transforms.Resize((IMG_HEIGHT, IMG_WIDTH), interpolation=transforms.InterpolationMode.BILINEAR),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                           std=[0.229, 0.224, 0.225])
        ])
    
    def extract_mask(self, image_path):
        """
        对单张图像提取掩膜
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            mask: 掩膜数组 (H, W)，值为类别编号 0-3
        """
        try:
            # 读取图像
            image = Image.open(image_path).convert('RGB')
            
            # 预处理
            transform = self._get_image_transform()
            image_tensor = transform(image).unsqueeze(0).to(self.device)
            
            # 推理
            with torch.no_grad():
                output = self.model(image_tensor)
                
                # 获取预测类别
                probs = torch.softmax(output, dim=1)
                preds = torch.argmax(probs, dim=1)
                
                # 转为 numpy 数组
                mask = preds.squeeze(0).cpu().numpy()
                
            return mask
            
        except Exception as e:
            print(f"处理图像失败 {image_path}: {str(e)}")
            return None
    
    def save_mask(self, mask, output_dir, base_filename):
        """
        保存掩膜为二值掩膜组
        
        Args:
            mask: 掩膜数组 (H, W)，值为类别编号 0-3
            output_dir: 输出目录路径
            base_filename: 基础文件名（不含扩展名）
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # 为每个前景类别保存二值掩膜
            for class_id, class_name in [
                (1, 'rightlung'),
                (2, 'leftlung'),
                (3, 'heart')
            ]:
                # 创建二值掩膜：255表示前景，0表示背景
                binary_mask = (mask == class_id).astype(np.uint8) * 255
                
                # 保存为单通道PNG
                mask_image = Image.fromarray(binary_mask, mode='L')
                
                # 构建输出文件名
                output_path = os.path.join(output_dir, f"{base_filename}_mask_{class_name}.png")
                mask_image.save(output_path)
                
        except Exception as e:
            print(f"保存掩膜失败 {output_dir}: {str(e)}")
    
    def process_jsonl(self, jsonl_path, image_root, output_dir):
        """
        处理 JSONL 文件中的所有图像
        
        Args:
            jsonl_path: JSONL 文件路径
            image_root: 图像根目录
            output_dir: 掩膜输出目录
        """
        # 读取 JSONL 文件
        print(f"正在读取 JSONL 文件: {jsonl_path}")
        
        image_paths = []
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if 'metadata' in data and 'image_path' in data['metadata']:
                        paths = data['metadata']['image_path']
                        image_paths.extend(paths)
        
        print(f"找到 {len(image_paths)} 张图像")
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 处理每张图像
        success_count = 0
        fail_count = 0
        
        for idx, rel_path in enumerate(tqdm(image_paths, desc="处理图像进度")):
            # 构建完整图像路径
            image_path = os.path.join(image_root, rel_path)
            
            # 检查图像是否存在
            if not os.path.exists(image_path):
                print(f"警告: 图像不存在: {image_path}")
                fail_count += 1
                continue
            
            # 提取掩膜
            mask = self.extract_mask(image_path)
            
            if mask is None:
                fail_count += 1
                continue
            
            # 构建输出路径
            # 保持与原图相同的目录结构
            rel_dir = os.path.dirname(rel_path)
            mask_dir = os.path.join(output_dir, rel_dir)
            
            # 使用相同的文件名（不含扩展名）
            base_filename = os.path.splitext(os.path.basename(rel_path))[0]
            
            # 保存掩膜
            self.save_mask(mask, mask_dir, base_filename)
            success_count += 1
        
        # 打印统计信息
        print(f"\n处理完成!")
        print(f"成功: {success_count} 张")
        print(f"失败: {fail_count} 张")
        print(f"掩膜保存位置: {output_dir}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MIMIC-CXR-A 掩膜提取工具')
    
    parser.add_argument('--jsonl', type=str, 
                   default='data/mimic-cxr-a/all_structured_reports.jsonl',
                   help='JSONL 文件路径')
    parser.add_argument('--image-root', type=str,
                   default='data/mimic-cxr-a/images',
                   help='图像根目录')
    parser.add_argument('--output-dir', type=str,
                   default='data/mimic-cxr-a/masks',
                   help='掩膜输出目录')
    parser.add_argument('--model-path', type=str,
                   default='my_ml_app/models/upp_model.pth',
                   help='模型权重文件路径')
    parser.add_argument('--device', type=str, default=None,
                   help='计算设备 (cuda/cpu)，默认自动检测')
    parser.add_argument('--limit', type=int, default=None,
                   help='限制处理图像数量（用于测试）')
    
    args = parser.parse_args()
    
    # 打印配置信息
    print("=" * 60)
    print("MIMIC-CXR-A 掩膜提取工具")
    print("=" * 60)
    print(f"JSONL 文件: {args.jsonl}")
    print(f"图像根目录: {args.image_root}")
    print(f"输出目录: {args.output_dir}")
    print(f"模型路径: {args.model_path}")
    print(f"计算设备: {args.device if args.device else DEVICE}")
    print(f"模型配置: {IMG_CHANNELS}通道, {IMG_HEIGHT}x{IMG_WIDTH}, {NUM_CLASSES}类")
    print(f"类别: {CLASS_NAMES}")
    print("=" * 60)
    
    # 创建掩膜提取器
    try:
        extractor = MaskExtractor(args.model_path, device=args.device)
        
        # 处理 JSONL 文件
        extractor.process_jsonl(args.jsonl, args.image_root, args.output_dir)
        
    except KeyboardInterrupt:
        print("\n\n用户中断处理")
    except Exception as e:
        print(f"\n\n错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
