import math
import torch
import torch.nn as nn
import torch.nn.functional as F


class PAB(nn.Module):
    """
    Patch Attention Branch (PAB) for computing Spatial Attention Graph (SAG)
    
    医学图像空间注意力图计算模块，基于补丁特征计算位置间的注意力权重
    """
    
    def __init__(self):
        super(PAB, self).__init__()
        # 可学习缩放参数alpha，初始化为1，控制空间注意力增强强度
        self.alpha = nn.Parameter(torch.tensor(1.0))
    
    def forward(self, A, alpha=None):
        """
        完整的PAB前向传播，包含SAG计算和特征增强
        
        Args:
            A (torch.Tensor): 医学图像补丁特征，维度为 (M, C)
                             M = H * W 是补丁总数，C 是特征通道数
            alpha (torch.Tensor, optional): 可学习参数，默认为None
        
        Returns:
            E (torch.Tensor): 增强后的特征，形状为 (M, C)
            SAG (torch.Tensor): 空间注意力图，形状为 (M, M)
        """
        # 使用可学习参数alpha（允许外部覆盖）
        if alpha is None:
            alpha = self.alpha
        # 确保数值稳定性：在半精度环境下先转换到float32再计算
        orig_dtype = A.dtype
        A_float = A.float()
        alpha = alpha.to(device=A.device, dtype=A_float.dtype)

        # 获取维度信息
        M, C = A_float.shape
        scaling = 1.0 / math.sqrt(max(C, 1))
        # 计算空间注意力图 (SAG)
        SAG = torch.einsum('mc,nc->mn', A_float, A_float) * scaling
        SAG = F.softmax(SAG, dim=-1)
        # 根据公式 (3) 及文字描述，计算最终输出特征 E
        # D = A.t() 对应 'cm'
        # temp1 = D @ SAG 对应 'cm,mn->cn'
        # temp2 = temp1.t() 对应 'nc'
        # E = temp2 * alpha + A
        # (M, C), (M, M) -> (M, C)
        E_float = torch.einsum('mc,mn->nc', A_float, SAG) * alpha + A_float
        return E_float.to(orig_dtype)

    def extra_repr(self):
        return f'alpha={self.alpha.item():.4f}'


class CAB(nn.Module):
    """
    通道注意力模块 (Channel Attention Block)
    实现通道间的注意力机制，增强重要通道的特征表示
    """
    def __init__(self):
        super(CAB, self).__init__()
        # 可学习参数beta，初始化为1，训练中自动更新
        self.beta = nn.Parameter(torch.tensor(1.0))
    def forward(self, A):
        """
        通道注意力前向传播
        Args:
            A (torch.Tensor): 原始补丁特征，形状为 (M, C)
                             M = H * W 是补丁总数，C 是通道数
        
        Returns:
            E (torch.Tensor): 融合通道注意力后的特征，形状为 (M, C)
            CAG (torch.Tensor): 通道注意力图，形状为 (C, C)
        """
        # 确保数值稳定性：在半精度环境下先转换到float32再计算
        orig_dtype = A.dtype
        A_float = A.float()
        
        # 确保beta参数在正确的设备上
        beta = self.beta.to(A.device)

        # 获取维度信息
        M, C = A_float.shape
        # 步骤1: 计算通道注意力图 CAG
        # 公式4: CAG = softmax(A^T @ A)
        # 转置A得到pmt_A: (M, C) -> (C, M)
        pmt_A = A_float.t()  # pmt_A: (C, M)
        # 计算交互: pmt_A @ A = (C, M) @ (M, C) = (C, C)
        interaction = torch.matmul(pmt_A, A_float)  # interaction: (C, C)
        # 通过softmax归一化得到CAG
        CAG = F.softmax(interaction, dim=-1)  # CAG: (C, C)
        # 步骤2: 计算融合特征E
        # 公式5: E = A + beta * (CAG @ A^T)^T
        # 转置A得到D: (M, C) -> (C, M)
        D = A_float.t()  # D: (C, M)
        # CAG @ D = (C, C) @ (C, M) = (C, M)
        temp = torch.matmul(CAG, D)  # temp: (C, M)
        # 转置结果: (C, M) -> (M, C)
        temp_t = temp.t()  # temp_t: (M, C)
        # 与beta相乘后与原始A相加
        E_float = A_float + beta * temp_t  # E: (M, C)
        return E_float.to(orig_dtype)

    def extra_repr(self):
        return f'beta={self.beta.item():.4f}'


