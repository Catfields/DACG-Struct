# U-Net医学图像分割模型

基于U-Net架构的医学图像分割系统，专为SCR数据集设计，支持原图(JPEG)和掩膜(TIFF)的处理。

## 功能特点

- **U-Net架构**: 经典的编码器-解码器结构，支持跳跃连接
- **UNet++架构**: 支持 Nested U-Net（UNet++）变体，提供更细粒度的解码路径
- **注意力机制**: 可选的Attention U-Net变体
- **多器官分割**: 原始PFS轮廓自动栅格化，实现左肺/右肺/心脏多分类输出
- **多种损失函数**: Dice、Focal、组合损失等
- **数据增强**: 旋转、翻转、颜色抖动等
- **完整流程**: 训练、验证、测试、推理一体化

## 环境要求

- Python 3.9+
- PyTorch 2.2.0+ (CUDA支持)
- OpenCV, PIL, NumPy
- Matplotlib, scikit-learn

## 项目结构

```
segmentation_modules/
├── __init__.py          # 模块初始化
├── config.py            # 配置参数
├── data_loader.py       # 数据加载和预处理
├── unet_model.py        # U-Net模型定义
├── upp.py               # UNet++ (Nested U-Net) 模型实现
├── losses.py            # 损失函数
├── trainer.py           # 训练器
├── evaluator.py         # 评估和推理
├── main.py              # 主程序入口
└── README.md            # 使用说明
```

## 数据集格式

项目支持SCR数据集，核心目录：
- **原图**: `/data/SCR/origin/` - JPEG格式
- **PFS轮廓**: `/data/SCR/points/points/` - 含左/右肺与心脏的多边形坐标
- **(可选) 预生成掩膜**: 使用 `preprocess_multiclass_masks.py` 可批量生成多分类PNG掩膜

## 使用方法

### 0. 预生成多分类掩膜（可选）

默认的数据加载器会在训练/评估时即时从PFS轮廓栅格化生成掩膜。如需提前生成PNG标签（便于检查或加速I/O），可运行：

```bash
python preprocess_multiclass_masks.py --output_dir data/SCR/masks_multiclass --color_dir data/SCR/masks_multiclass_color
```

若不需要彩色可视化，可省略 `--color_dir` 参数；使用 `--overwrite` 可重新生成。

### 1. 测试组件功能

```bash
python main.py test
```

### 2. 训练模型

```bash
# 基础训练
python main.py train

# 自定义参数训练
python main.py train --model_type unet --loss_type ce_dice_mc --epochs 100 --batch_size 8

# UNet++ 训练示例
python main.py train --model_type unet++ --loss_type ce_dice_mc --epochs 100 --batch_size 8
```

**训练参数**:
- `--model_type`: 模型类型 (unet, unet++, attention_unet)
- `--loss_type`: 损失函数 (cross_entropy, ce_dice_mc, dice_mc, combined[=ce_dice_mc])
- `--epochs`: 训练轮数 (默认100)
- `--batch_size`: 批次大小 (默认8)
- `--learning_rate`: 学习率 (默认1e-4)

### 3. 评估模型

```bash
# 基础评估
python main.py evaluate

# 带可视化的评估
python main.py evaluate --visualize --num_samples 10
```

评估器会自动读取检查点中的 `model_type` 信息并实例化对应的模型结构（U-Net / UNet++ / Attention U-Net）。
### 4. 单张图像推理

```bash
# 基础推理
python main.py predict /path/to/image.jpg

# 带可视化的推理
python main.py predict /path/to/image.jpg --visualize --output_path result.png
```

推理会额外生成 `*_labels.png`（类别编号图）与 `*_prob.png`（最大类别置信度热图），`--output_path` 指定的文件保存为彩色可视化掩膜。

## 配置说明

主要配置参数在 `config.py` 中：

```python
# 数据路径
IMG_HEIGHT = 256
IMG_WIDTH = 256
IMG_CHANNELS = 3
NUM_CLASSES = 4
CLASS_NAMES = ["background", "right_lung", "left_lung", "heart"]

# 训练参数
BATCH_SIZE = 8
EPOCHS = 100
LEARNING_RATE = 1e-4

# 数据增强
ROTATION_RANGE = 10
HORIZONTAL_FLIP = True
VERTICAL_FLIP = True
```

## 输出结果

训练完成后，以下目录会自动创建：

```
segmentation_modules/
├── models/              # 保存的模型文件
│   ├── best_model.pth   # 最佳模型
│   └── checkpoint_*.pth # 检查点
├── results/             # 结果和可视化
│   ├── training_history.png    # 训练曲线
│   ├── evaluation_report.txt   # 评估报告
│   └── visualizations/         # 预测可视化
├── unet++_results/      # UNet++ 专用训练曲线和 training_info.json
└── logs/                # 日志文件
```

## 评估指标

系统提供多种评估指标：
- **准确率**: 整体分类准确率
- **精确率**: 预测为正例中真正的比例
- **召回率**: 真实正例中被预测为正例的比例
- **F1分数**: 精确率和召回率的调和平均
- **Dice系数**: 分割任务的核心指标
- **IoU**: 交并比

## 模型架构

### 标准U-Net
- 编码器: 4层下采样
- 解码器: 4层上采样
- 跳跃连接: 保持空间信息

### Attention U-Net
- 在跳跃连接中添加注意力机制
- 自动学习重要区域
- 提高分割精度

## 损失函数

- **Dice Loss**: 直接优化Dice系数
- **Focal Loss**: 处理类别不平衡
- **Combined Loss**: Dice + BCE组合
- **Dice+BCE+Focal**: 三重组合损失

## 常见问题

### 1. CUDA内存不足
- 减小批次大小
- 使用梯度累积
- 减少图像尺寸

### 2. 训练不收敛
- 检查数据路径
- 调整学习率
- 尝试不同损失函数

### 3. 推理结果不佳
- 检查输入图像预处理
- 尝试不同的阈值
- 使用数据增强

## 扩展功能

### 添加新的损失函数
```python
class CustomLoss(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, inputs, targets):
        # 自定义损失计算
        return loss
```

### 添加新的模型架构
```python
class CustomModel(nn.Module):
    def __init__(self):
        super().__init__()
        # 定义模型结构

    def forward(self, x):
        # 前向传播
        return x
```

## 联系方式

如有问题，请联系作者。
```
Author: Catfield
Email: 2022211136@stu.hit.edu.cn
```
