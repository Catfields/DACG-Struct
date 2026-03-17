import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Optional, Tuple


class StructuredDecoderLayer(nn.Module):
    """
    单层非自回归结构化解码器
    实现 Cross-Attention 机制：queries ↔ memory
    """

    def __init__(self, d_model=512, nhead=8, dim_feedforward=2048, dropout=0.1):
        super().__init__()

        self.cross_attn = nn.MultiheadAttention(
            embed_dim=d_model,
            num_heads=nhead,
            dropout=dropout,
            batch_first=True
        )

        self.norm1 = nn.LayerNorm(d_model)
        self.dropout1 = nn.Dropout(dropout)

        self.ffn = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, d_model),
            nn.Dropout(dropout)
        )

        self.norm2 = nn.LayerNorm(d_model)
        self.dropout2 = nn.Dropout(dropout)

    def forward(self, queries: torch.Tensor, memory: torch.Tensor) -> torch.Tensor:
        """
        Args:
            queries: 查询状态 (B, K, D)，可来自 GM 或上一层 decoder
            memory: 编码器输出 (B, M, D)

        Returns:
            decoded_states: (B, K, D) 解码后的语义状态
        """
        attn_out, _ = self.cross_attn(
            query=queries,
            key=memory,
            value=memory
        )

        # Add & Norm
        decoded_states = self.norm1(queries + self.dropout1(attn_out))

        # FFN
        ffn_out = self.ffn(decoded_states)

        # Add & Norm
        decoded_states = self.norm2(decoded_states + self.dropout2(ffn_out))

        return decoded_states


class StructuredDecoder(nn.Module):
    """
    非自回归结构化解码器
    N层 Cross-Attention Decoder
    
    输入：
    - queries: (B, K, D)，第一层来自 GM 输出
    - memory:  (B, M, D)
    
    输出：
    - Z ∈ R^{B×K×D}，每个查询的语义表示
    """
    
    def __init__(self, d_model=512, nhead=8, num_layers=1,
                 dim_feedforward=2048, dropout=0.1):
        super().__init__()
        
        self.d_model = d_model
        self.num_layers = num_layers
        
        self.layers = nn.ModuleList([
            StructuredDecoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=dim_feedforward,
                dropout=dropout
            )
            for _ in range(num_layers)
        ])
        
        self.final_norm = nn.LayerNorm(d_model)
        
    def forward(self, queries: torch.Tensor, memory: torch.Tensor) -> torch.Tensor:
        assert queries.dim() == 3, \
            f"queries 应为 (B, K, D)，但得到 {queries.shape}"
        assert memory.dim() == 3, \
            f"memory 应为 (B, M, D)，但得到 {memory.shape}"
        assert queries.size(-1) == memory.size(-1) == self.d_model, \
            f"特征维度不匹配: queries={queries.size(-1)}, memory={memory.size(-1)}, d_model={self.d_model}"
        
        x = queries
        for layer in self.layers:
            x = layer(x, memory)
        
        Z = self.final_norm(x)
        return Z


# class DiseaseQueryGenerator(nn.Module):
#     """
#     疾病查询生成器
#     为每个疾病创建可学习的查询向量
#     """
    
#     def __init__(self, d_model: int, num_diseases: int, dropout: float = 0.1):
#         super().__init__()
        
#         self.d_model = d_model
#         self.num_diseases = num_diseases
        
#         # 为每个疾病创建可学习的查询向量
#         self.disease_queries = nn.Parameter(
#             torch.randn(num_diseases, d_model) * 0.1
#         )
        
#         self.dropout = nn.Dropout(dropout)
        
#     def forward(self, batch_size: int) -> torch.Tensor:
#         """
#         生成疾病查询向量
        
#         Args:
#             batch_size: 批次大小
            
#         Returns:
#             queries: 疾病查询 (B, Q, D)
#         """
#         # 扩展到批次大小
#         queries = self.disease_queries.unsqueeze(0).expand(batch_size, -1, -1)
#         queries = self.dropout(queries)
        
#         return queries


# class StructuredDecoderWithClassifier(nn.Module):
#     """
#     完整的结构化解码器（包含多分类头）
#     这个类将解码器和多分类头组合在一起

