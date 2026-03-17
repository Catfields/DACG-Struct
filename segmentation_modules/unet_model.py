"""
U-Net模型实现
基于经典的U-Net架构进行医学图像分割
"""

import os
import torch
import torch.nn as nn
import torch.nn.functional as F
try:
    from .config import *  # package import
except ImportError:  # fallback when running as script
    from config import *


def _load_unetpp_module():
    """Dynamically load the UNet++ module (supports upp.py or upp_model.py)."""
    import importlib.util

    base_dir = os.path.dirname(__file__)
    candidates = ['upp.py', 'upp_model.py']

    for filename in candidates:
        module_path = os.path.join(base_dir, filename)
        if not os.path.exists(module_path):
            continue

        spec = importlib.util.spec_from_file_location("segmentation_modules.upp_dynamic", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
        return module

    raise ImportError("未找到 UNet++ 实现文件（期望 upp.py 或 upp_model.py）")


def _load_attention_unet_module():
    """Dynamically load the Attention UNet module if present."""
    import importlib.util

    base_dir = os.path.dirname(__file__)
    module_path = os.path.join(base_dir, 'attention_unet_model.py')
    if not os.path.exists(module_path):
        raise ImportError("未找到 attention_unet_model.py")

    spec = importlib.util.spec_from_file_location("segmentation_modules.attention_unet_dynamic", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module

class DoubleConv(nn.Module):
    """双层卷积块"""

    def __init__(self, in_channels, out_channels):
        super(DoubleConv, self).__init__()
        self.double_conv = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )

    def forward(self, x):
        return self.double_conv(x)

class Down(nn.Module):
    """下采样块"""

    def __init__(self, in_channels, out_channels):
        super(Down, self).__init__()
        self.maxpool_conv = nn.Sequential(
            nn.MaxPool2d(2),
            DoubleConv(in_channels, out_channels)
        )

    def forward(self, x):
        return self.maxpool_conv(x)

class Up(nn.Module):
    """上采样块"""

    def __init__(self, in_channels, out_channels, bilinear=True):
        super(Up, self).__init__()

        if bilinear:
            self.up = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.conv = DoubleConv(in_channels, out_channels)
        else:
            self.up = nn.ConvTranspose2d(in_channels, in_channels // 2, kernel_size=2, stride=2)
            self.conv = DoubleConv(in_channels, out_channels)

    def forward(self, x1, x2):
        x1 = self.up(x1)

        # 处理维度不匹配的情况
        diffY = x2.size()[2] - x1.size()[2]
        diffX = x2.size()[3] - x1.size()[3]

        x1 = F.pad(x1, [diffX // 2, diffX - diffX // 2,
                        diffY // 2, diffY - diffY // 2])

        x = torch.cat([x2, x1], dim=1)
        return self.conv(x)

class OutConv(nn.Module):
    """输出卷积层"""

    def __init__(self, in_channels, out_channels):
        super(OutConv, self).__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=1)

    def forward(self, x):
        return self.conv(x)

class UNet(nn.Module):
    """U-Net模型"""

    def __init__(self, n_channels=IMG_CHANNELS, n_classes=NUM_CLASSES, bilinear=True):
        super(UNet, self).__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes
        self.bilinear = bilinear

        # 编码器部分
        self.inc = DoubleConv(n_channels, 64)
        self.down1 = Down(64, 128)
        self.down2 = Down(128, 256)
        self.down3 = Down(256, 512)
        factor = 2 if bilinear else 1
        self.down4 = Down(512, 1024 // factor)

        # 解码器部分
        self.up1 = Up(1024, 512 // factor, bilinear)
        self.up2 = Up(512, 256 // factor, bilinear)
        self.up3 = Up(256, 128 // factor, bilinear)
        self.up4 = Up(128, 64, bilinear)

        # 输出层
        self.outc = OutConv(64, n_classes)

    def forward(self, x):
        # 编码路径
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)

        # 解码路径
        x = self.up1(x5, x4)
        x = self.up2(x, x3)
        x = self.up3(x, x2)
        x = self.up4(x, x1)

        # 输出
        logits = self.outc(x)
        return logits

    def predict(self, x):
        """预测方法，返回类别编号图"""
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            probs = torch.softmax(logits, dim=1)
            preds = torch.argmax(probs, dim=1)
            return preds

class AttentionBlock(nn.Module):
    """注意力块 (可选的改进版本)"""

    def __init__(self, F_g, F_l, F_int):
        super(AttentionBlock, self).__init__()
        self.W_g = nn.Sequential(
            nn.Conv2d(F_g, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int)
        )

        self.W_x = nn.Sequential(
            nn.Conv2d(F_l, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int)
        )

        self.psi = nn.Sequential(
            nn.Conv2d(F_int, 1, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(1),
            nn.Sigmoid()
        )

        self.relu = nn.ReLU(inplace=True)

    def forward(self, g, x):
        g1 = self.W_g(g)
        x1 = self.W_x(x)
        psi = self.relu(g1 + x1)
        psi = self.psi(psi)

        return x * psi

class AttentionUNet(nn.Module):
    """带注意力机制的U-Net"""

    def __init__(self, n_channels=IMG_CHANNELS, n_classes=NUM_CLASSES):
        super(AttentionUNet, self).__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes

        # 编码器
        self.inc = DoubleConv(n_channels, 64)
        self.down1 = Down(64, 128)
        self.down2 = Down(128, 256)
        self.down3 = Down(256, 512)
        self.down4 = Down(512, 1024)

        # 注意力块
        self.att1 = AttentionBlock(F_g=1024, F_l=512, F_int=512)
        self.att2 = AttentionBlock(F_g=512, F_l=256, F_int=256)
        self.att3 = AttentionBlock(F_g=256, F_l=128, F_int=128)
        self.att4 = AttentionBlock(F_g=128, F_l=64, F_int=64)

        # 解码器
        self.up1 = Up(1024, 512)
        self.up2 = Up(512, 256)
        self.up3 = Up(256, 128)
        self.up4 = Up(128, 64)

        # 输出层
        self.outc = OutConv(64, n_classes)

    def forward(self, x):
        # 编码路径
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)

        # 解码路径（带注意力）
        x = self.up1(x5, self.att1(x5, x4))
        x = self.up2(x, self.att2(x, x3))
        x = self.up3(x, self.att3(x, x2))
        x = self.up4(x, self.att4(x, x1))

        logits = self.outc(x)
        return logits

def get_model(model_type='unet'):
    """获取模型实例"""
    if model_type == 'unet':
        return UNet(n_channels=IMG_CHANNELS, n_classes=NUM_CLASSES)
    elif model_type == 'attention_unet':
        try:
            attention_module = _load_attention_unet_module()
            if hasattr(attention_module, 'get_model'):
                return attention_module.get_model('attention_unet')
            if hasattr(attention_module, 'AttentionUNet'):
                return attention_module.AttentionUNet(n_channels=IMG_CHANNELS, n_classes=NUM_CLASSES)
        except Exception as exc:
            print(f"加载 attention_unet_model 失败 ({exc})，回退到内置 AttentionUNet。")
        return AttentionUNet(n_channels=IMG_CHANNELS, n_classes=NUM_CLASSES)
    elif model_type == 'unet++':
        upp_module = _load_unetpp_module()
        if hasattr(upp_module, 'get_model'):
            return upp_module.get_model('unet++')
        if hasattr(upp_module, 'NestedUNet'):
            return upp_module.NestedUNet(n_channels=IMG_CHANNELS, n_classes=NUM_CLASSES)
        raise AttributeError("UNet++ 模块缺少 get_model 或 NestedUNet 实现")
    else:
        raise ValueError(f"不支持的模型类型: {model_type}")

def test_model():
    """测试模型"""
    print("测试U-Net模型...")

    device = torch.device(DEVICE)
    model = get_model('unet').to(device)

    # 创建测试输入
    test_input = torch.randn(2, IMG_CHANNELS, IMG_HEIGHT, IMG_WIDTH).to(device)

    print(f"输入形状: {test_input.shape}")

    # 前向传播
    with torch.no_grad():
        output = model(test_input)
        prediction = model.predict(test_input)

    print(f"输出形状: {output.shape}")
    print(f"预测形状: {prediction.shape}")
    print(f"输出值范围: [{output.min():.3f}, {output.max():.3f}]")
    print(f"预测值范围: [{prediction.min():.3f}, {prediction.max():.3f}]")

    # 计算模型参数数量
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    print(f"总参数数量: {total_params:,}")
    print(f"可训练参数数量: {trainable_params:,}")

    print("模型测试完成！")

if __name__ == "__main__":
    test_model()
