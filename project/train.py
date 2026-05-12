#!/usr/bin/env python3
"""
DACG模型训练入口脚本
支持命令行参数和配置文件
"""

from __future__ import annotations

import argparse
import os
import sys
import yaml
import json
import logging
import glob
import random
from pathlib import Path
from typing import Dict, Any, Optional

import torch
# 导入核心模块
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_args():
    """解析命令行参数（简化版，主要参数通过配置文件传递）"""
    parser = argparse.ArgumentParser(description='DACG模型训练脚本 - 使用YAML配置文件')
    
    # 配置文件（必要参数）
    parser.add_argument('--config', type=str, 
                       default='config/structured_config.yaml',
                       help='配置文件路径')
    
    # 运行模式（快速选择不同的配置）
    parser.add_argument('--mode', type=str, default='normal',
                       choices=['normal', 'quick', 'debug'],
                       help='运行模式：normal(正常), quick(快速测试), debug(调试模式)')
    
    # 保留一些关键的覆盖选项（可选）
    parser.add_argument('--resume', type=str, default=None,
                       help='恢复训练的检查点路径（覆盖配置文件）')
    parser.add_argument('--device', type=str, default=None,
                       choices=['auto', 'cuda', 'cpu'],
                       help='训练设备（覆盖配置文件）')
    
    return parser.parse_args()


def load_config(config_path: str) -> Dict[str, Any]:
    """加载YAML配置文件"""
    if not os.path.exists(config_path):
        print(f"警告: 配置文件 {config_path} 不存在，使用默认配置")
        return {}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config


def deep_merge(base_dict: Dict, override_dict: Dict) -> Dict:
    """深度合并字典"""
    result = base_dict.copy()
    
    for key, value in override_dict.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def merge_configs(args: argparse.Namespace, config: Dict) -> Dict:
    """合并命令行参数和配置文件，命令行参数优先级更高"""
    merged = config.copy()
    
    # 只处理保留的命令行覆盖选项
    if args.resume:
        merged.setdefault('experiment', {})['resume'] = args.resume
    
    if args.device:
        merged.setdefault('environment', {})['device'] = args.device
    
    # 处理运行模式
    if hasattr(args, 'mode'):
        merged.setdefault('experiment', {})['mode'] = args.mode
    
    return merged


def setup_logging(log_dir: str, experiment_name: str, level: str = 'INFO') -> None:
    """设置日志系统"""
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f"{experiment_name}.log")
    
    # 设置日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"日志文件: {log_file}")
    logger.info(f"日志级别: {level}")


