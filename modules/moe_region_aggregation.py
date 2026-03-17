import torch
import torch.nn as nn
import torch.nn.functional as F


class MoERegionAggregation(nn.Module):
    """
    MoE风格的区域间聚合模块
    将4个区域当作4个expert，通过softmax权重加权求和
    """
    
    def __init__(self, feature_dim=512, num_regions=4):
        """
        Args:
            feature_dim (int): 特征维度 D
            num_regions (int): 区域数量，默认为4
        """
        super(MoERegionAggregation, self).__init__()
        self.feature_dim = feature_dim
        self.num_regions = num_regions
        
        # 每个区域的routing score生成器: D -> 1
        self.routing_linears = nn.ModuleList([
            nn.Linear(feature_dim, 1) for _ in range(num_regions)
        ])
        
    def forward(self, region_feats_list):
        """
        Args:
            region_feats_list: 4个门控区域特征列表 [(B, M, D), ...]
            
        Returns:
            V_fused: 融合后的视觉token序列 (B, M, D)
            routing_weights: routing权重 (B, 4)
            region_vectors: 每个区域的向量表示 h_k (B, 4, D)
        """
        assert len(region_feats_list) == self.num_regions, \
            f"期望{self.num_regions}个区域特征，但收到了{len(region_feats_list)}个"
        
        B, M, D = region_feats_list[0].shape
        
        # 1. 计算每个区域的routing score
        scores = []
        region_vectors = []  # 存储每个区域的向量表示
        for i, F_k in enumerate(region_feats_list):
            h_k = F_k.mean(dim=1)  # (B, D) token平均
            s_k = self.routing_linears[i](h_k)  # (B, 1)
            scores.append(s_k)
            region_vectors.append(h_k)
        
        # 2. softmax得到权重
        scores = torch.cat(scores, dim=-1)  # (B, 4)
        routing_weights = F.softmax(scores, dim=-1)  # (B, 4)
        region_vectors = torch.stack(region_vectors, dim=1)  # (B, 4, D)
        
        # 3. 广播权重并加权求和
        V_fused = torch.zeros(B, M, D, device=region_feats_list[0].device)
        for i, F_k in enumerate(region_feats_list):
            a_k = routing_weights[:, i:i+1].unsqueeze(-1)  # (B, 1, 1)
            V_fused = V_fused + a_k * F_k  # (B, M, D)
        
        return V_fused, routing_weights, region_vectors
    
    def extra_repr(self):
        return f'feature_dim={self.feature_dim}, num_regions={self.num_regions}'


