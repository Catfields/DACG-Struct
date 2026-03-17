"""
DACG模型训练器
实现完整的训练、验证、测试逻辑
基于structured_model.py和structured_loss.py
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torch.cuda.amp import GradScaler, autocast
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import os
import json
import time
from pathlib import Path

# 导入模型和损失函数
from project.model import DACGModel, DACGModelConfig
from modules.structured_loss import compute_structured_loss
from modules.s_score_evaluator import SScoresEvaluator


@dataclass
class TrainerConfig:
    """训练器配置类"""
    # 基础训练参数
    learning_rate: float = 1e-4
    weight_decay: float = 1e-5
    warmup_epochs: int = 5
    max_grad_norm: float = 1.0
    
    # 损失权重
    loss_weights: Dict[str, float] = field(default_factory=lambda: {
        'mention_loss': 1.0,
        'polarity_loss': 1.0,
        'probability_loss': 1.0,
        'severity_loss': 1.0,
        'location_loss': 1.0
    })
    
    # 训练控制
    num_epochs: int = 100
    save_interval: int = 5
    eval_interval: int = 1
    log_interval: int = 50
    
    # 保存和日志
    save_dir: str = './checkpoints'
    log_dir: str = './logs'
    experiment_name: str = 'dacg_experiment'
    
    # 设备和优化
    device: str = 'cuda' if torch.cuda.is_available() else 'cpu'
    use_amp: bool = True
    num_workers: int = 4
    
    # S-Score评估配置
    enable_s_score: bool = True              # 是否启用S-Score评估
    s_score_interval: int = 1               # S-Score评估间隔（每几个epoch评估一次）
    s_score_threshold: float = 0.3           # 疾病存在性判断阈值
    s_score_weights: Dict[str, float] = field(default_factory=lambda: {
        'p_weight': 0.5,                    # P-Score权重
        'd_weight': 0.5                      # D-Score权重
    })
    save_best_s_score: bool = True           # 是否根据S-Score保存最佳模型
    
    # 早停
    patience: int = 10
    min_delta: float = 1e-4


class DACGTrainer:
    """
    DACG模型训练器
    
    支持完整的训练流程：
    - 数据格式转换
    - 多任务损失计算
    - 梯度裁剪和混合精度训练
    - 验证和早停
    - 检查点管理
    """
    
    def __init__(
        self,
        model: DACGModel,
        train_loader: DataLoader,
        val_loader: DataLoader,
        config: TrainerConfig,
        disease_list: List[str],
        test_loader: Optional[DataLoader] = None
    ):
        """
        初始化训练器
        
        Args:
            model: DACG模型实例
            train_loader: 训练数据加载器
            val_loader: 验证数据加载器
            config: 训练配置
            disease_list: 疾病词汇表
            test_loader: 测试数据加载器（可选）
        """
        self.model = model
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.test_loader = test_loader
        self.config = config
        self.disease_list = disease_list
        
        # 设备管理
        self.device = torch.device(config.device)
        self.model.to(self.device)
        
        # 构建映射字典
        self.severity_to_id = self._build_severity_mapping()
        self.location_to_id = self._build_location_mapping()
        
        # 优化器和调度器
        self.optimizer = self._build_optimizer()
        self.scheduler = self._build_scheduler()
        
        # 混合精度训练
        self.use_amp = config.use_amp and self.device.type == 'cuda'
        self.scaler = GradScaler() if self.use_amp else None
        
        # 训练状态
        self.current_epoch = 0
        self.best_val_loss = float('inf')
        self.epochs_without_improvement = 0
        
        # S-Score评估器
        self.s_score_evaluator = None
        if config.enable_s_score:
            self.s_score_evaluator = SScoresEvaluator(
                disease_list=self.disease_list,
                location_mapper=self._create_location_mapper()
            )
        
        # S-Score历史记录
        self.best_s_score = 0.0
        self.best_p_score = 0.0
        self.best_d_score = 0.0
        
        self.training_history = {
            'train_loss': [],
            'val_loss': [],
            'train_metrics': [],
            'val_metrics': [],
            's_score_history': []  # 新增：S-Score历史
        }
        
        # 创建保存目录
        self._create_directories()
        
        print(f"训练器初始化完成")
        print(f"设备: {self.device}")
        print(f"混合精度: {self.use_amp}")
        print(f"疾病数量: {len(self.disease_list)}")
    
    def _build_severity_mapping(self) -> Dict[str, int]:
        """构建严重程度映射字典"""
        return {
            'None': 0, 'none': 0, '': 0,
            'Mild': 1, 'mild': 1,
            'Moderate': 2, 'moderate': 2,
            'Severe': 3, 'severe': 3
        }
    
    def _build_location_mapping(self) -> Dict[str, int]:
        """构建位置映射字典"""
        return {
            'None': 0, 'none': 0, '': 0,
            'left lung': 1, 'left_lung': 1, 'left': 1,
            'right lung': 2, 'right_lung': 2, 'right': 2,
            'heart': 3, 'cardiac': 3,
            'both lungs': 4, 'bilateral': 4,
            'basilar': 5, 'base': 5,
            'upper lobe': 6, 'lower lobe': 7,
            'mediastinum': 8
        }
    
    def _create_location_mapper(self):
        """
        创建位置映射器（简化版本）
        """
        class SimpleLocationMapper:
            def __init__(self):
                self.location_map = {
                    0: 'None', 1: 'left lung', 2: 'right lung',
                    3: 'heart', 4: 'both lungs', 5: 'basilar',
                    6: 'upper lobe', 7: 'lower lobe', 8: 'mediastinum'
                }
            
            def get_location_name(self, location_id):
                return self.location_map.get(location_id, 'None')
        
        return SimpleLocationMapper()
    
    def _build_optimizer(self) -> optim.Optimizer:
        """构建优化器"""
        return optim.AdamW(
            self.model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
            betas=(0.9, 0.999),
            eps=1e-8
        )
    
    def _build_scheduler(self) -> optim.lr_scheduler._LRScheduler:
        """构建学习率调度器"""
        return optim.lr_scheduler.CosineAnnealingWarmRestarts(
            self.optimizer,
            T_0=10,
            T_mult=2,
            eta_min=1e-6
        )
    
    def _create_directories(self):
        """创建保存目录"""
        Path(self.config.save_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.log_dir).mkdir(parents=True, exist_ok=True)
    
    def _convert_targets_to_batch_labels(self, targets_dict: Dict) -> List[Dict]:
        """
        将dataloader的targets转换为structured_loss需要的batch_labels格式
        
        Args:
            targets_dict: dataloader输出的targets字典
            
        Returns:
            batch_labels: 损失函数需要的格式
        """
        batch_size = targets_dict['disease_labels'].size(0)
        batch_labels = []
        
        # 获取数据
        disease_details_batch = targets_dict['disease_details']
        negative_diseases_batch = targets_dict['negative_diseases']
        
        for i in range(batch_size):
            # 处理正样本发现
            positive_findings = []
            disease_details = disease_details_batch[i]
            
            for detail in disease_details:
                if detail['disease_id'] >= 0:  # 有效疾病
                    finding = {
                        'disease_name': detail['disease_name'],
                        'probability': int(detail['probability']),  # 转换为int
                        'severity': self._id_to_severity(detail['severity']),
                        'location': self._id_to_location(detail['location'])
                    }
                    positive_findings.append(finding)
            
            # 处理负样本发现
            negative_findings = negative_diseases_batch[i]
            
            batch_labels.append({
                'positive_findings': positive_findings,
                'negative_findings': negative_findings
            })
        
        return batch_labels
    
    def _id_to_severity(self, severity_id: int) -> str:
        """将严重程度ID转换为字符串"""
        id_to_severity = {v: k for k, v in self.severity_to_id.items()}
        return id_to_severity.get(severity_id, 'None')
    
    def _id_to_location(self, location_id: int) -> str:
        """将位置ID转换为字符串"""
        id_to_location = {v: k for k, v in self.location_to_id.items()}
        return id_to_location.get(location_id, 'None')
    
    def _prepare_model_outputs_for_loss(self, outputs: Dict) -> Dict:
        """
        将模型输出适配为损失函数期望的格式
        
        Args:
            outputs: 模型原始输出
            
        Returns:
            loss_outputs: 适配后的输出
        """
        def _safe(t: torch.Tensor) -> torch.Tensor:
            # 将非有限值替换为有限数以防损失出现nan/inf
            return torch.nan_to_num(t, nan=0.0, posinf=50.0, neginf=-50.0)

        return {
            # 原始logits（供loss使用）
            'mention_logits': _safe(outputs['disease_logits']),               # (B, Q)
            'polarity_logits': _safe(outputs['polarity_logits']),             # (B, Q, 2)
            'prob_logits': _safe(outputs['probability_logits']),              # (B, Q, 3)
            'sev_logits': _safe(outputs['severity_logits']),                  # (B, Q, 4)
            'loc_logits': _safe(outputs['location_logits']),                  # (B, Q, 50)
            
            # S-Score评估需要的格式
            'disease_mentions': outputs['disease_mentions'],          # (B, Q, 1)
            'disease_probability': outputs['disease_probability'],      # (B, Q, 3)
            'disease_severity': outputs['disease_severity'],          # (B, Q, 4)
            'location_probs': outputs['location_probs']                 # (B, Q, 50)
        }
    
    def _prepare_masks(self, mask_images: Optional[torch.Tensor], batch_size: int) -> torch.Tensor:
        """
        准备掩膜张量
        
        Args:
            mask_images: 批次掩膜图像，可能为None
            batch_size: 批次大小
            
        Returns:
            masks: 4通道掩膜张量 (B, 4, H, W)
        """
        height, width = 224, 224  # 默认尺寸
        
        if mask_images is None:
            # 创建零掩膜
            masks = torch.zeros(batch_size, 4, height, width, device=self.device)
        else:
            # 确保mask_images在正确的设备上
            mask_images = mask_images.to(self.device)
            
            # 将单通道掩膜转换为4通道
            masks = torch.zeros(batch_size, 4, height, width, device=self.device)
            
            # 如果mask_images是单通道，创建4个不同的二进制掩膜
            if mask_images.dim() == 4:  # (B, C, H, W)
                if mask_images.size(1) == 1:  # 单通道
                    # 简单策略：为每个区域创建不同的掩膜
                    for i in range(4):
                        # 创建随机掩膜模式（这里用简单的区域划分）
                        h, w = mask_images.shape[2], mask_images.shape[3]
                        if i == 0:  # 左肺
                            masks[:, i, :, :w//2] = 1.0
                        elif i == 1:  # 右肺
                            masks[:, i, :, w//2:] = 1.0
                        elif i == 2:  # 心脏
                            masks[:, i, h//3:2*h//3, w//3:2*w//3] = 1.0
                        # i=3 是背景，保持为0
                elif mask_images.size(1) >= 4:  # 已经有4个通道
                    masks = mask_images[:, :4, :, :]
            
        return masks
    
    def _compute_weighted_loss(self, loss_dict: Dict[str, torch.Tensor]) -> torch.Tensor:
        """计算加权总损失"""
        total_loss = 0.0
        for loss_name, loss_value in loss_dict.items():
            if loss_name in self.config.loss_weights:
                weight = self.config.loss_weights[loss_name]
                total_loss += weight * loss_value
        return total_loss
    
    def train_epoch(self) -> Dict[str, float]:
        """
        训练一个epoch
        
        Returns:
            epoch_metrics: 本epoch的训练指标
        """
        self.model.train()
        epoch_losses = {
            'total_loss': 0.0,
            'mention_loss': 0.0,
            'polarity_loss': 0.0,
            'probability_loss': 0.0,
            'severity_loss': 0.0,
            'location_loss': 0.0
        }
        
        num_batches = len(self.train_loader)
        
        for batch_idx, batch in enumerate(self.train_loader):
            # 获取数据 - 处理不同的数据格式
            if isinstance(batch, dict):
                # 标准dataloader格式
                images = batch['images'].to(self.device)
                targets = batch['targets']
                mask_images = batch.get('mask_images')
            else:
    # TensorDataset格式 (用于测试)
                images = batch[0].to(self.device)
                targets = batch[1]  # targets 在 batch[1]
                mask_images = batch[3] if len(batch) > 3 else None  # mask_image 在 batch[3]
            
            # 创建虚拟targets（如果需要）
            if targets is None:
                targets = {
                    'disease_labels': torch.zeros(images.size(0), len(self.disease_list)),
                    'disease_details': [[] for _ in range(images.size(0))],
                    'negative_diseases': [[] for _ in range(images.size(0))],
                    'probability_scores': torch.zeros(images.size(0), len(self.disease_list)),
                    'severity_scores': torch.zeros(images.size(0), len(self.disease_list)),
                    'location_ids': torch.zeros(images.size(0), len(self.disease_list)),
                    'num_findings': torch.zeros(images.size(0))
                }
            
            if mask_images is not None:
                mask_images = mask_images.to(self.device)
                
            # 准备掩膜
            masks = self._prepare_masks(mask_images, images.size(0))
                
            # 数据格式转换
            batch_labels = self._convert_targets_to_batch_labels(targets)
                
            # 前向传播
            with autocast(enabled=self.use_amp):
                outputs = self.model(images, masks)
                loss_outputs = self._prepare_model_outputs_for_loss(outputs)
                
                # 计算损失
                loss_dict = compute_structured_loss(
                    loss_outputs, batch_labels,
                    self.disease_list, self.severity_to_id, self.location_to_id
                )
                
                # 应用权重
                weighted_total_loss = self._compute_weighted_loss(loss_dict)
                loss_dict['total_loss'] = weighted_total_loss
                
                # 确保损失张量有梯度（修复梯度问题）
                weighted_total_loss = weighted_total_loss.requires_grad_(True)
            
            #每个 batch 开始就清梯度（比 step 后再清更标准）
            self.optimizer.zero_grad(set_to_none=True)

            # 如果 loss 已经是 nan/inf，直接跳过这个 batch（避免 scaler 相关断言）
            if not torch.isfinite(weighted_total_loss):
                print("Warning: non-finite total loss; skipping batch")
                continue

            # 反向传播
            if self.use_amp:
                self.scaler.scale(weighted_total_loss).backward()

                # backward 后检查是否有梯度产生（关键：避免 No inf checks 断言）
                has_grad = any(p.grad is not None for p in self.model.parameters())
                if not has_grad:
                    print("Warning: no grads produced (likely loss fallback). Skipping optimizer step.")
                    # 不要 step，不要 unscale/clip
                    self.optimizer.zero_grad(set_to_none=True)
                    # 可选：让 scaler 继续更新其内部状态
                    self.scaler.update()
                    continue

                # 梯度裁剪
                if self.config.max_grad_norm > 0:
                    self.scaler.unscale_(self.optimizer)
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)

                self.scaler.step(self.optimizer)
                self.scaler.update()
            else:
                weighted_total_loss.backward()

                # backward 后同样可做梯度检查（可选但安全）
                has_grad = any(p.grad is not None for p in self.model.parameters())
                if not has_grad:
                    print("Warning: no grads produced. Skipping optimizer step.")
                    self.optimizer.zero_grad(set_to_none=True)
                    continue

                # 梯度裁剪
                if self.config.max_grad_norm > 0:
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)

                self.optimizer.step()
            
            # 累积损失
            for key in epoch_losses:
                if key in loss_dict:
                    epoch_losses[key] += loss_dict[key].item()
            
            # 日志记录
            if batch_idx % self.config.log_interval == 0:
                current_lr = self.optimizer.param_groups[0]['lr']
                print(f"Epoch [{self.current_epoch+1}/{self.config.num_epochs}] "
                      f"Batch [{batch_idx}/{num_batches}] "
                      f"Loss: {weighted_total_loss.item():.4f} "
                      f"LR: {current_lr:.6f}")
        
        # 计算平均损失
        for key in epoch_losses:
            epoch_losses[key] /= num_batches
        
        return epoch_losses
    
    def validate(self) -> Dict[str, float]:
        """
        验证模型 - 同时计算损失和S-Score
        
        Returns:
            val_metrics: 验证指标，包含损失和S-Score
        """
        self.model.eval()
        
        # 损失累积
        val_losses = {
            'total_loss': 0.0,
            'mention_loss': 0.0,
            'polarity_loss': 0.0,
            'probability_loss': 0.0,
            'severity_loss': 0.0,
            'location_loss': 0.0
        }
        
        # S-Score数据收集
        all_predictions = []
        all_targets = []
        
        num_batches = len(self.val_loader)
        
        with torch.no_grad():
            for batch in self.val_loader:
                # 获取数据 - 处理不同的数据格式
                if isinstance(batch, dict):
                    # 标准dataloader格式
                    images = batch['images'].to(self.device)
                    targets = batch['targets']
                    mask_images = batch.get('mask_images')
                else:
                    # TensorDataset格式 (用于测试)
                    images = batch[0].to(self.device)
                    masks = batch[1].to(self.device)
                    # 创建虚拟targets
                    targets = {
                        'disease_labels': torch.zeros(images.size(0), len(self.disease_list)),
                        'disease_details': [[] for _ in range(images.size(0))],
                        'negative_diseases': [[] for _ in range(images.size(0))],
                        'probability_scores': torch.zeros(images.size(0), len(self.disease_list)),
                        'severity_scores': torch.zeros(images.size(0), len(self.disease_list)),
                        'location_ids': torch.zeros(images.size(0), len(self.disease_list)),
                        'num_findings': torch.zeros(images.size(0))
                    }
                    mask_images = None
                
                if mask_images is not None:
                    mask_images = mask_images.to(self.device)
                
                # 准备掩膜
                masks = self._prepare_masks(mask_images, images.size(0))
                
                # 数据格式转换
                batch_labels = self._convert_targets_to_batch_labels(targets)
                
                # 前向传播
                with autocast(enabled=self.use_amp):
                    outputs = self.model(images, masks)
                    loss_outputs = self._prepare_model_outputs_for_loss(outputs)
                    
                    # 计算损失
                    loss_dict = compute_structured_loss(
                        loss_outputs, batch_labels,
                        self.disease_list, self.severity_to_id, self.location_to_id
                    )
                    
                    # 应用权重
                    weighted_total_loss = self._compute_weighted_loss(loss_dict)
                    loss_dict['total_loss'] = weighted_total_loss
                
                # 累积损失
                for key in val_losses:
                    if key in loss_dict:
                        val_losses[key] += loss_dict[key].item()
                
                # 收集预测和目标用于S-Score计算
                if self.s_score_evaluator is not None:
                    # 保存模型输出和目标
                    all_predictions.append(outputs)
                    all_targets.extend(batch_labels)
        
        # 计算平均损失
        for key in val_losses:
            val_losses[key] /= num_batches
        
        # 计算S-Score（如果启用）
        if self.s_score_evaluator is not None and all_predictions:
            s_score_results = self._compute_s_score_metrics(
                all_predictions, all_targets
            )
            val_losses.update(s_score_results)
        
        return val_losses
    
    def _compute_s_score_metrics(self, all_predictions: List[Dict], 
                              all_targets: List[Dict]) -> Dict[str, float]:
        """
        计算S-Score相关指标
        """
        # 合并所有批次的预测
        merged_predictions = self._merge_batch_predictions(all_predictions)
        
        # 使用S-Score评估器
        s_score_results = self.s_score_evaluator.evaluate_batch(
            merged_predictions, all_targets, 
            disease_threshold=self.config.s_score_threshold
        )
        
        # 更新最佳分数
        current_s_score = s_score_results.get('S-Score', 0.0)
        if current_s_score > self.best_s_score:
            self.best_s_score = current_s_score
            self.best_p_score = s_score_results.get('P-Score', 0.0)
            self.best_d_score = s_score_results.get('D-Score', 0.0)
        
        return s_score_results

    def _merge_batch_predictions(self, all_predictions: List[Dict]) -> Dict:
        """
        合并批次预测结果
        """
        merged = {
            'disease_mentions': [],
            'disease_probability': [],
            'disease_severity': [],
            'location_probs': []
        }
        
        for batch_pred in all_predictions:
            for key in merged.keys():
                if key in batch_pred:
                    merged[key].append(batch_pred[key])
        
        # 拼接张量
        for key in merged.keys():
            if merged[key]:
                merged[key] = torch.cat(merged[key], dim=0)
        
        return merged
    
    def _print_epoch_summary(self, train_metrics: Dict, val_metrics: Dict):
        """
        打印详细的epoch总结
        """
        print(f"\nEpoch [{self.current_epoch+1}/{self.config.num_epochs}] 完成:")
        print(f"  训练损失: {train_metrics['total_loss']:.4f}")
        print(f"  验证损失: {val_metrics['total_loss']:.4f}")
        
        if 'S-Score' in val_metrics:
            print(f"  P-Score: {val_metrics['P-Score']:.4f}")
            print(f"  D-Score: {val_metrics['D-Score']:.4f}")
            print(f"  S-Score: {val_metrics['S-Score']:.4f}")
            print(f"  最佳S-Score: {self.best_s_score:.4f}")
        
        print(f"  最佳验证损失: {self.best_val_loss:.4f}")

    def _should_save_checkpoint(self, val_metrics: Dict) -> bool:
        """
        判断是否应该保存检查点
        """
        # 传统方式：基于验证损失
        loss_based = val_metrics['total_loss'] < self.best_val_loss
        
        # 新方式：基于S-Score（如果启用）
        s_score_based = False
        if self.config.save_best_s_score and 'S-Score' in val_metrics:
            s_score_based = val_metrics['S-Score'] > self.best_s_score
        
        return loss_based or s_score_based
    
    def _update_s_score_history(self, val_metrics: Dict):
        """
        更新S-Score历史记录
        """
        s_score_entry = {
            'epoch': self.current_epoch,
            'P-Score': val_metrics.get('P-Score', 0.0),
            'D-Score': val_metrics.get('D-Score', 0.0),
            'S-Score': val_metrics.get('S-Score', 0.0),
            'best_P-Score': self.best_p_score,
            'best_D-Score': self.best_d_score,
            'best_S-Score': self.best_s_score
        }
        
        self.training_history['s_score_history'].append(s_score_entry)
    
    def save_checkpoint(self, is_best: bool = False):
        """保存检查点"""
        checkpoint = {
            'epoch': self.current_epoch,
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'scheduler_state_dict': self.scheduler.state_dict(),
            'best_val_loss': self.best_val_loss,
            'best_s_score': self.best_s_score,
            'best_p_score': self.best_p_score,
            'best_d_score': self.best_d_score,
            'training_history': self.training_history,
            'config': self.config,
            'disease_list': self.disease_list
        }
        
        if self.use_amp:
            checkpoint['scaler_state_dict'] = self.scaler.state_dict()
        
        # 始终覆盖保存最新检查点
        checkpoint_path = Path(self.config.save_dir) / "last.pth"
        torch.save(checkpoint, checkpoint_path)
        
        # 保存最佳检查点
        if is_best:
            best_path = Path(self.config.save_dir) / "best.pth"
            torch.save(checkpoint, best_path)
            print(f"保存最佳模型: {best_path}")
    
    def load_checkpoint(self, checkpoint_path: str):
        """加载检查点"""
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
        
        if 'scaler_state_dict' in checkpoint and self.use_amp:
            self.scaler.load_state_dict(checkpoint['scaler_state_dict'])
        
        self.current_epoch = checkpoint['epoch']
        self.best_val_loss = checkpoint['best_val_loss']
        self.training_history = checkpoint['training_history']
        
        print(f"加载检查点: {checkpoint_path}")
        print(f"恢复到epoch {self.current_epoch}")
    
    def should_early_stop(self, current_val_loss: float) -> bool:
        """判断是否应该早停"""
        if current_val_loss < self.best_val_loss - self.config.min_delta:
            self.best_val_loss = current_val_loss
            self.epochs_without_improvement = 0
            return False
        else:
            self.epochs_without_improvement += 1
            return self.epochs_without_improvement >= self.config.patience
    
    def train(self):
        """主训练循环"""
        print("开始训练...")
        print(f"总epoch数: {self.config.num_epochs}")
        print(f"早停patience: {self.config.patience}")
        
        start_time = time.time()
        
        for epoch in range(self.current_epoch, self.config.num_epochs):
            self.current_epoch = epoch
            
            # 训练
            train_metrics = self.train_epoch()
            
            # 验证
            if (epoch + 1) % self.config.eval_interval == 0:
                val_metrics = self.validate()
                
                # 更新学习率
                self.scheduler.step()
                
                # 记录历史
                self.training_history['train_loss'].append(train_metrics)
                self.training_history['val_loss'].append(val_metrics)
                
                # 更新S-Score历史
                if 'S-Score' in val_metrics:
                    self._update_s_score_history(val_metrics)
                
                # 打印epoch总结
                self._print_epoch_summary(train_metrics, val_metrics)
                
                # 保存检查点
                is_best = self._should_save_checkpoint(val_metrics)
                self.save_checkpoint(is_best)
                
                # 早停检查
                if self.should_early_stop(val_metrics['total_loss']):
                    print(f"早停触发，在epoch {epoch+1}")
                    break
            else:
                # 只更新学习率
                self.scheduler.step()
                self.training_history['train_loss'].append(train_metrics)
        
        total_time = time.time() - start_time
        print(f"\n训练完成! 总用时: {total_time/3600:.2f}小时")
        
        # 保存最终历史记录
        history_path = Path(self.config.log_dir) / f"{self.config.experiment_name}_history.json"
        with open(history_path, 'w') as f:
            # 转换numpy类型为Python原生类型以便JSON序列化
            history_serializable = {}
            for key, value in self.training_history.items():
                if isinstance(value, list):
                    history_serializable[key] = [
                        {k: float(v) if isinstance(v, torch.Tensor) else v 
                         for k, v in epoch_dict.items()} if isinstance(epoch_dict, dict) else value
                        for epoch_dict in value
                    ]
                else:
                    history_serializable[key] = value
            
            json.dump(history_serializable, f, indent=2)
        
        print(f"训练历史保存到: {history_path}")
    
    def test(self) -> Dict[str, float]:
        """测试模型"""
        if self.test_loader is None:
            print("没有测试数据加载器")
            return {}
        
        print("开始测试...")
        self.model.eval()
        
        test_losses = {
            'total_loss': 0.0,
            'mention_loss': 0.0,
            'polarity_loss': 0.0,
            'probability_loss': 0.0,
            'severity_loss': 0.0,
            'location_loss': 0.0
        }
        
        num_batches = len(self.test_loader)
        
        with torch.no_grad():
            for batch_idx, batch in enumerate(self.test_loader):
                images = batch['images'].to(self.device)
                targets = batch['targets']
                mask_images = batch.get('mask_images')
                
                if mask_images is not None:
                    mask_images = mask_images.to(self.device)
                
                # 准备掩膜
                masks = self._prepare_masks(mask_images, images.size(0))
                
                # 数据格式转换
                batch_labels = self._convert_targets_to_batch_labels(targets)
                
                # 前向传播
                with autocast(enabled=self.use_amp):
                    outputs = self.model(images, masks)
                    loss_outputs = self._prepare_model_outputs_for_loss(outputs)
                    
                    # 计算损失
                    loss_dict = compute_structured_loss(
                        loss_outputs, batch_labels,
                        self.disease_list, self.severity_to_id, self.location_to_id
                    )
                    
                    # 应用权重
                    weighted_total_loss = self._compute_weighted_loss(loss_dict)
                    loss_dict['total_loss'] = weighted_total_loss
                
                # 累积损失
                for key in test_losses:
                    if key in loss_dict:
                        test_losses[key] += loss_dict[key].item()
                
                if batch_idx % 50 == 0:
                    print(f"测试批次 [{batch_idx}/{num_batches}]")
        
        # 计算平均损失
        for key in test_losses:
            test_losses[key] /= num_batches
        
        print("\n测试结果:")
        for key, value in test_losses.items():
            print(f"  {key}: {value:.4f}")
        
        return test_losses


def create_trainer(
    model: DACGModel,
    train_loader: DataLoader,
    val_loader: DataLoader,
    disease_list: List[str],
    config: Optional[TrainerConfig] = None,
    test_loader: Optional[DataLoader] = None
) -> DACGTrainer:
    """
    创建训练器的便捷函数
    
    Args:
        model: DACG模型
        train_loader: 训练数据加载器
        val_loader: 验证数据加载器
        disease_list: 疾病词汇表
        config: 训练配置，如果为None则使用默认配置
        test_loader: 测试数据加载器
        
    Returns:
        trainer: 训练器实例
    """
    if config is None:
        config = TrainerConfig()
    
    return DACGTrainer(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        config=config,
        disease_list=disease_list,
        test_loader=test_loader
    )


# 使用示例
if __name__ == "__main__":
    print("DACG训练器模块已加载")
    print("使用示例:")
    print("```python")
    print("from project.trainer import create_trainer, TrainerConfig")
    print("")
    print("# 创建配置")
    print("config = TrainerConfig(")
    print("    learning_rate=1e-4,")
    print("    num_epochs=100,")
    print("    experiment_name='my_dacg_experiment'")
    print(")")
    print("")
    print("# 创建训练器")
    print("trainer = create_trainer(")
    print("    model=model,")
    print("    train_loader=train_loader,")
    print("    val_loader=val_loader,")
    print("    disease_list=disease_list,")
    print("    config=config")
    print(")")
    print("")
    print("# 开始训练")
    print("trainer.train()")
    print("```")
