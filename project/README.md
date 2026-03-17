# DACG训练器使用指南

本目录包含DACG模型的完整训练器实现，支持多任务学习、混合精度训练、早停机制等功能。

## 文件说明

- `structured_model.py` - DACG模型定义
- `trainer.py` - 训练器核心实现
- `trainer_example.py` - 使用示例代码
- `README.md` - 本说明文档

## 快速开始

### 1. 基本使用

```python
from project.structured_model import DACGModel, DACGModelConfig
from project.trainer import create_trainer, TrainerConfig
from dataloader.dataloader import create_mimic_cxr_data_loaders

# 创建数据加载器
train_loader, val_loader, test_loader = create_mimic_cxr_data_loaders(
    args=args,
    split_dir=split_dir,
    load_masks=True
)

# 获取疾病词汇表
disease_list = train_loader.dataset.get_disease_list()

# 创建模型
model_config = DACGModelConfig(
    visual_extractor='resnet101',
    d_model=512,
    num_regions=4
)
model = DACGModel.from_config(model_config)

# 创建训练器
config = TrainerConfig(
    learning_rate=1e-4,
    num_epochs=100,
    experiment_name='my_experiment'
)

trainer = create_trainer(
    model=model,
    train_loader=train_loader,
    val_loader=val_loader,
    disease_list=disease_list,
    config=config
)

# 开始训练
trainer.train()
```

### 2. 配置参数

#### TrainerConfig 主要参数

```python
@dataclass
class TrainerConfig:
    # 基础训练参数
    learning_rate: float = 1e-4          # 学习率
    weight_decay: float = 1e-5           # 权重衰减
    warmup_epochs: int = 5               # 预热epoch数
    max_grad_norm: float = 1.0            # 梯度裁剪阈值
    
    # 损失权重
    loss_weights: Dict[str, float] = {
        'mention_loss': 1.0,      # 疾病提及损失权重
        'polarity_loss': 1.0,      # 极性损失权重
        'probability_loss': 1.0,   # 概率损失权重
        'severity_loss': 1.0,      # 严重程度损失权重
        'location_loss': 1.0       # 位置损失权重
    }
    
    # 训练控制
    num_epochs: int = 100               # 总训练轮数
    save_interval: int = 5               # 保存间隔
    eval_interval: int = 1               # 验证间隔
    log_interval: int = 50               # 日志间隔
    
    # 早停参数
    patience: int = 10                   # 早停耐心值
    min_delta: float = 1e-4              # 最小改善阈值
    
    # 设备和优化
    device: str = 'cuda'                 # 训练设备
    use_amp: bool = True                 # 混合精度训练
```

#### DACGModelConfig 主要参数

```python
@dataclass
class DACGModelConfig:
    # 视觉提取器配置
    visual_extractor: str = 'resnet101'     # 视觉提取器类型
    visual_feat_dim: int = 2048              # 视觉特征维度
    visual_extractor_pretrained: bool = True  # 是否使用预训练
    
    # 模型架构配置
    d_model: int = 512                       # 模型特征维度
    num_regions: int = 4                     # 区域数量
    
    # V_fused_Encoder 配置
    vfused_encoder_layers: int = 1           # 编码器层数
    vfused_encoder_heads: int = 8             # 注意力头数
    vfused_encoder_d_ff: int = 2048          # 前馈网络维度
    vfused_encoder_dropout: float = 0.1      # dropout率
```

## 核心功能

### 1. 多任务损失计算

训练器自动处理5个任务的损失计算：
- **疾病提及检测** (Mention Detection)
- **极性分类** (Polarity Classification) 
- **概率等级预测** (Probability Level Prediction)
- **严重程度分类** (Severity Classification)
- **解剖位置预测** (Anatomical Location Prediction)

### 2. 数据格式转换

训练器自动将dataloader的输出格式转换为损失函数需要的格式：

```python
# DataLoader输出格式
targets = {
    'disease_details': [...],
    'negative_diseases': [...],
    'probability_scores': [...],
    'severity_scores': [...],
    'location_ids': [...]
}

# 自动转换为损失函数需要的格式
batch_labels = [
    {
        'positive_findings': [
            {
                'disease_name': str,
                'probability': int,
                'severity': str,
                'location': str
            }
        ],
        'negative_findings': [str, ...]
    },
    ...
]
```

### 3. 混合精度训练

支持自动混合精度(AMP)训练，显著提升训练速度并减少显存使用：

```python
config = TrainerConfig(
    use_amp=True,  # 启用混合精度
    device='cuda'  # 需要CUDA设备
)
```

### 4. 早停机制

自动监控验证损失，当性能不再提升时停止训练：

```python
config = TrainerConfig(
    patience=10,        # 10个epoch无改善则停止
    min_delta=1e-4      # 最小改善阈值
)
```

### 5. 检查点管理

自动保存和管理训练检查点：

