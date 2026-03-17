import torch
import torch.nn as nn

class PartitionModule(nn.Module):
    """
    分区模块
    将原始图像与4种二进制掩膜依次做哈达玛积，得到5张分区图像
    注意：这里只是进行分区处理，暂未进行特征融合
    """
    
    def __init__(self):
        super(PartitionModule, self).__init__()
        
    def forward(self, original_image, binary_masks):
        """
        Args:
            original_image: 原始图像 (B, C, H, W)
            binary_masks: 4种二进制掩膜 (B, 4, H, W)
        
        Returns:
            partitioned_images: 5张分区图像列表 [(B, C, H, W), ...]
        """
        partitioned_images = [original_image]  # 第一张是原始图像
        
        # 原始图像与每种掩膜做哈达玛积
        for i in range(binary_masks.size(1)):
            mask = binary_masks[:, i:i+1, :, :]  # (B, 1, H, W)
            # 广播掩膜到与图像相同的通道数
            mask_expanded = mask.expand(-1, original_image.size(1), -1, -1)
            # 哈达玛积（逐元素相乘）
            partitioned_result = original_image * mask_expanded
            partitioned_images.append(partitioned_result)
            
        return partitioned_images


# 为了向后兼容，保留别名
HadamardFusion = PartitionModule


# 测试代码
if __name__ == "__main__":
    # 测试分区模块
    partition_module = PartitionModule()
    
    # 模拟输入
    batch_size = 2
    channels = 3
    height = 224
    width = 224
    
    original_image = torch.randn(batch_size, channels, height, width)
    binary_masks = torch.randint(0, 2, (batch_size, 4, height, width)).float()
    
    # 前向传播
    partitioned_images = partition_module(original_image, binary_masks)
    
    print(f"原始图像形状: {original_image.shape}")
    print(f"二进制掩膜形状: {binary_masks.shape}")
    print(f"分区后图像数量: {len(partitioned_images)}")
    for i, img in enumerate(partitioned_images):
        print(f"分区图像 {i} 形状: {img.shape}")
    
    print("分区模块测试通过！")