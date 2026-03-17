"""
U-Net医学图像分割主程序
提供命令行接口用于训练、评估和推理
"""

import argparse
import os
import sys

def train(args):
    """训练模型"""
    print(f"开始训练模型: {args.model_type}")

    try:
        from .trainer import Trainer
        from .data_loader import create_data_loaders
    except ImportError:
        from trainer import Trainer
        from data_loader import create_data_loaders

    # 创建数据加载器
    train_loader, val_loader, _ = create_data_loaders(batch_size=args.batch_size)

    # 创建训练器
    trainer = Trainer(
        model_type=args.model_type,
        loss_type=args.loss_type,
        learning_rate=args.learning_rate
    )
    results_dir = getattr(trainer, 'results_dir', RESULTS_DIR)
    print(f"训练输出目录: {results_dir}")

    # 开始训练
    trainer.train(train_loader, val_loader, epochs=args.epochs)

    # 绘制训练历史
    trainer.plot_training_history()

    # 保存训练信息
    trainer.save_training_info()

    print(f"训练完成！曲线与日志保存在: {results_dir}")

def evaluate(args):
    """评估模型"""
    print(f"开始评估模型，检查点: {args.model_path}")

    try:
        from .evaluator import Evaluator
        from .data_loader import create_data_loaders
    except ImportError:
        from evaluator import Evaluator
        from data_loader import create_data_loaders

    # 根据模型路径推断结果输出目录
    base_dir = os.path.dirname(__file__)
    results_root = os.path.join(base_dir, 'results')
    model_path_str = str(args.model_path)
    model_path_lower = model_path_str.lower()
    if 'attention_unet' in model_path_lower:
        results_dir = os.path.join(results_root, 'attention_unet_results')
    elif 'upp' in model_path_lower or 'unetpp' in model_path_lower:
        results_dir = os.path.join(results_root, 'upp_results')
    else:
        results_dir = os.path.join(results_root, 'unet_results')
    os.makedirs(results_dir, exist_ok=True)

    # 创建评估器
    evaluator = Evaluator(args.model_path)

    # 创建测试数据加载器
    _, _, test_loader = create_data_loaders()

    # 评估测试集
    avg_metrics, overall_metrics = evaluator.evaluate_dataset(test_loader)

    # 保存评估报告
    report_path = os.path.join(results_dir, 'evaluation_report.txt')
    evaluator.save_evaluation_report(avg_metrics, overall_metrics, save_path=report_path)

    # 批量可视化
    if args.visualize:
        viz_dir = os.path.join(results_dir, 'visualizations')
        evaluator.batch_visualize(test_loader, num_samples=args.num_samples, save_dir=viz_dir)
        print(f"预测可视化结果保存至: {viz_dir}")

    print("评估完成！")

def predict(args):
    """单张图像推理"""
    print(f"对图像 {args.image_path} 进行推理（模型: {args.model_path}）...")

    try:
        from .evaluator import Evaluator
    except ImportError:
        from evaluator import Evaluator

    # 创建评估器
    evaluator = Evaluator(args.model_path)

    # 预测
    pred_mask, prob_map = evaluator.predict_single_image(args.image_path)

    # 保存结果
    import numpy as np
    from PIL import Image
    try:
        from .config import CLASS_COLOR_MAP
    except ImportError:
        from config import CLASS_COLOR_MAP

    mask_save_path = args.output_path if args.output_path else 'prediction_mask.png'
    label_map_path = mask_save_path.replace('.png', '_labels.png')

    # 保存标签编号图 (0...NUM_CLASSES-1)
    label_image = Image.fromarray(pred_mask.astype(np.uint8), mode='L')
    label_image.save(label_map_path)
    print(f"标签编号掩膜已保存: {label_map_path}")

    # 生成彩色可视化掩膜
    palette = np.zeros((NUM_CLASSES, 3), dtype=np.uint8)
    for idx in range(NUM_CLASSES):
        default_color = (
            int(255 * idx / max(1, NUM_CLASSES - 1)),
            int(128 * idx / max(1, NUM_CLASSES - 1)),
            int(64 * idx / max(1, NUM_CLASSES - 1)),
        )
        color = CLASS_COLOR_MAP.get(idx, default_color)
        palette[idx] = np.array(color, dtype=np.uint8)
    color_mask = palette[pred_mask]
    Image.fromarray(color_mask).save(mask_save_path)
    print(f"彩色掩膜已保存: {mask_save_path}")

    # 保存最大概率图
    prob_save_path = mask_save_path.replace('.png', '_prob.png')
    prob_min, prob_max = float(prob_map.min()), float(prob_map.max())
    if prob_max - prob_min < 1e-6:
        prob_normalized = np.zeros_like(prob_map, dtype=np.uint8)
    else:
        prob_normalized = ((prob_map - prob_min) / (prob_max - prob_min) * 255).astype(np.uint8)
    Image.fromarray(prob_normalized).save(prob_save_path)
    print(f"最大概率图已保存: {prob_save_path}")

    # 可视化
    if args.visualize:
        evaluator.visualize_prediction(args.image_path, mask_save_path.replace('.png', '_vis.png'))

    print("推理完成！")

