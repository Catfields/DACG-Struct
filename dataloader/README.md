# MIMIC-CXR-A DataLoader 使用说明

## 概述

这个模块提供了完整的MIMIC-CXR-A数据集加载功能，支持：
- 胸部X光图像加载
- 结构化疾病标注（包含概率、严重程度、位置信息）
- 分割掩膜加载（可选）
- 分层分割索引支持

## 快速开始

### 基本使用

```python
from dataloader import MIMICCXRADataset, MIMICCXRACollator, create_mimic_cxr_data_loaders

# 方法1：使用工厂函数（推荐）
class Args:
    def __init__(self):
        self.csv_path = '/path/to/structured_reports.csv'
        self.image_dir = '/path/to/images'
        self.mask_dir = '/path/to/masks'  # 可选
        self.batch_size = 32
        self.num_workers = 4

args = Args()
split_dir = '/path/to/stratified_split'

# 创建数据加载器
train_loader, val_loader, test_loader = create_mimic_cxr_data_loaders(
    args, split_dir, load_masks=True
)

# 方法2：手动创建
from torchvision import transforms

transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225))
])

dataset = MIMICCXRADataset(
    csv_path='/path/to/structured_reports.csv',
    split='train',
    image_dir='/path/to/images',
    split_dir='/path/to/stratified_split',
    mask_dir='/path/to/masks',  # 可选
    transform=transform,
    load_masks=True
)

collator = MIMICCXRACollator()
dataloader = data.DataLoader(
    dataset, batch_size=32, shuffle=True, 
    collate_fn=collator, num_workers=4
)
```

### 数据格式

每个批次返回的数据格式：

```python
batch = next(iter(dataloader))
print(batch.keys())
# ['images', 'targets', 'image_ids', 'mask_images']

print(batch['images'].shape)      # [batch_size, 3, height, width]
print(batch['targets'].keys())
# ['disease_labels', 'disease_details', 'probability_scores', 
#  'severity_scores', 'location_ids', 'negative_diseases', 'num_findings']

# 疾病标签（多标签二分类）
print(batch['targets']['disease_labels'].shape)  # [batch_size, num_diseases]

# 详细的疾病信息
print(batch['targets']['disease_details'][0])  # 第一个样本的疾病详情
# [
#   {
#       'disease_name': 'pneumonia',
#       'disease_id': 10,
#       'probability': 0.75,  # 标准化后的概率 (0.25-1.0)
#       'severity': 2,        # 严重程度 (0-3: none, mild, moderate, severe)
#       'location': 1          # 位置ID (见位置映射表)
#   },
#   ...
# ]

# 概率、严重程度、位置分数（已padding到相同长度）
print(batch['targets']['probability_scores'].shape)  # [batch_size, max_findings]
print(batch['targets']['severity_scores'].shape)     # [batch_size, max_findings]
print(batch['targets']['location_ids'].shape)        # [batch_size, max_findings]

# 掩膜图像（如果启用）
if batch['mask_images'] is not None:
    print(batch['mask_images'].shape)  # [batch_size, 1, height, width]
```

## 数据结构说明

### 疾病详细信息

每个阳性疾病包含以下信息：
- `disease_name`: 疾病名称（字符串）
- `probability`: 概率等级（1-4，标准化为0.25-1.0）
- `severity`: 严重程度（None/Mild/Moderate/Severe，标准化为0-3）
- `location`: 解剖位置（标准化为整数ID）

### 位置映射

```python
LOCATION_MAP = {
    'None': 0, 'none': 0, '': 0,
    'left lung': 1, 'left_lung': 1, 'left': 1,
    'right lung': 2, 'right_lung': 2, 'right': 2,
    'heart': 3, 'cardiac': 3,
    'both lungs': 4, 'bilateral': 4,
    'basilar': 5, 'base': 5,
    'upper lobe': 6, 'lower lobe': 7,
    'mediastinum': 8
}
```

### 严重程度映射

```python
SEVERITY_MAP = {
    None: 0, 'None': 0, 'none': 0, '': 0,
    'Mild': 1, 'mild': 1,
    'Moderate': 2, 'moderate': 2,
    'Severe': 3, 'severe': 3
}
```

## 配置选项

### MIMICCXRADataset 参数

- `csv_path`: 结构化报告CSV文件路径
- `split`: 数据分割 ('train', 'val', 'test')
- `image_dir`: 图像文件根目录
- `split_dir`: 分层分割索引目录（可选）
- `mask_dir`: 掩膜图像目录（可选）
- `transform`: 图像变换（可选）
- `disease_list`: 预定义疾病词汇表（可选）
- `load_masks`: 是否加载掩膜图像（默认True）

### MIMICCXRACollator 参数

- `pad_value`: 填充值，用于变长序列（默认-1）

## 测试

运行测试代码：

```python
from dataloader import test_mimic_cxr_dataloader
test_mimic_cxr_dataloader()
```

## 注意事项

1. **缺失图像处理**: 如果图像文件不存在，会创建黑色占位符图像并发出警告
2. **掩膜加载**: 掩膜是可选的，如果没有找到对应的掩膜文件，返回None
3. **内存使用**: 大数据集建议使用适当的batch_size和num_workers
4. **疾病词汇表**: 如果不提供预定义词汇表，会从训练数据中自动构建

## 示例：训练循环

```python
import torch
import torch.nn as nn
from dataloader import create_mimic_cxr_data_loaders

# 创建数据加载器
train_loader, val_loader, test_loader = create_mimic_cxr_data_loaders(
    args, split_dir, load_masks=False
)

# 模型定义
class CXRModel(nn.Module):
    def __init__(self, num_diseases):
        super().__init__()
        self.backbone = ...  # 你的backbone
        self.classifier = nn.Linear(..., num_diseases)
    
    def forward(self, x):
        features = self.backbone(x)
        return self.classifier(features)

# 训练
model = CXRModel(num_diseases=len(train_loader.dataset.disease_list))
criterion = nn.BCEWithLogitsLoss()
optimizer = torch.optim.Adam(model.parameters())

for epoch in range(num_epochs):
    for batch in train_loader:
        images = batch['images']
        labels = batch['targets']['disease_labels'].float()
        
        outputs = model(images)
        loss = criterion(outputs, labels)
        
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
```

这样就完成了MIMIC-CXR-A数据加载器的完整实现和使用说明！