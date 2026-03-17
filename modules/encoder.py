"""
V_fused_Encoder 模块
专门处理 V_fused 的标准 Transformer Encoder

该模块接收来自 MoE Region Aggregation 的融合特征 V_fused (B, M, d_model)，
通过标准 Transformer Encoder 层处理，输出编码后的 memory (B, M, d_model)。

特性:
- 相对位置编码 (max_length=512)
- 标准 Multi-Head Self-Attention
- Feed Forward Network with 残差连接
- 可配置层数（默认1层）
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import math

class AbsolutePositionalEncoding(nn.Module):
    """
    绝对位置编码 - 用于为序列中的每个位置提供唯一的位置信息
    
    绝对位置编码通过为序列中每一个固定位置分配一个独立的向量，
    显式地建模“当前位置是第几个 token / patch”。
    常用于 Transformer 中的文本和视觉序列建模。
    """
    def __init__(self, d_model, max_length=512):
        super(AbsolutePositionalEncoding, self).__init__()
        self.d_model = d_model
        self.max_length = max_length
        
        # 创建绝对位置编码矩阵 (max_length, d_model)
        # 每一个位置都有一个独立、可学习的向量
        self.position_embedding = nn.Parameter(
            torch.randn(max_length, d_model)
        )
        nn.init.xavier_uniform_(self.position_embedding)
        
    def forward(self, seq_len):
        """
        生成当前序列长度对应的绝对位置编码
        
        Args:
            seq_len: 序列长度 M
        
        Returns:
            pos_emb: (1, seq_len, d_model) 位置编码
        """
        # 确保 seq_len 不超过 max_length
        seq_len = min(seq_len, self.max_length)
        
        # 取前 seq_len 个位置的编码
        pos_emb = self.position_embedding[:seq_len]  # (seq_len, d_model)
        pos_emb = pos_emb.unsqueeze(0)  # (1, seq_len, d_model)
        
        return pos_emb
class RelativePositionalEncoding(nn.Module):
    """
    相对位置编码 - 专门用于视觉特征的序列位置建模
    
    相比绝对位置编码，相对位置编码在长序列和视觉任务中表现更好。
    能够更好地处理不同长度的序列，并捕捉序列元素间的相对位置关系。
    """
    def __init__(self, d_model, max_length=512):
        super(RelativePositionalEncoding, self).__init__()
        self.d_model = d_model
        self.max_length = max_length
        
        # 创建相对位置偏置矩阵 (2*max_length-1, d_model)
        # 用于建模序列中任意两个位置之间的相对距离
        self.relative_bias = nn.Parameter(torch.randn(2 * max_length - 1, d_model))
        nn.init.xavier_uniform_(self.relative_bias)
        
    def forward(self, seq_len):
        """
        生成当前序列长度对应的相对位置偏置
        
        Args:
            seq_len: 序列长度 M
        
        Returns:
            pos_bias: (1, seq_len, d_model) 位置偏置
        """
        # 确保 seq_len 不超过 max_length
        seq_len = min(seq_len, self.max_length)
        
        # 从相对位置矩阵中提取当前序列长度对应的偏置
        # 对于长度为 seq_len 的序列，我们需要 seq_len 个位置编码
        # 简单地使用前 seq_len 个编码（可以优化为更复杂的相对位置逻辑）
        bias = self.relative_bias[:seq_len]  # (seq_len, d_model)
        bias = bias.unsqueeze(0)  # (1, seq_len, d_model)
        
        return bias


class EncoderLayer(nn.Module):
    """
    标准 Transformer Encoder 层
    
    包含:
    - Multi-Head Self-Attention
    - Feed Forward Network  
    - 残差连接和层归一化
    - Dropout 正则化
    """
    def __init__(self, d_model=512, num_heads=8, d_ff=2048, dropout=0.1):
        super(EncoderLayer, self).__init__()
        self.d_model = d_model
        
        # Multi-Head Self-Attention
        self.self_attention = nn.MultiheadAttention(
            embed_dim=d_model,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True
        )
        
        # Feed Forward Network
        self.feed_forward = nn.Sequential(
            nn.Linear(d_model, d_ff),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d_ff, d_model)
        )
        
        # Layer Norm 和 Dropout
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)
        
    def forward(self, x):
        """
        前向传播
        
        Args:
            x: 输入序列 (B, M, d_model)
        
        Returns:
            输出序列 (B, M, d_model)
        """
        # Self-Attention + 残差连接
        attn_output, attn_weights = self.self_attention(x, x, x)
        x = self.norm1(x + self.dropout(attn_output))
        
        # Feed Forward + 残差连接
        ff_output = self.feed_forward(x)
        x = self.norm2(x + self.dropout(ff_output))
        
        return x


class V_fused_Encoder(nn.Module):
    """
    专门处理 V_fused 的标准 Transformer Encoder
    
    输入: V_fused (B, M, d_model) - 已包含多区域融合和Dual Attention信息
    输出: memory (B, M, d_model) - 标准 Transformer Encoder 编码后的特征
    
    架构:
    1. 绝对位置编码添加
    2. N层标准 Transformer Encoder Layer (默认1层)
    3. 最终层归一化
    """
    def __init__(self, d_model=512, num_layers=1, num_heads=8, d_ff=2048, dropout=0.1, max_length=512):
        super(V_fused_Encoder, self).__init__()
        self.d_model = d_model
        self.num_layers = num_layers
        
        # 绝对位置编码 (max_length 默认512，可配置)
        self.absolute_pos_encoding = AbsolutePositionalEncoding(d_model, max_length=max_length)
        
        # 标准 Transformer Encoder 层
        self.layers = nn.ModuleList([
            EncoderLayer(d_model, num_heads, d_ff, dropout)
            for _ in range(num_layers)
        ])
        
        # 最终层归一化
        self.final_layer_norm = nn.LayerNorm(d_model)
        
        # Dropout
        self.dropout = nn.Dropout(dropout)
        
    def forward(self, V_fused):
        """
        前向传播
        
        Args:
            V_fused: 融合后的视觉特征 (B, M, d_model)
                     B: 批次大小, M: 补丁数, d_model: 特征维度
        
        Returns:
            memory: 编码器输出 (B, M, d_model)
        """
        batch_size, seq_len, d_model = V_fused.shape
        
        # 添加绝对位置编码
        pos_emb = self.absolute_pos_encoding(seq_len)  # (1, seq_len, d_model)
        x = V_fused + pos_emb  # (B, M, d_model)
        x = self.dropout(x)
        
        # 通过 N 层标准 Transformer Encoder
        for layer in self.layers:
            x = layer(x)
        
        # 最终层归一化
        x = self.final_layer_norm(x)
        
        return x  # memory: (B, M, d_model)
    
    def extra_repr(self):
        """返回模块的额外表示信息"""
        num_heads = self.layers[0].self_attention.num_heads if self.layers else 0
        return f'd_model={self.d_model}, num_layers={self.num_layers}, num_heads={num_heads}'
