"""
UNet++模型实现（Nested UNet）
基于经典UNet++架构进行医学图像分割
保持与原UNet相同的5层结构和输入输出维度
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
try:
    from .config import *  # package import
except ImportError:  # fallback when running as script
    from config import *

class DoubleConv(nn.Module):
    """双层卷积块，与原UNet保持一致"""
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
    """下采样块，与原UNet保持一致"""
    def __init__(self, in_channels, out_channels):
        super(Down, self).__init__()
        self.maxpool_conv = nn.Sequential(
            nn.MaxPool2d(2),
            DoubleConv(in_channels, out_channels)
        )

    def forward(self, x):
        return self.maxpool_conv(x)

class Up(nn.Module):
    """上采样块，与原UNet保持一致"""
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
    """输出卷积层，与原UNet保持一致"""
    def __init__(self, in_channels, out_channels):
        super(OutConv, self).__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=1)

    def forward(self, x):
        return self.conv(x)

class NestedUNet(nn.Module):
    """UNet++模型（Nested UNet）
    保持与原UNet相同的5层深度结构和输入输出维度
    """

    def __init__(self, n_channels=IMG_CHANNELS, n_classes=NUM_CLASSES, bilinear=True):
        super(NestedUNet, self).__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes
        self.bilinear = bilinear

        # 计算通道数缩放因子
        factor = 2 if bilinear else 1

        # 编码器 backbone（与原UNet相同）
        self.pool = nn.MaxPool2d(2)

        # X0,0: 第一层输入块
        self.conv0_0 = DoubleConv(n_channels, 64)

        # X1,0: 第二层下采样
        self.conv1_0 = DoubleConv(64, 128)

        # X2,0: 第三层下采样
        self.conv2_0 = DoubleConv(128, 256)

        # X3,0: 第四层下采样
        self.conv3_0 = DoubleConv(256, 512)

        # X4,0: 瓶颈层（第五层）
        self.conv4_0 = DoubleConv(512, 1024 // factor)

        # UNet++ 嵌套和跳跃连接 - 修正通道数
        # 第一列：X0,1 -> X0,2 -> X0,3 -> X0,4
        self.conv0_1 = DoubleConv(64 + 128, 64)  # x0_0 + up1_0(x1_0)
        self.conv0_2 = DoubleConv(64 + 128, 64)  # x0_0 + up0_1(x1_1)
        self.conv0_3 = DoubleConv(64 + 128, 64)  # x0_0 + up0_2(x1_2)
        self.conv0_4 = DoubleConv(64 + 128, 64)  # x0_0 + up0_3(x1_3)

        # 第二列：X1,1 -> X1,2 -> X1,3
        self.conv1_1 = DoubleConv(128 + 256, 128)  # x1_0 + up2_0(x2_0)
        self.conv1_2 = DoubleConv(128 + 256, 128)  # x1_0 + up1_1(x2_1)
        self.conv1_3 = DoubleConv(128 + 256, 128)  # x1_0 + up1_2(x2_2)

        # 第三列：X2,1 -> X2,2
        self.conv2_1 = DoubleConv(256 + 512, 256)  # x2_0 + up3_0(x3_0)
        self.conv2_2 = DoubleConv(256 + 512, 256)  # x2_0 + up2_1(x3_1)

        # 第四列：X3,1
        self.conv3_1 = DoubleConv(512 + (1024 // factor), 512)  # x3_0 + up4_0(x4_0)

        # 上采样操作
        if bilinear:
            self.up4_0 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up3_1 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up3_0 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up2_2 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up2_1 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up2_0 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up1_3 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up1_2 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up1_1 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up1_0 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up0_4 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up0_3 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up0_2 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.up0_1 = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
        else:
            self.up4_0 = nn.ConvTranspose2d(1024 // factor, 512, kernel_size=2, stride=2)
            self.up3_1 = nn.ConvTranspose2d(512 + (1024 // factor), 256, kernel_size=2, stride=2)
            self.up3_0 = nn.ConvTranspose2d(512, 256, kernel_size=2, stride=2)
            self.up2_2 = nn.ConvTranspose2d(256*2 + (1024 // factor), 128, kernel_size=2, stride=2)
            self.up2_1 = nn.ConvTranspose2d(256*2, 128, kernel_size=2, stride=2)
            self.up2_0 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
            self.up1_3 = nn.ConvTranspose2d(128*3 + (1024 // factor), 64, kernel_size=2, stride=2)
            self.up1_2 = nn.ConvTranspose2d(128*3, 64, kernel_size=2, stride=2)
            self.up1_1 = nn.ConvTranspose2d(128*2, 64, kernel_size=2, stride=2)
            self.up1_0 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
            self.up0_4 = nn.ConvTranspose2d(64*4 + (1024 // factor), 64, kernel_size=2, stride=2)
            self.up0_3 = nn.ConvTranspose2d(64*3 + 512, 64, kernel_size=2, stride=2)
            self.up0_2 = nn.ConvTranspose2d(64*2 + 256, 64, kernel_size=2, stride=2)
            self.up0_1 = nn.ConvTranspose2d(64 + 128, 64, kernel_size=2, stride=2)

        # 最终输出层
        self.final_conv = OutConv(64, n_classes)

        # 深度监督输出（可选，训练时可使用）
        self.deep_supervision = True
        if self.deep_supervision:
            self.final_conv0_1 = OutConv(64, n_classes)
            self.final_conv0_2 = OutConv(64, n_classes)
            self.final_conv0_3 = OutConv(64, n_classes)

    def _concat(self, x1, x2):
        """拼接两个tensor，处理维度不匹配问题"""
        diffY = x2.size()[2] - x1.size()[2]
        diffX = x2.size()[3] - x1.size()[3]

        x1 = F.pad(x1, [diffX // 2, diffX - diffX // 2,
                        diffY // 2, diffY - diffY // 2])
        x = torch.cat([x2, x1], dim=1)
        return x

    def forward(self, x):
        # 编码路径
        x0_0 = self.conv0_0(x)
        x1_0 = self.conv1_0(self.pool(x0_0))
        x0_1 = self.conv0_1(self._concat(self.up1_0(x1_0), x0_0))

        x2_0 = self.conv2_0(self.pool(x1_0))
        x1_1 = self.conv1_1(self._concat(self.up2_0(x2_0), x1_0))
        x0_2 = self.conv0_2(self._concat(self.up0_1(x1_1), x0_0))  # 修正：只使用x0_0，不拼接

        x3_0 = self.conv3_0(self.pool(x2_0))
        x2_1 = self.conv2_1(self._concat(self.up3_0(x3_0), x2_0))
        x1_2 = self.conv1_2(self._concat(self.up1_1(x2_1), x1_0))  # 修正：只使用x1_0，不拼接
        x0_3 = self.conv0_3(self._concat(self.up0_2(x1_2), x0_0))  # 修正：只使用x0_0，不拼接

        x4_0 = self.conv4_0(self.pool(x3_0))
        x3_1 = self.conv3_1(self._concat(self.up4_0(x4_0), x3_0))
        x2_2 = self.conv2_2(self._concat(self.up2_1(x3_1), x2_0))  # 修正：只使用x2_0，不拼接
        x1_3 = self.conv1_3(self._concat(self.up1_2(x2_2), x1_0))  # 修正：只使用x1_0，不拼接
        x0_4 = self.conv0_4(self._concat(self.up0_3(x1_3), x0_0))  # 修正：只使用x0_0，不拼接

        if self.deep_supervision:
            # 深度监督模式，返回多个尺度的输出
            output0_1 = self.final_conv0_1(x0_1)
            output0_2 = self.final_conv0_2(x0_2)
            output0_3 = self.final_conv0_3(x0_3)
            output0_4 = self.final_conv(x0_4)

            # 将多个尺度的输出上采样到原始尺寸并取平均
            h, w = x.size()[2:]
            output0_1 = F.interpolate(output0_1, size=(h, w), mode='bilinear', align_corners=True)
            output0_2 = F.interpolate(output0_2, size=(h, w), mode='bilinear', align_corners=True)
            output0_3 = F.interpolate(output0_3, size=(h, w), mode='bilinear', align_corners=True)
            output0_4 = F.interpolate(output0_4, size=(h, w), mode='bilinear', align_corners=True)

            output = (output0_1 + output0_2 + output0_3 + output0_4) / 4
            return output
        else:
            # 标准模式，只返回最终输出
            output = self.final_conv(x0_4)
            return output

    def predict(self, x):
        """预测方法，返回类别编号图，与原UNet保持一致"""
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            probs = torch.softmax(logits, dim=1)
            preds = torch.argmax(probs, dim=1)
            return preds

def get_model(model_type='unet++', deep_supervision=False):
    """获取模型实例，与原UNet接口保持一致"""
    model = NestedUNet(n_channels=IMG_CHANNELS, n_classes=NUM_CLASSES)
    model.deep_supervision = deep_supervision
    return model

def test_model():
    """测试模型，验证与原UNet的输入输出维度一致性"""
    print("测试UNet++模型...")

    device = torch.device(DEVICE)
    model = get_model('unet++', deep_supervision=False).to(device)

    # 创建测试输入（与原UNet测试保持一致）
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

    # 验证与原UNet的输出维度一致性
    expected_shape = (2, NUM_CLASSES, IMG_HEIGHT, IMG_WIDTH)
    if output.shape == expected_shape:
        print("✓ 输出维度与原UNet一致")
    else:
        print(f"✗ 输出维度不匹配，期望: {expected_shape}, 实际: {output.shape}")

    print("UNet++模型测试完成！")

if __name__ == "__main__":
    test_model()