"""
训练器模块
包含U-Net模型的训练、验证和保存功能
"""

import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
from datetime import datetime
import json
import torch.nn.functional as F
try:
    from .config import *
except ImportError:
    from config import *
from unet_model import get_model
from data_loader import create_data_loaders
from losses import get_loss_function

plt.rcParams['font.sans-serif'] = ['AR PL UMing CN']
plt.rcParams['axes.unicode_minus'] = False
class Trainer:
    """训练器类"""

    def __init__(self, model_type='unet', loss_type='cross_entropy', learning_rate=LEARNING_RATE):
        """
        初始化训练器

        Args:
            model_type: 模型类型 ('unet' 或 'attention_unet')
            loss_type: 损失函数类型
            learning_rate: 学习率
        """
        self.device = torch.device(DEVICE)
        self.model = get_model(model_type).to(self.device)
        self.criterion = get_loss_function(loss_type)
        self.optimizer = optim.Adam(self.model.parameters(), lr=learning_rate, weight_decay=1e-5)
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer, mode='min', factor=0.5, patience=10
        )
        self.model_save_dir, self.results_dir = self._resolve_output_dirs(model_type)
        os.makedirs(self.model_save_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)

        # 训练历史
        self.train_losses = []
        self.val_losses = []
        self.train_dices = []
        self.val_dices = []
        self.best_val_dice = 0.0

        # 模型和损失类型
        self.model_type = model_type
        self.loss_type = loss_type

        print(f"训练器初始化完成:")
        print(f"  模型: {model_type}")
        print(f"  损失函数: {loss_type}")
        print(f"  设备: {self.device}")
        print(f"  学习率: {learning_rate}")
        print(f"  权重保存目录: {self.model_save_dir}")
        print(f"  结果输出目录: {self.results_dir}")

    def _resolve_output_dirs(self, model_type):
        """按模型类型选择权重与日志目录"""
        base_dir = os.path.dirname(__file__)
        models_root = os.path.join(base_dir, 'models')
        results_root = os.path.join(base_dir, 'results')
        mapping = {
            'attention_unet': (
                os.path.join(models_root, 'attention_unet_model'),
                os.path.join(results_root, 'attention_unet_results'),
            ),
            'unet++': (
                os.path.join(models_root, 'unetpp_model'),
                os.path.join(results_root, 'unetpp_results'),
            ),
        }
        return mapping.get(model_type, (MODEL_SAVE_DIR, RESULTS_DIR))

    def multiclass_dice(self, logits, targets, include_background=False):
        """计算多分类Dice系数（默认不包含背景）"""
        with torch.no_grad():
            num_classes = logits.shape[1]
            probs = torch.softmax(logits, dim=1)
            targets_oh = F.one_hot(targets.long(), num_classes=num_classes).permute(0, 3, 1, 2).float()

            if not include_background and num_classes > 1:
                probs = probs[:, 1:, ...]
                targets_oh = targets_oh[:, 1:, ...]

            dims = (0, 2, 3)
            intersection = (probs * targets_oh).sum(dims)
            denominator = probs.sum(dims) + targets_oh.sum(dims)
            dice = (2 * intersection + 1e-6) / (denominator + 1e-6)

            return dice.mean().item()

    def train_epoch(self, train_loader):
        """训练一个epoch"""
        self.model.train()
        total_loss = 0.0
        total_dice = 0.0

        progress_bar = tqdm(train_loader, desc="训练")
        for batch_idx, (images, masks) in enumerate(progress_bar):
            images = images.to(self.device, non_blocking=True)
            masks = masks.to(self.device, non_blocking=True)

            # 前向传播
            self.optimizer.zero_grad()
            outputs = self.model(images)

            # 计算损失
            loss = self.criterion(outputs, masks)

            # 反向传播
            loss.backward()
            self.optimizer.step()

            # 计算指标
            dice = self.multiclass_dice(outputs, masks)
            total_loss += loss.item()
            total_dice += dice

            # 更新进度条
            progress_bar.set_postfix({
                'loss': f'{loss.item():.4f}',
                'dice': f'{dice:.4f}'
            })

        avg_loss = total_loss / len(train_loader)
        avg_dice = total_dice / len(train_loader)

        return avg_loss, avg_dice

    def validate_epoch(self, val_loader):
        """验证一个epoch"""
        self.model.eval()
        total_loss = 0.0
        total_dice = 0.0

        with torch.no_grad():
            progress_bar = tqdm(val_loader, desc="验证")
            for batch_idx, (images, masks) in enumerate(progress_bar):
                images = images.to(self.device, non_blocking=True)
                masks = masks.to(self.device, non_blocking=True)

                outputs = self.model(images)
                loss = self.criterion(outputs, masks)
                dice = self.multiclass_dice(outputs, masks)

                total_loss += loss.item()
                total_dice += dice

                progress_bar.set_postfix({
                    'loss': f'{loss.item():.4f}',
                    'dice': f'{dice:.4f}'
                })

        avg_loss = total_loss / len(val_loader)
        avg_dice = total_dice / len(val_loader)

        return avg_loss, avg_dice

    def train(self, train_loader, val_loader, epochs=EPOCHS):
        """完整训练过程"""
        print(f"开始训练 {epochs} 个epoch...")

        for epoch in range(epochs):
            print(f"\nEpoch {epoch+1}/{epochs}")

            # 训练
            train_loss, train_dice = self.train_epoch(train_loader)

            # 验证
            val_loss, val_dice = self.validate_epoch(val_loader)

            # 更新学习率
            self.scheduler.step(val_loss)

            # 记录历史
            self.train_losses.append(train_loss)
            self.val_losses.append(val_loss)
            self.train_dices.append(train_dice)
            self.val_dices.append(val_dice)

            # 打印结果
            print(f"训练损失: {train_loss:.4f}, 训练Dice: {train_dice:.4f}")
            print(f"验证损失: {val_loss:.4f}, 验证Dice: {val_dice:.4f}")

            # 保存最佳模型
            if val_dice > self.best_val_dice:
                self.best_val_dice = val_dice
                self.save_model('best_model.pth')
                print(f"保存最佳模型 (Dice: {val_dice:.4f})")

            # 定期保存检查点
            if (epoch + 1) % 10 == 0:
                self.save_model(f'checkpoint_epoch_{epoch+1}.pth')

        print(f"训练完成！最佳验证Dice: {self.best_val_dice:.4f}")

    def save_model(self, filename):
        """保存模型"""
        filepath = os.path.join(self.model_save_dir, filename)
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'scheduler_state_dict': self.scheduler.state_dict(),
            'model_type': self.model_type,
            'loss_type': self.loss_type,
            'best_val_dice': self.best_val_dice,
            'train_losses': self.train_losses,
            'val_losses': self.val_losses,
            'train_dices': self.train_dices,
            'val_dices': self.val_dices
        }, filepath)

    def load_model(self, filename):
        """加载模型"""
        filepath = os.path.join(self.model_save_dir, filename)
        checkpoint = torch.load(filepath, map_location=self.device)

        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
        self.best_val_dice = checkpoint['best_val_dice']
        self.train_losses = checkpoint['train_losses']
        self.val_losses = checkpoint['val_losses']
        self.train_dices = checkpoint['train_dices']
        self.val_dices = checkpoint['val_dices']

        print(f"模型加载成功: {filename}")

    def plot_training_history(self):
        """绘制训练历史"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5))

        # 损失曲线
        ax1.plot(self.train_losses, label='训练损失')
        ax1.plot(self.val_losses, label='验证损失')
        ax1.set_title('训练和验证损失')
        ax1.set_xlabel('Epoch')
        ax1.set_ylabel('损失')
        ax1.legend()
        ax1.grid(True)

        # Dice系数曲线
        ax2.plot(self.train_dices, label='训练Dice')
        ax2.plot(self.val_dices, label='验证Dice')
        ax2.set_title('训练和验证Dice系数')
        ax2.set_xlabel('Epoch')
        ax2.set_ylabel('Dice系数')
        ax2.legend()
        ax2.grid(True)

        plt.tight_layout()
        plt.savefig(os.path.join(self.results_dir, 'training_history.png'), dpi=300, bbox_inches='tight')
        plt.show()

    def save_training_info(self):
        """保存训练信息"""
        info = {
            'model_type': self.model_type,
            'loss_type': self.loss_type,
            'best_val_dice': self.best_val_dice,
            'train_losses': self.train_losses,
            'val_losses': self.val_losses,
            'train_dices': self.train_dices,
            'val_dices': self.val_dices,
            'timestamp': datetime.now().isoformat()
        }

        filepath = os.path.join(self.results_dir, 'training_info.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(info, f, indent=4, ensure_ascii=False)

        print(f"训练信息已保存: {filepath}")

def main():
    """主训练函数"""
    print("U-Net医学图像分割训练开始...")

    # 创建数据加载器
    train_loader, val_loader, test_loader = create_data_loaders()

    # 创建训练器
    trainer = Trainer(
        model_type='unet',
        loss_type='combined',
        learning_rate=LEARNING_RATE
    )

    # 开始训练
    trainer.train(train_loader, val_loader, epochs=EPOCHS)

    # 绘制训练历史
    trainer.plot_training_history()

    # 保存训练信息
    trainer.save_training_info()

    print("训练完成！")

if __name__ == "__main__":
    main()