class DualAttention(nn.Module):
    """
    双注意力模块 (Dual Attention Block)
    结合位置注意力模块(PAB)和通道注意力模块(CAB)，实现空间和通道维度的双重注意力机制
    """
    
    def __init__(self):
        super(DualAttention, self).__init__()
        # 实例化位置注意力模块
        self.pab = PAB()
        # 实例化通道注意力模块
        self.cab = CAB()
    
    def _forward_single(self, A):
        """
        单个样本的双注意力前向传播（原有逻辑）
        
        Args:
            A (torch.Tensor): 输入特征，形状为 (M, C)
                             M = H * W 是补丁总数，C 是通道数
        
        Returns:
            output (torch.Tensor): 双注意力融合后的特征，形状为 (M, C)
        """
        # 位置注意力模块前向传播
        E_p = self.pab(A)
        
        # 通道注意力模块前向传播
        E_c = self.cab(A)
        
        # 双注意力融合：output = E_p + E_c
        output = E_p + E_c
        
        return output
    
    def forward(self, A):
        """
        支持batch维度的双注意力前向传播
        
        Args:
            A (torch.Tensor): 输入特征，形状为 (B, M, C) 或 (M, C)
                             B = 批次大小，M = H * W 是补丁总数，C 是通道数
        
        Returns:
            output (torch.Tensor): 双注意力融合后的特征，形状为 (B, M, C) 或 (M, C)
        """
        if A.dim() == 2:
            # 单样本模式 (M, C)
            return self._forward_single(A)
        elif A.dim() == 3:
            # 批次模式 (B, M, C)
            batch_size = A.size(0)
            outputs = []
            for i in range(batch_size):
                output = self._forward_single(A[i])  # (M, C)
                outputs.append(output)
            return torch.stack(outputs, dim=0)  # (B, M, C)
        else:
            raise ValueError(f"不支持的输入维度: {A.dim()}，期望2或3维")
    
    def extra_repr(self):
        return f'PAB: {self.pab.extra_repr()}, CAB: {self.cab.extra_repr()}'


# 测试代码
if __name__ == "__main__":
    # 测试PAB模块
    batch_size = 64
    M = 49  # 7x7 patches
    C = 2048  # feature channels
    
    # 创建测试数据
    A = torch.randn(M, C)
    alpha = torch.tensor(0.5, device=A.device, dtype=A.dtype)
    
    # 创建PAB实例
    pab = PAB()
    
    # 计算增强特征和SAG
    E = pab(A, alpha=alpha)
    
    print(f"输入特征A形状: {A.shape}")
    print(f"增强特征E形状: {E.shape}")
   
    
    # 测试批次处理
    A_batch = torch.randn(batch_size, M, C)
    alpha_batch = torch.tensor(0.5, device=A_batch.device, dtype=A_batch.dtype)
    # 对批次中的每个样本单独计算
    E_batch = [pab(A_batch[i], alpha=alpha_batch) for i in range(batch_size)]
    E_batch = torch.stack(E_batch)
    print(f"批次增强特征E形状: {E_batch.shape}")


    # Test CAB class
    print("\n" + "="*50)
    print("Testing CAB (Channel Attention Block)")
    print("="*50)
    
    cab_model = CAB()
    print(f"CAB initial beta: {cab_model.beta.item():.4f}")
    
    # 测试CAB
    E_cab = cab_model(A)
    print("CAB enhanced features shape:", E_cab.shape)
    
    
    # 测试批次处理
    print("\nTesting CAB with batch processing...")
    E_cab_batch = [cab_model(A_batch[i]) for i in range(batch_size)]
    E_cab_batch = torch.stack(E_cab_batch)
    print(f"批次CAB增强特征形状: {E_cab_batch.shape}")

    
    # 测试DualAttention类
    print("\n" + "="*50)
    print("Testing DualAttention (Dual Attention Block)")
    print("="*50)
    
    dual_attention = DualAttention()
    print(f"DualAttention: {dual_attention}")
    
    # 测试双注意力模块
    output= dual_attention(A)
    print("DualAttention output shape:", output.shape)

    
    
    # 测试批次处理
    print("\nTesting DualAttention with batch processing...")
    output_batch = [dual_attention(A_batch[i]) for i in range(batch_size)]
    output_batch = torch.stack(output_batch)
    print(f"批次DualAttention输出形状: {output_batch.shape}")