#     支持 disease-specific location head
#     """

#     def __init__(self,
#                  d_model: int = 512,
#                  num_diseases: int = 16,
#                  probability_levels: int = 3,
#                  severity_levels: int = 4,
#                  nhead: int = 8,
#                  num_layers: int = 1,
#                  dim_feedforward: int = 2048,
#                  dropout: float = 0.1,
#                  location_vocab_size: Optional[int] = None,
#                  disease_vocab_sizes: Optional[Dict[str, int]] = None,
#                  disease_order: Optional[List[str]] = None):
#         """
#         Args:
#             d_model: 模型特征维度
#             num_diseases: 疾病数量
#             probability_levels: 概率等级数
#             severity_levels: 严重程度等级数
#             nhead: 注意力头数
#             num_layers: 解码器层数
#             dim_feedforward: 前馈网络维度
#             dropout: dropout率
#             location_vocab_size: 标准 location head 的 vocab_size（向后兼容）
#             disease_vocab_sizes: disease-specific 的 vocab_size（新推荐）
#             disease_order: 疾病顺序列表（必须与 disease_order.json 一致）
#         """
#         super().__init__()

#         self.d_model = d_model
#         self.num_diseases = num_diseases
#         self.probability_levels = probability_levels
#         self.severity_levels = severity_levels

#         # 初始化查询生成器
#         self.query_generator = DiseaseQueryGenerator(
#             d_model=d_model,
#             num_diseases=num_diseases,
#             dropout=dropout
#         )

#         # 初始化结构化解码器
#         self.decoder = StructuredDecoder(
#             d_model=d_model,
#             nhead=nhead,
#             num_layers=num_layers,
#             dim_feedforward=dim_feedforward,
#             dropout=dropout
#         )

#         # 导入多分类头
#         from modules.multi_head_classifier import MultiHeadClassifier

#         # 初始化多分类头（支持两种模式）
#         use_disease_specific = disease_vocab_sizes is not None and disease_order is not None

#         if use_disease_specific:
#             print("✅ StructuredDecoderWithClassifier 使用 DiseaseSpecificLocationHead")
#             self.classifier = MultiHeadClassifier(
#                 d_model=d_model,
#                 num_diseases=num_diseases,
#                 probability_levels=probability_levels,
#                 severity_levels=severity_levels,
#                 disease_vocab_sizes=disease_vocab_sizes,
#                 disease_order=disease_order
#             )
#             self.num_locations = self.classifier.location_vocab_size
#         else:
#             if location_vocab_size is None:
#                 raise ValueError(
#                     "必须提供 location_vocab_size 或 (disease_vocab_sizes + disease_order)"
#                 )
#             print(f"⚠️  StructuredDecoderWithClassifier 使用标准 LocationHead (vocab_size={location_vocab_size})")
#             self.classifier = MultiHeadClassifier(
#                 d_model=d_model,
#                 num_diseases=num_diseases,
#                 probability_levels=probability_levels,
#                 severity_levels=severity_levels,
#                 location_vocab_size=location_vocab_size
#             )
#             self.num_locations = location_vocab_size
        
#     def forward(self, memory: torch.Tensor, GM_t: Optional[torch.Tensor] = None) -> Dict[str, torch.Tensor]:
#         """
#         结构化解码器前向传播

#         Args:
#             memory: 编码器记忆 (B, M, D)
#             GM_t: 引导记忆 (B, Q, D)，可选（GM生成器输出的调制后的queries）

#         Returns:
#             包含疾病语义表示和分类预测的字典
#         """
#         batch_size = memory.size(0)

#         # 生成疾病查询
#         queries = self.query_generator(batch_size)  # (B, Q, D)

#         # 如果提供了引导记忆（GM生成的调制queries），则使用它
#         if GM_t is not None:
#             # GM_t 形状: (B, Q, D)，直接使用
#             queries = GM_t + queries

#         # 结构化解码
#         disease_features = self.decoder(queries, memory)  # (B, Q, D)

#         # 多分类预测
#         classifier_output = self.classifier(disease_features)

#         # 添加疾病特征到输出中
#         classifier_output['disease_features'] = disease_features

#         return classifier_output


