"""
Attention U-Net 模型实现
在经典 U-Net 的跳跃连接处加入注意力门控，保持与 segmentation_modules/unet_model.Unet
相同的输入输出维度与接口（IMG_CHANNELS -> NUM_CLASSES，空间尺寸不变）。
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

try:  # 支持包内与脚本两种运行方式
    from .config import *
except ImportError:
    from config import *


class DoubleConv(nn.Module):
    """两层卷积 + BN + ReLU，用于特征提取"""

    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.double_conv = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.double_conv(x)


class Down(nn.Module):
    """下采样：MaxPool + DoubleConv"""

    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.maxpool_conv = nn.Sequential(
            nn.MaxPool2d(kernel_size=2),
            DoubleConv(in_channels, out_channels),
        )

    def forward(self, x):
        return self.maxpool_conv(x)


class Up(nn.Module):
    """上采样：双线性上采样或反卷积，再与 skip 拼接并卷积"""

    def __init__(self, in_channels, out_channels, bilinear=True):
        super().__init__()
        if bilinear:
            self.up = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
        else:
            self.up = nn.ConvTranspose2d(in_channels // 2, in_channels // 2, kernel_size=2, stride=2)

        self.conv = DoubleConv(in_channels, out_channels)

    def forward(self, x1, x2):
        x1 = self.up(x1)
        diffY = x2.size(2) - x1.size(2)
        diffX = x2.size(3) - x1.size(3)
        x1 = F.pad(x1, [diffX // 2, diffX - diffX // 2,
                        diffY // 2, diffY - diffY // 2])
        x = torch.cat([x2, x1], dim=1)
        return self.conv(x)


class OutConv(nn.Module):
    """最终 1x1 卷积输出类别 logits"""

    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=1)

    def forward(self, x):
        return self.conv(x)


class AttentionBlock(nn.Module):
    """注意力门控，抑制无用 skip 信息"""

    def __init__(self, F_g, F_l, F_int):
        super().__init__()
        self.W_g = nn.Sequential(
            nn.Conv2d(F_g, F_int, kernel_size=1, stride=1, padding=0, bias=False),
            nn.BatchNorm2d(F_int),
        )
        self.W_x = nn.Sequential(
            nn.Conv2d(F_l, F_int, kernel_size=1, stride=1, padding=0, bias=False),
            nn.BatchNorm2d(F_int),
        )
        self.psi = nn.Sequential(
            nn.Conv2d(F_int, 1, kernel_size=1, stride=1, padding=0, bias=True),
            nn.Sigmoid(),
        )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, g, x):
        g1 = self.W_g(g)
        x1 = self.W_x(x)
        if g1.shape[2:] != x1.shape[2:]:
            g1 = F.interpolate(g1, size=x1.shape[2:], mode='bilinear', align_corners=True)
        psi = self.relu(g1 + x1)
        psi = self.psi(psi)
        return x * psi


class AttentionUNet(nn.Module):
    """Attention U-Net，结构与基础 U-Net 对齐"""

    def __init__(self, n_channels=IMG_CHANNELS, n_classes=NUM_CLASSES, bilinear=True):
        super().__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes
        self.bilinear = bilinear

        factor = 2 if bilinear else 1

        # 编码器
        self.inc = DoubleConv(n_channels, 64)
        self.down1 = Down(64, 128)
        self.down2 = Down(128, 256)
        self.down3 = Down(256, 512)
        self.down4 = Down(512, 1024 // factor)

        # 注意力块（g 来自解码端，l 为 skip 特征）
        self.att1 = AttentionBlock(1024 // factor, 512, 512 // factor)
        self.att2 = AttentionBlock(512 // factor, 256, 256 // factor)
        self.att3 = AttentionBlock(256 // factor, 128, 128 // factor)
        self.att4 = AttentionBlock(128 // factor, 64, 64 // factor if factor > 1 else 64)

        # 解码器
        self.up1 = Up(1024, 512 // factor, bilinear)
        self.up2 = Up(512, 256 // factor, bilinear)
        self.up3 = Up(256, 128 // factor, bilinear)
        self.up4 = Up(128, 64, bilinear)

        self.outc = OutConv(64, n_classes)

    def forward(self, x):
        # 编码
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)

        # 带注意力的解码
        x = self.up1(x5, self.att1(x5, x4))
        x = self.up2(x, self.att2(x, x3))
        x = self.up3(x, self.att3(x, x2))
        x = self.up4(x, self.att4(x, x1))

        return self.outc(x)

    def predict(self, x):
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            probs = torch.softmax(logits, dim=1)
            preds = torch.argmax(probs, dim=1)
            return preds


def get_model(model_type='attention_unet'):
    if model_type != 'attention_unet':
        raise ValueError(f"Unsupported model_type: {model_type}")
    return AttentionUNet(n_channels=IMG_CHANNELS, n_classes=NUM_CLASSES)


def test_model():
    """简单的前向测试，确保输入输出维度匹配"""
    print("Testing Attention U-Net ...")
    device = torch.device(DEVICE)
    model = get_model().to(device)
    dummy = torch.randn(2, IMG_CHANNELS, IMG_HEIGHT, IMG_WIDTH, device=device)
    with torch.no_grad():
        out = model(dummy)
    print(f"Input shape : {dummy.shape}")
    print(f"Output shape: {out.shape}")
    assert out.shape == (2, NUM_CLASSES, IMG_HEIGHT, IMG_WIDTH), "输出维度不匹配"
    print("Attention U-Net forward passes!")


if __name__ == "__main__":
    test_model()
