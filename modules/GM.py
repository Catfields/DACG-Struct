import torch
import torch.nn as nn
import torch.nn.functional as F


class GM_Generator(nn.Module):
    """
    引导记忆生成器 (Guided Memory Generator)

    变化点：
    - Q_init 不再是 nn.Parameter（不交给优化器），而是一个 buffer（模型状态）
    - 在 forward(train) 中用当前 batch 产生的 Q_guided 的均值来原地更新 Q_init（EMA）
    """

    def __init__(self, hidden_dim=512, num_queries=16, dropout=0.1, ema_momentum=0.01):
        super(GM_Generator, self).__init__()
        self.hidden_dim = hidden_dim
        self.num_queries = num_queries
        self.ema_momentum = float(ema_momentum)

        # 两层 MLP：hidden_dim -> hidden_dim -> 2*hidden_dim
        self.film_mlp = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim * 2),
            nn.Dropout(dropout),
        )

        # 用 buffer 保存“持续更新”的 Q_init（不走 optimizer）
        q = torch.empty(num_queries, hidden_dim)
        nn.init.xavier_uniform_(q)
        self.register_buffer("Q_init", q)  # (K, D)

    @torch.no_grad()
    def _update_q_init(self, Q_guided: torch.Tensor):
        """
        使用当前 batch 的 Q_guided 均值来更新 Q_init（EMA 原地更新）
        Q_guided: (B, K, D)
        """
        # (K, D)
        q_new = Q_guided.mean(dim=0)

        m = self.ema_momentum
        # EMA: Q_init <- (1-m)*Q_init + m*q_new
        self.Q_init.mul_(1.0 - m).add_(q_new, alpha=m)

    def forward(self, V_fused: torch.Tensor) -> torch.Tensor:
        assert V_fused.dim() == 3
        B, M, D = V_fused.shape
        assert D == self.hidden_dim

        u = V_fused.mean(dim=1)
        film_params = self.film_mlp(u)
        gamma, beta = film_params.chunk(2, dim=-1)
        gamma = gamma.unsqueeze(1)
        beta = beta.unsqueeze(1)

        # 用 Q_init 的“快照”参与本次计算，避免后面原地更新影响计算图
        Q_init_snapshot = self.Q_init.detach().clone()   # (K, D) 不进图 + 独立存储
        Q_init_batch = Q_init_snapshot.unsqueeze(0).expand(B, -1, -1)

        Q_guided = gamma * Q_init_batch + beta

        # 更新用 detach 的结果，且放在不影响图的路径上
        if self.training and self.ema_momentum > 0:
            self._update_q_init(Q_guided.detach())

        return Q_guided