def set_random_seed(seed: int):
    """设置随机种子"""
    import torch
    import numpy as np
    random.seed(seed)
    np.random.seed(seed)
    
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    
    # 设置确定性
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def auto_detect_disease_count(data_path: str, data_format: str = 'auto') -> int:
    """从数据文件中自动检测疾病数量"""
    try:
        # 自动检测格式
        if data_format == 'auto':
            if data_path.endswith('.jsonl'):
                data_format = 'jsonl'
            elif data_path.endswith('.csv'):
                data_format = 'csv'
            else:
                print(f"警告: 无法检测数据格式，默认使用CSV")
                data_format = 'csv'
        
        all_diseases = set()
        
        if data_format == 'jsonl':
            # 处理JSONL格式
            import json
            with open(data_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        # 从 positive_findings 中提取疾病
                        for finding in record.get('positive_findings', []):
                            if isinstance(finding, dict):
                                disease_name = finding.get('disease_name', '')
                                if disease_name:
                                    all_diseases.add(disease_name)
                        # 从 negative_findings 中提取疾病
                        for disease in record.get('negative_findings', []):
                            if disease:
                                all_diseases.add(disease)
                    except:
                        continue
        else:
            # 处理CSV格式
            import pandas as pd
            df = pd.read_csv(data_path)
            
            # 解析positive_diseases_detail字段
            all_diseases = set()
            for _, row in df.iterrows():
                if pd.notna(row['positive_diseases_detail']):
                    import ast
                    diseases = ast.literal_eval(row['positive_diseases_detail'])
                    for disease in diseases:
                        if isinstance(disease, dict):
                            all_diseases.add(disease.get('disease', ''))
        
        disease_count = len(all_diseases)
        print(f"自动检测到疾病数量: {disease_count}")
        return disease_count
    except Exception as e:
        print(f"警告: 无法自动检测疾病数量: {e}")
        return 30  # 默认值


def create_model_config(args: Dict) -> DACGModelConfig:
    """从合并后的参数创建模型配置"""
    from project.model import DACGModelConfig

    # 调试输出：验证vfused_encoder配置
    vfused_encoder_config = args.get('model', {}).get('vfused_encoder', {})
    vfused_layers = vfused_encoder_config.get('layers', 1)
    print(f"[DEBUG] 从配置文件读取的vfused_encoder配置: {vfused_encoder_config}")
    print(f"[DEBUG] vfused_encoder.layers值: {vfused_layers}")

    # 如果提供了 disease_vocab_sizes，则 location_vocab_size 设为 -1（使用 disease-specific 模式）
    disease_vocab_sizes = args.get('model', {}).get('disease_vocab_sizes')
    if disease_vocab_sizes is not None:
        location_vocab_size = -1  # 使用 disease-specific 模式
    else:
        # 计算全局 location_vocab_size（向后兼容）
        location_candidates = args.get('model', {}).get('location_candidates', {})
        total_concepts = sum(len(c.get('concept_candidates', [])) for c in location_candidates.values())
        total_modifiers = sum(len(c.get('modifier_candidates', [])) for c in location_candidates.values())
        location_vocab_size = total_concepts + total_modifiers + 1

    return DACGModelConfig(
        visual_extractor=args.get('model', {}).get('visual_extractor', 'resnet101'),
        visual_feat_dim=args.get('model', {}).get('visual_feat_dim', 2048),
        visual_extractor_pretrained=args.get('model', {}).get('visual_extractor_pretrained', False),
        d_model=args.get('model', {}).get('d_model', 512),
        num_regions=args.get('model', {}).get('num_regions', 4),
        vfused_encoder_layers=vfused_layers,
        vfused_encoder_heads=args.get('model', {}).get('vfused_encoder', {}).get('heads', 8),
        vfused_encoder_d_ff=args.get('model', {}).get('vfused_encoder', {}).get('d_ff', 2048),
        vfused_encoder_dropout=args.get('model', {}).get('vfused_encoder', {}).get('dropout', 0.1),
        num_diseases=args.get('model', {}).get('num_diseases', 16),
        location_vocab_size=location_vocab_size,
        dropout=args.get('model', {}).get('dropout', 0.1),
        device=args.get('environment', {}).get('device', 'auto'),
        # 新增：disease-specific 参数
        disease_vocab_sizes=disease_vocab_sizes,
        disease_order=args.get('model', {}).get('disease_order'),
        disease_json_path=args.get('model', {}).get(
            'disease_json_path',
            os.path.join(
                args.get('data', {}).get('split_dir', 'data/mimic-cxr-a'),
                'disease_location_candidates.json'
            )
        ),
    )


def create_trainer_config(args: Dict) -> TrainerConfig:
    """创建训练器配置"""
    from project.trainer import TrainerConfig

    loss_weights = args.get('loss', {}).get('weights', {
        'mention_loss': 1.0,
        'polarity_loss': 1.0,
        'probability_loss': 1.0,
        'severity_loss': 1.0,
        'modifier_loss': 1.0,
        'anatomy_loss': 1.0,
    })

    # 兼容旧配置键 location_loss
    if 'location_loss' in loss_weights:
        loss_weights.setdefault('modifier_loss', loss_weights['location_loss'])
        loss_weights.setdefault('anatomy_loss', loss_weights['location_loss'])

    return TrainerConfig(
        learning_rate=float(args.get('training', {}).get('learning_rate', '1e-4')),
        weight_decay=float(args.get('training', {}).get('weight_decay', '1e-5')),
        warmup_epochs=args.get('training', {}).get('warmup_epochs', 5),
        max_grad_norm=args.get('training', {}).get('max_grad_norm', 1.0),
        
        # 损失权重
        loss_weights=loss_weights,
        
        # 训练控制
        num_epochs=args.get('training', {}).get('num_epochs', 100),
        save_interval=args.get('experiment', {}).get('save', {}).get('interval', 5),
        eval_interval=args.get('training', {}).get('eval_interval', 1),
        log_interval=args.get('training', {}).get('log_interval', 50),
        
        # 保存和日志
        save_dir=args.get('experiment', {}).get('save', {}).get('dir', './checkpoints'),
        log_dir=args.get('experiment', {}).get('logging', {}).get('dir', './logs'),
        experiment_name=args.get('experiment', {}).get('name', 'dacg_experiment'),
        
        # 设备和优化
        device=args.get('environment', {}).get('device', 'auto'),
        use_amp=args.get('environment', {}).get('mixed_precision', True),
        num_workers=args.get('training', {}).get('num_workers', 4),
        max_train_batches=args.get('training', {}).get('max_train_batches'),
        max_val_batches=args.get('training', {}).get('max_val_batches'),
        max_test_batches=args.get('training', {}).get('max_test_batches'),
        
        # S-Score评估配置
        enable_s_score=args.get('s_score', {}).get('enabled', True),
        s_score_interval=args.get('s_score', {}).get('interval', 1),
        s_score_threshold=args.get('s_score', {}).get('threshold', 0.3),
        s_score_weights=args.get('s_score', {}).get('weights', {
            'p_weight': args.get('s_score', {}).get('weights', {}).get('p_weight', 0.5),
            'd_weight': args.get('s_score', {}).get('weights', {}).get('d_weight', 0.5)
        }),
        save_best_s_score=args.get('s_score', {}).get('save_best', True),
        
        # 早停参数
        patience=int(args.get('experiment', {}).get('early_stopping', {}).get('patience', 10)),
        min_delta=float(args.get('experiment', {}).get('early_stopping', {}).get('min_delta', 1e-4)),
        polarity_class_weights=args.get('loss', {}).get('polarity_class_weights'),
    )


def create_multilabel_model_config(args: Dict, label_names) -> MultiLabelDACGModelConfig:
    """从配置创建单任务多标签模型配置"""
    from project.multilabel_model import MultiLabelDACGModelConfig

    vfused_encoder_config = args.get('model', {}).get('vfused_encoder', {})
    vfused_layers = vfused_encoder_config.get('layers', 1)

    return MultiLabelDACGModelConfig(
        visual_extractor=args.get('model', {}).get('visual_extractor', 'resnet101'),
        visual_extractor_pretrained=args.get('model', {}).get('visual_extractor_pretrained', False),
        d_model=args.get('model', {}).get('d_model', 512),
        num_regions=args.get('model', {}).get('num_regions', 4),
        vfused_encoder_layers=vfused_layers,
        vfused_encoder_heads=args.get('model', {}).get('vfused_encoder', {}).get('heads', 8),
        vfused_encoder_d_ff=args.get('model', {}).get('vfused_encoder', {}).get('d_ff', 2048),
        vfused_encoder_dropout=args.get('model', {}).get('vfused_encoder', {}).get('dropout', 0.1),
        dropout=args.get('model', {}).get('dropout', 0.1),
        num_labels=len(label_names),
        label_names=list(label_names),
    )


def _compute_multilabel_pos_weight(train_loader, max_value: Optional[float] = None):
    labels = train_loader.dataset.label_matrix()
    positives = labels.sum(dim=0)
    negatives = labels.size(0) - positives
    pos_weight = negatives / torch.clamp(positives, min=1.0)
    if max_value is not None:
        pos_weight = torch.clamp(pos_weight, max=float(max_value))
    return [float(x) for x in pos_weight.tolist()]


def create_multilabel_trainer_config(args: Dict, train_loader) -> MultiLabelTrainerConfig:
    """创建单任务多标签训练器配置"""
    from project.multilabel_trainer import MultiLabelTrainerConfig

    pos_weight = args.get('loss', {}).get('pos_weight')
    if isinstance(pos_weight, str) and pos_weight.lower() == 'auto':
        max_pos_weight = args.get('loss', {}).get('max_pos_weight')
        pos_weight = _compute_multilabel_pos_weight(train_loader, max_pos_weight)
    elif pos_weight is not None:
        pos_weight = [float(x) for x in pos_weight]

    return MultiLabelTrainerConfig(
        learning_rate=float(args.get('training', {}).get('learning_rate', '1e-4')),
        weight_decay=float(args.get('training', {}).get('weight_decay', '1e-5')),
        max_grad_norm=args.get('training', {}).get('max_grad_norm', 1.0),
        num_epochs=args.get('training', {}).get('num_epochs', 100),
        eval_interval=args.get('training', {}).get('eval_interval', 1),
        log_interval=args.get('training', {}).get('log_interval', 50),
        threshold=float(args.get('metrics', {}).get('threshold', 0.5)),
        save_dir=args.get('experiment', {}).get('save', {}).get('dir', './checkpoints_multilabel'),
        log_dir=args.get('experiment', {}).get('logging', {}).get('dir', './logs'),
        experiment_name=args.get('experiment', {}).get('name', 'dacg_multilabel'),
        device=args.get('environment', {}).get('device', 'auto'),
        use_amp=args.get('environment', {}).get('mixed_precision', True),
        patience=int(args.get('experiment', {}).get('early_stopping', {}).get('patience', 10)),
        min_delta=float(args.get('experiment', {}).get('early_stopping', {}).get('min_delta', 1e-4)),
        pos_weight=pos_weight,
        loss_type=args.get('loss', {}).get('type', 'focal'),
        focal_alpha=args.get('loss', {}).get('focal_alpha'),
        focal_gamma=float(args.get('loss', {}).get('focal_gamma', 2.0)),
        logit_clip=float(args.get('loss', {}).get('logit_clip', 20.0)),
        progress_bar=bool(args.get('training', {}).get('progress_bar', True)),
    )


def main_multilabel(merged_config: Dict, config_path: str, logger: logging.Logger):
    """单任务多标签训练流程"""
    from dataloader.multilabel_dataloader import create_mimic_cxr_multilabel_data_loaders
    from project.multilabel_model import MultiLabelDACGModel
    from project.multilabel_trainer import create_multilabel_trainer

    logger.info("启动单任务多标签训练流程")
    logger.info(f"使用配置文件: {config_path}")

    dataloader_args = create_args_namespace(**merged_config.get('data', {}), **merged_config.get('training', {}))
    train_loader, val_loader, test_loader, label_names = create_mimic_cxr_multilabel_data_loaders(
        dataloader_args
    )
    merged_config.setdefault('model', {})['num_labels'] = len(label_names)
    merged_config['model']['label_names'] = list(label_names)

    logger.info(f"多标签类别数: {len(label_names)}")
    logger.info(f"标签顺序: {label_names}")

    model_config = create_multilabel_model_config(merged_config, label_names)
    model = MultiLabelDACGModel.from_config(model_config)
    model.print_model_info()

    trainer_config = create_multilabel_trainer_config(merged_config, train_loader)
    trainer = create_multilabel_trainer(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        label_names=label_names,
        config=trainer_config,
        test_loader=test_loader,
    )

    resume_path = merged_config.get('experiment', {}).get('resume') or merged_config.get('resume')
    if resume_path:
        logger.info(f"恢复训练: {resume_path}")
        trainer.load_checkpoint(resume_path)

    logger.info("开始训练...")
    logger.info(f"实验名称: {merged_config.get('experiment', {}).get('name', 'dacg_multilabel')}")
    logger.info(f"训练轮数: {merged_config.get('training', {}).get('num_epochs', 100)}")
    logger.info(f"批次大小: {merged_config.get('training', {}).get('batch_size', 16)}")
    logger.info(f"学习率: {merged_config.get('training', {}).get('learning_rate', 1e-4)}")

    trainer.train()

    if test_loader is not None and merged_config.get('experiment', {}).get('test_after_train', True):
        test_results = trainer.test()
        logger.info(f"测试结果: {test_results}")

    logger.info("多标签训练完成!")


def validate_paths(args: Dict) -> None:
    """验证所有必要路径是否存在"""
    required_paths = [
        ('data', 'data_path', '数据文件'),
        ('data', 'image_dir', '图像目录'),
        ('data', 'split_dir', '分割目录')
    ]
    
    for section, path_key, path_name in required_paths:
        path = args.get(section, {}).get(path_key)
        if path and not os.path.exists(path):
            raise FileNotFoundError(f"{path_name}不存在: {path}")
    
    # 可选路径检查
    optional_paths = [
        ('data', 'mask_dir', '掩膜目录')
    ]
    
    for section, path_key, path_name in optional_paths:
        path = args.get(section, {}).get(path_key)
        if path and not os.path.exists(path):
            print(f"警告: {path_name}不存在: {path}")


def create_args_namespace(**kwargs):
    """将字典转换为类似argparse.Namespace的对象"""
    class ArgsNamespace:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    return ArgsNamespace(**kwargs)


def get_model_architecture(args: Dict) -> str:
    """返回模型架构版本。默认保持 v2/原 DACG 行为。"""
    model_cfg = args.get('model', {}) or {}
    architecture = (
        model_cfg.get('architecture')
        or model_cfg.get('version')
        or model_cfg.get('name')
        or 'v2'
    )
    return str(architecture).lower()


def main():
    """主训练函数"""
    # 1. 解析参数
    args = parse_args()

    # 2. 选择配置文件（根据模式）
    if args.mode == 'quick':
        config_path = 'config/quick_config.yaml'
    elif args.mode == 'debug':
        config_path = 'config/debug_config.yaml'
    else:
        config_path = args.config

    # 3. 加载配置文件
    config = load_config(config_path)

    # 4. 合并配置（现在主要是处理命令行覆盖选项）
    merged_config = merge_configs(args, config)

    # 5. 设置随机种子
    seed = merged_config.get('experiment', {}).get('seed') or merged_config.get('seed', 42)
    set_random_seed(seed)

    # 6. 设置日志（必须在logger使用之前）
    log_level = 'DEBUG' if args.mode == 'debug' else merged_config.get('experiment', {}).get('logging', {}).get('level', 'INFO')
    setup_logging(
        merged_config.get('experiment', {}).get('logging', {}).get('dir', './logs'),
        merged_config.get('experiment', {}).get('name', 'dacg_experiment'),
        log_level
    )
    logger = logging.getLogger(__name__)

    task_type = str(
        merged_config.get('task')
        or merged_config.get('experiment', {}).get('task')
        or merged_config.get('data', {}).get('task')
        or ''
    ).lower()
    if task_type in ('multilabel', 'multi_label', 'multi-label'):
        main_multilabel(merged_config, config_path, logger)
        return

    # 7. 加载疾病顺序和候选集合
    logger.info("加载疾病元数据...")

    split_dir = merged_config.get('data', {}).get('split_dir', 'data/mimic-cxr-a')

    # 加载 disease_order.json
    disease_order_path = os.path.join(split_dir, 'disease_order.json')
    with open(disease_order_path, 'r') as f:
        disease_order = json.load(f)
    logger.info(f"疾病顺序: {disease_order}")

    # 加载 disease_location_candidates.json
    location_candidates_path = os.path.join(split_dir, 'disease_location_candidates.json')
    with open(location_candidates_path, 'r') as f:
        location_candidates = json.load(f)

    # 构建 disease_vocab_sizes（用于 disease-specific location head）
    disease_vocab_sizes = {}
    for disease, candidates in location_candidates.items():
        concept_count = len(candidates.get('concept_candidates', []))
        modifier_count = len(candidates.get('modifier_candidates', []))
        disease_vocab_sizes[disease] = concept_count + modifier_count

    logger.info(f"构建了 {len(disease_vocab_sizes)} 个疾病的 vocab_sizes")
    for disease, vocab_size in list(disease_vocab_sizes.items())[:5]:
        logger.info(f"  {disease}: {vocab_size}")
    logger.info(f"  ...")

    # 8. 验证路径
    validate_paths(merged_config)

    # 9. 自动检测疾病数量
    if merged_config.get('model', {}).get('num_diseases') == 'auto':
        data_path = merged_config['data'].get('data_path') or merged_config['data'].get('csv_path')
        data_format = merged_config['data'].get('data_format', 'auto')
        disease_count = auto_detect_disease_count(data_path, data_format)
        merged_config['model']['num_diseases'] = disease_count

    # 10. 将 disease_vocab_sizes 和 disease_order 添加到配置中
    merged_config.setdefault('model', {})['disease_vocab_sizes'] = disease_vocab_sizes
    merged_config.setdefault('model', {})['disease_order'] = disease_order

    # 11. 创建数据加载器
    logger.info("创建数据加载器...")
    logger.info(f"使用配置文件: {config_path}")

    # 创建args对象用于dataloader
    dataloader_args = create_args_namespace(**merged_config['data'], **merged_config['training'])

    try:
        from dataloader.dataloader import create_mimic_cxr_data_loaders

        train_loader, val_loader, test_loader = create_mimic_cxr_data_loaders(
            args=dataloader_args,
            split_dir=merged_config['data']['split_dir'],
            severity_to_id_json=merged_config['data'].get('severity_to_id_json'),
            disease_modifier_to_id_json=merged_config['data'].get('disease_modifier_to_id_json'),
            disease_anatomy_to_id_json=merged_config['data'].get('disease_anatomy_to_id_json'),
            disease_list=disease_order,
            load_masks=merged_config['data'].get('mask_dir') is not None,
            data_format=merged_config['data'].get('data_format', 'auto'),
            no_finding_downsample_ratio=merged_config['data'].get('no_finding_downsample_ratio'),
        )

        # 获取疾病词汇表
        disease_list = train_loader.dataset.get_disease_list()
        if disease_list != disease_order:
            logger.warning(f"DataLoader疾病顺序与disease_order.json不一致！")
            logger.warning(f"  DataLoader: {disease_list}")
            logger.warning(f"  disease_order.json: {disease_order}")
            logger.warning("  将使用 disease_order.json 的顺序")
            disease_list = disease_order  # 强制使用disease_order.json的顺序
        merged_config['model']['num_diseases'] = len(disease_list)
    except Exception as e:
        logger.error(f"创建数据加载器失败: {e}")
        raise

    # 12. 创建模型
    logger.info("创建模型...")
    try:
        model_config = create_model_config(merged_config)
        model_arch = get_model_architecture(merged_config)
        if model_arch == 'v1':
            from project.model_v1 import DACGV1Model

            logger.info("使用 DACG v1 精简架构（无分区提取/双重注意力/Transformer Encoder）")
            model = DACGV1Model.from_config(model_config)
        else:
            from project.model import DACGModel

            logger.info("使用 DACG v2 完整架构")
            model = DACGModel.from_config(model_config)
        model.print_model_info()
    except Exception as e:
        logger.error(f"创建模型失败: {e}")
        raise

    # 13. 创建训练器
    logger.info("创建训练器...")
    try:
        from project.trainer import create_trainer

        trainer_config = create_trainer_config(merged_config)
        trainer = create_trainer(
            model=model,
            train_loader=train_loader,
            val_loader=val_loader,
            disease_list=disease_list,
            config=trainer_config,
            test_loader=test_loader
        )
    except Exception as e:
        logger.error(f"创建训练器失败: {e}")
        raise

    # 14. 恢复训练（如果指定）
    resume_path = merged_config.get('experiment', {}).get('resume') or merged_config.get('resume')
    if resume_path:
        logger.info(f"恢复训练: {resume_path}")
        try:
            trainer.load_checkpoint(resume_path)
        except Exception as e:
            logger.error(f"恢复训练失败: {e}")
            raise

    # 15. 开始训练
    logger.info("开始训练...")
    logger.info(f"实验名称: {merged_config.get('experiment', {}).get('name', 'dacg_experiment')}")
    logger.info(f"训练轮数: {merged_config.get('training', {}).get('num_epochs', 100)}")
    logger.info(f"批次大小: {merged_config.get('training', {}).get('batch_size', 16)}")
    logger.info(f"学习率: {merged_config.get('training', {}).get('learning_rate', 1e-4)}")
    logger.info(f"S-Score启用: {merged_config.get('s_score', {}).get('enabled', True)}")

    try:
        trainer.train()
    except KeyboardInterrupt:
        logger.info("训练被用户中断")
    except Exception as e:
        logger.error(f"训练失败: {e}")
        raise

    # 16. 测试模型
    if test_loader is not None and merged_config.get('experiment', {}).get('test_after_train', True):
        logger.info("测试模型...")
        try:
            test_results = trainer.test()
            logger.info(f"测试结果: {test_results}")
        except Exception as e:
            logger.error(f"测试失败: {e}")
    
    logger.info("训练完成!")


if __name__ == "__main__":
    main()
