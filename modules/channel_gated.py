import torch
import torch.nn as nn
import torch.nn.functional as F


class ChannelGatedFusion(nn.Module):
    """
    区域内通道级门控融合模块
    对单个区域的全局特征和区域特征进行通道级门控融合
    """
    
    def __init__(self, feature_dim):
        """
        Args:
            feature_dim (int): 特征维度 D
        """
        super(ChannelGatedFusion, self).__init__()
        self.feature_dim = feature_dim
        
        # MLP用于生成通道级门控：输入D，输出D
        self.gate_mlp = nn.Sequential(
            nn.Linear(feature_dim, feature_dim*2),
            nn.ReLU(),
            nn.Linear(feature_dim*2, feature_dim),
            nn.Sigmoid()
        )
        
    def forward(self, global_feat, region_feat):
        """
        Args:
            global_feat: 全局特征 (B, M, D)
            region_feat: 区域特征 (B, M, D)
            
        Returns:
            fused_feat: 融合后的区域特征 (B, M, D)
        """
        # 计算通道级summary：mean_tokens
        gV = torch.mean(global_feat, dim=1)  # (B, D)
        gR = torch.mean(region_feat, dim=1)  # (B, D)
        
        # 全局和区域summary求和
        sum = gV + gR  # (B, D)
        
        # 通过MLP + Sigmoid生成通道级门控
        gate = self.gate_mlp(sum)  # (B, D)
        
        # 广播门控到token维度
        gate_expanded = gate.unsqueeze(1).expand(-1, global_feat.size(1), -1)  # (B, M, D)
        
        # 软融合：F_k = g_k ⊙ V̂ + (1 - g_k) ⊙ R_k
        fused_feat = gate_expanded * global_feat + (1 - gate_expanded) * region_feat
        
        return fused_feat


class RegionWiseChannelGatedFusion(nn.Module):
    """
    区域内通道级门控融合模块
    对4个区域分别进行通道级门控融合
    """
    
    def __init__(self, feature_dim=512, num_regions=4):
        """
        Args:
            feature_dim (int): 特征维度 D
            num_regions (int): 区域数量，默认为4（左肺/右肺/心脏/背景）
        """
        super(RegionWiseChannelGatedFusion, self).__init__()
        self.feature_dim = feature_dim
        self.num_regions = num_regions
        
        # 为每个区域创建独立的门控融合模块
        self.region_fusion_modules = nn.ModuleList([
            ChannelGatedFusion(feature_dim) for _ in range(num_regions)
        ])
        
    def forward(self, refined_global_feat, region_feats_list):
        """
        Args:
            refined_global_feat: 精炼后的全局特征 (B, M, D)
            region_feats_list: 4个区域特征的列表 [(B, M, D), ...]
            
        Returns:
            fused_region_feats: 4组门控后的区域特征列表 [(B, M, D), ...]
        """
        assert len(region_feats_list) == self.num_regions, \
            f"期望{self.num_regions}个区域特征，但收到了{len(region_feats_list)}个"
        
        fused_region_feats = []
        
        # 对每个区域进行门控融合
        for i, region_feat in enumerate(region_feats_list):
            fused_feat = self.region_fusion_modules[i](refined_global_feat, region_feat)
            fused_region_feats.append(fused_feat)
            
        return fused_region_feats
    
    def extra_repr(self):
        return f'feature_dim={self.feature_dim}, num_regions={self.num_regions}'


# 测试代码
if __name__ == "__main__":
    # 设置随机种子以确保可重复性
    torch.manual_seed(42)
    
    # 测试参数
    batch_size = 2
    num_patches = 49  # 7x7 patches
    feature_dim = 512
    
    print("="*60)
    print("测试Region-wise Channel-Gated Fusion模块")
    print("="*60)
    
    # 创建测试数据
    refined_global_feat = torch.randn(batch_size, num_patches, feature_dim)
    region_feats_list = [
        torch.randn(batch_size, num_patches, feature_dim) 
        for _ in range(4)
    ]
    
    print(f"精炼全局特征形状: {refined_global_feat.shape}")
    print(f"区域特征列表长度: {len(region_feats_list)}")
    for i, feat in enumerate(region_feats_list):
        print(f"区域 {i+1} 特征形状: {feat.shape}")
    
    # 创建融合模块
    fusion_module = RegionWiseChannelGatedFusion(feature_dim)
    print(f"\n融合模块配置: {fusion_module.extra_repr()}")
    
    # 前向传播
    fused_feats = fusion_module(refined_global_feat, region_feats_list)
    
    print(f"\n融合后特征列表长度: {len(fused_feats)}")
    for i, feat in enumerate(fused_feats):
        print(f"融合区域 {i+1} 特征形状: {feat.shape}")
    
    # 验证输出维度正确性
    expected_shape = (batch_size, num_patches, feature_dim)
    for i, feat in enumerate(fused_feats):
        assert feat.shape == expected_shape, \
            f"区域 {i+1} 输出形状错误: 期望 {expected_shape}, 实际 {feat.shape}"
    
    print("\n✅ 所有维度验证通过!")
    
    # 测试门控机制的直观性
    print("\n" + "="*60)
    print("测试门控机制的直观性")
    print("="*60)
    
    # 创建一个人为设计的测试案例
    test_global = torch.ones(batch_size, num_patches, feature_dim)  # 全局特征全1
    test_region1 = torch.zeros(batch_size, num_patches, feature_dim)  # 区域1特征全0（无信息）
    test_region2 = torch.ones(batch_size, num_patches, feature_dim) * 2  # 区域2特征全2（强信息）
    
    # 测试只有两个区域
    test_fusion = ChannelGatedFusion(feature_dim)
    
    # 区域1：无信息情况，应该更依赖全局特征
    fused1 = test_fusion(test_global, test_region1)
    print(f"区域1（无信息）- 融合特征范围: [{fused1.min().item():.3f}, {fused1.max().item():.3f}]")
    
    # 区域2：强信息情况，应该更依赖区域特征
    fused2 = test_fusion(test_global, test_region2)
    print(f"区域2（强信息）- 融合特征范围: [{fused2.min().item():.3f}, {fused2.max().item():.3f}]")
    
    print("\n门控机制测试完成!")
    print("Region-wise Channel-Gated Fusion模块测试通过！🎉")