- `experiment_name_latest.pth` - 最新检查点
- `experiment_name_best.pth` - 最佳性能检查点
- `experiment_name_epoch_N.pth` - 定期保存的检查点

## 高级用法

### 1. 恢复训练

```python
# 创建训练器
trainer = create_trainer(model, train_loader, val_loader, disease_list)

# 加载检查点
trainer.load_checkpoint('./checkpoints/experiment_latest.pth')

# 继续训练
trainer.train()
```

### 2. 自定义训练循环

```python
trainer = create_trainer(model, train_loader, val_loader, disease_list)

for epoch in range(50):
    # 训练一个epoch
    train_metrics = trainer.train_epoch()
    
    # 验证
    val_metrics = trainer.validate()
    
    # 自定义逻辑
    if val_metrics['total_loss'] < best_loss:
        trainer.save_checkpoint(is_best=True)
```

### 3. 测试模型

```python
# 训练完成后测试
test_results = trainer.test()

# 或者单独加载模型进行测试
model = DACGModel.from_config(model_config)
checkpoint = torch.load('./checkpoints/experiment_best.pth')
model.load_state_dict(checkpoint['model_state_dict'])

trainer = create_trainer(model, train_loader, val_loader, disease_list)
test_results = trainer.test()
```

### 4. 推理

```python
# 加载训练好的模型
model = DACGModel.from_config(model_config)
checkpoint = torch.load('./checkpoints/experiment_best.pth')
model.load_state_dict(checkpoint['model_state_dict'])
model.eval()

# 准备输入
images = torch.randn(1, 3, 224, 224)
masks = torch.randint(0, 2, (1, 4, 224, 224)).float()

# 推理
with torch.no_grad():
    outputs = model(images, masks)

# 处理输出
disease_probs = outputs['disease_mentions']  # (1, num_diseases, 1)
polarity_probs = outputs['disease_polarity']  # (1, num_diseases, 2)
# ... 其他输出
```

## 监控和日志

### 1. 训练日志

训练过程中会自动打印训练进度：

```
Epoch [1/100] Batch [0/500] Loss: 2.3456 LR: 0.000100
Epoch [1/100] Batch [50/500] Loss: 2.1234 LR: 0.000095
...

Epoch [1/100] 完成:
  训练损失: 1.9876
  验证损失: 1.8765
  最佳验证损失: 1.8765
保存最佳模型: ./checkpoints/experiment_best.pth
```

### 2. 训练历史

训练历史会自动保存为JSON文件：

```python
# 加载训练历史
import json
with open('./logs/experiment_history.json', 'r') as f:
    history = json.load(f)

train_losses = [epoch['total_loss'] for epoch in history['train_loss']]
val_losses = [epoch['total_loss'] for epoch in history['val_loss']]
```

## 常见问题

### Q1: 如何调整损失权重？

```python
config = TrainerConfig(
    loss_weights={
        'mention_loss': 2.0,      # 增加疾病检测权重
        'polarity_loss': 1.0,
        'probability_loss': 0.5,   # 降低概率预测权重
        'severity_loss': 0.5,
        'location_loss': 0.3
    }
)
```

### Q2: 如何处理显存不足？

```python
# 1. 减小batch size
args.batch_size = 4  # 从8减小到4

# 2. 启用混合精度
config = TrainerConfig(use_amp=True)

# 3. 使用梯度累积
# (需要在trainer.py中添加梯度累积逻辑)
```

### Q3: 如何使用不同的优化器？

修改`trainer.py`中的`_build_optimizer`方法：

```python
def _build_optimizer(self):
    return optim.SGD(
        self.model.parameters(),
        lr=self.config.learning_rate,
        momentum=0.9,
        weight_decay=self.config.weight_decay
    )
```

### Q4: 如何添加自定义指标？

继承`DACGTrainer`类并重写相关方法：

```python
class CustomTrainer(DACGTrainer):
    def validate(self):
        val_metrics = super().validate()
        
        # 添加自定义指标计算
        custom_metrics = self.compute_custom_metrics()
        val_metrics.update(custom_metrics)
        
        return val_metrics
```

## 完整示例

查看 `trainer_example.py` 文件获取完整的使用示例，包括：

- 完整训练流程
- 恢复训练
- 推理示例
- 自定义训练循环

运行示例：
```bash
cd project
python trainer_example.py
```

## 依赖要求

- PyTorch >= 1.8.0
- torchvision
- numpy
- 其他依赖见 `environment.yml`

## 注意事项

1. 确保数据路径正确设置
2. 检查CUDA是否可用（如果使用GPU训练）
3. 监控显存使用情况
4. 定期备份检查点文件
5. 根据具体任务调整损失权重

## 技术支持

如有问题，请检查：
1. 数据格式是否正确
2. 模型配置是否匹配
3. 损失函数输入输出格式
4. 设备和显存设置