def test_components():
    """测试各组件功能"""
    print("测试组件功能...")

    try:
        print("1. 测试数据加载...")
        try:
            from .data_loader import test_data_loading
        except ImportError:
            from data_loader import test_data_loading
        test_data_loading()

        print("\n2. 测试模型...")
        try:
            from .unet_model import test_model
        except ImportError:
            from unet_model import test_model
        test_model()

        print("\n3. 测试损失函数...")
        try:
            from .losses import test_loss_functions
        except ImportError:
            from losses import test_loss_functions
        test_loss_functions()

        print("\n所有组件测试完成！")
    except Exception as e:
        print(f"测试失败: {e}")
        sys.exit(1)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='U-Net医学图像分割')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # 训练命令
    train_parser = subparsers.add_parser('train', help='训练模型')
    train_parser.add_argument('--model_type', type=str, default='unet', choices=['unet', 'unet++','attention_unet'],
                           help='模型类型')
    train_parser.add_argument('--loss_type', type=str, default='cross_entropy',
                           choices=['cross_entropy', 'ce_dice_mc', 'dice_mc', 'combined'],
                           help='损失函数类型')
    train_parser.add_argument('--epochs', type=int, default=EPOCHS, help='训练轮数')
    train_parser.add_argument('--batch_size', type=int, default=BATCH_SIZE, help='批次大小')
    train_parser.add_argument('--learning_rate', type=float, default=LEARNING_RATE, help='学习率')

    # 评估命令
    eval_parser = subparsers.add_parser('evaluate', help='评估模型')
    eval_parser.add_argument('--model_path', type=str, default='best_model.pth',
                           help='模型文件路径')
    eval_parser.add_argument('--visualize', action='store_true', help='可视化预测结果')
    eval_parser.add_argument('--num_samples', type=int, default=10, help='可视化样本数量')

    # 推理命令
    predict_parser = subparsers.add_parser('predict', help='单张图像推理')
    predict_parser.add_argument('image_path', type=str, help='输入图像路径')
    predict_parser.add_argument('--model_path', type=str, default='best_model.pth',
                              help='模型文件路径')
    predict_parser.add_argument('--output_path', type=str, help='输出掩膜路径')
    predict_parser.add_argument('--visualize', action='store_true', help='可视化结果')

    # 测试命令
    test_parser = subparsers.add_parser('test', help='测试组件功能')

    args = parser.parse_args()

    if args.command == 'train':
        train(args)
    elif args.command == 'evaluate':
        evaluate(args)
    elif args.command == 'predict':
        predict(args)
    elif args.command == 'test':
        test_components()
    else:
        parser.print_help()

if __name__ == "__main__":
    # 导入配置变量
    try:
        from .config import *
    except ImportError:
        from config import *
    main()
