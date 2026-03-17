"""
损失函数定义
包含多分类分割所需的交叉熵、Dice等损失函数
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    from .config import NUM_CLASSES
except ImportError:
    from config import NUM_CLASSES


class CrossEntropyLossMC(nn.Module):
    """标准多分类交叉熵损失"""

    def __init__(self, weight=None, ignore_index=255):
        super().__init__()
        self.loss = nn.CrossEntropyLoss(weight=weight, ignore_index=ignore_index)

    def forward(self, inputs, targets):
        """
        Args:
            inputs: (N, C, H, W) logits
            targets: (N, H, W) long
        """
        return self.loss(inputs, targets.long())


class DiceLossMC(nn.Module):
    """多分类Dice损失（默认不包含背景）"""

    def __init__(self, smooth=1e-6, include_background=False):
        super().__init__()
        self.smooth = smooth
        self.include_background = include_background

    def forward(self, inputs, targets):
        """
        Args:
            inputs: (N, C, H, W) logits
            targets: (N, H, W) long
        """
        num_classes = inputs.shape[1]
        probs = torch.softmax(inputs, dim=1)

        targets_oh = F.one_hot(targets.long(), num_classes=num_classes).permute(0, 3, 1, 2).float()

        if not self.include_background and num_classes > 1:
            probs = probs[:, 1:, ...]
            targets_oh = targets_oh[:, 1:, ...]

        dims = (0, 2, 3)
        intersection = (probs * targets_oh).sum(dims)
        denominator = probs.sum(dims) + targets_oh.sum(dims)

        dice = (2 * intersection + self.smooth) / (denominator + self.smooth)
        return 1 - dice.mean()


class CEDiceLossMC(nn.Module):
    """交叉熵 + 多分类Dice组合损失"""

    def __init__(self, ce_weight=0.7, include_background=False):
        super().__init__()
        self.ce_weight = ce_weight
        self.ce_loss = CrossEntropyLossMC()
        self.dice_loss = DiceLossMC(include_background=include_background)

    def forward(self, inputs, targets):
        ce = self.ce_loss(inputs, targets)
        dice = self.dice_loss(inputs, targets)
        return self.ce_weight * ce + (1 - self.ce_weight) * dice


def get_loss_function(loss_type='cross_entropy'):
    """获取损失函数"""
    loss_type = loss_type.lower()

    if loss_type == 'cross_entropy':
        return CrossEntropyLossMC()
    if loss_type in ('ce_dice', 'ce_dice_mc', 'combined'):
        if loss_type == 'combined':
            print("警告: 'combined' 已弃用，已自动切换为多分类CE+Dice损失。")
        return CEDiceLossMC()
    if loss_type in ('dice', 'dice_mc'):
        return DiceLossMC()

    raise ValueError(f"不支持的损失函数类型: {loss_type}")


def test_loss_functions():
    """测试损失函数"""
    print("测试损失函数...")

    pred = torch.randn(2, NUM_CLASSES, 256, 256)
    target = torch.randint(0, NUM_CLASSES, (2, 256, 256))

    loss_types = ['cross_entropy', 'ce_dice_mc', 'dice_mc']
    for loss_type in loss_types:
        loss_fn = get_loss_function(loss_type)
        loss = loss_fn(pred, target)
        print(f"{loss_type}: {loss.item():.4f}")

    print("损失函数测试完成！")


if __name__ == "__main__":
    test_loss_functions()
