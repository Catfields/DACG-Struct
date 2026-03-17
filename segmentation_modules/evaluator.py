"""
评估和推理模块
包含模型评估、推理和可视化功能
"""

import os
import torch
import numpy as np
import cv2
from PIL import Image
import matplotlib
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix, accuracy_score, precision_score, recall_score, f1_score
import torch.nn.functional as F

from .config import *
from .unet_model import get_model
from .data_loader import create_data_loaders

plt.rcParams['font.sans-serif'] = ['AR PL UMing CN'] 
plt.rcParams['axes.unicode_minus'] = False


def overlay_mask_with_prob(image_rgb, mask, prob_map, alpha_min=0.2, alpha_max=0.7):
    """
    将预测mask按置信度动态透明度叠加到原图上。

    Args:
        image_rgb: ndarray, HxWx3, uint8 或 0~1 浮点
        mask: ndarray, HxW, uint8，类别编号
        prob_map: ndarray, HxW, float32/float64, 每像素最大类别概率 (0~1)
        alpha_min: float, 最低透明度（背景或低置信度区域）
        alpha_max: float, 最高透明度（高置信度区域）
    """
    if image_rgb.dtype != np.uint8:
        img = (np.clip(image_rgb, 0, 1) * 255).astype(np.uint8)
    else:
        img = image_rgb

    h, w = mask.shape
    color_mask = np.zeros((h, w, 3), dtype=np.uint8)
    for cls_id, color in CLASS_COLOR_MAP.items():
        if cls_id == 0:
            continue
        color_mask[mask == cls_id] = color

    alpha = np.clip(prob_map, 0.0, 1.0)
    alpha = alpha_min + (alpha_max - alpha_min) * alpha
    alpha_map = np.repeat(alpha[..., None], 3, axis=2).astype(np.float32)

    overlay = (alpha_map * color_mask.astype(np.float32) + (1.0 - alpha_map) * img.astype(np.float32)).astype(np.uint8)
    return overlay
class Evaluator:
    """评估器类"""

    def __init__(self, model_path='best_model.pth'):
        """
        初始化评估器

        Args:
            model_path: 模型文件路径
        """
        self.device = torch.device(DEVICE)
        self.model = None

        # 加载模型
        self.load_model(model_path)
        self.model.eval()

        print(f"评估器初始化完成，加载模型: {model_path}")

    def load_model(self, model_path):
        """加载模型"""
        filepath = self._resolve_model_path(model_path)
        checkpoint = torch.load(filepath, map_location=self.device)
        model_type = checkpoint.get('model_type', 'unet')
        self.model = get_model(model_type).to(self.device)
        self.model.load_state_dict(checkpoint['model_state_dict'])

        print(f"模型加载成功: {model_path} (model_type={model_type})")

    def _resolve_model_path(self, model_path):
        """尽量灵活地解析模型权重路径"""
        if os.path.isabs(model_path) and os.path.exists(model_path):
            return model_path

        base_dir = os.path.dirname(__file__)
        models_root = os.path.join(base_dir, 'models')
        candidates = [
            os.path.join(base_dir, model_path),
            os.path.join(models_root, model_path),
            os.path.join(MODEL_SAVE_DIR, model_path),
        ]

        for cand in candidates:
            if os.path.exists(cand):
                return cand

        raise FileNotFoundError(
            f"无法找到模型文件: {model_path}. "
            f"尝试的路径: {', '.join(candidates)}"
        )

    def compute_metrics_from_counts(self, intersection, pred_area, target_area, correct_pixels, total_pixels):
        """根据像素统计计算整体与逐类指标"""
        per_class_metrics = []
        for cls_idx in range(NUM_CLASSES):
            inter = intersection[cls_idx]
            pred_cnt = pred_area[cls_idx]
            tgt_cnt = target_area[cls_idx]

            precision = inter / pred_cnt if pred_cnt > 0 else 0.0
            recall = inter / tgt_cnt if tgt_cnt > 0 else 0.0
            f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

            dice_denom = pred_cnt + tgt_cnt
            dice = (2 * inter) / dice_denom if dice_denom > 0 else 0.0

            iou_denom = pred_cnt + tgt_cnt - inter
            iou = inter / iou_denom if iou_denom > 0 else 0.0

            per_class_metrics.append({
                'class': CLASS_NAMES[cls_idx] if cls_idx < len(CLASS_NAMES) else f'class_{cls_idx}',
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'dice': dice,
                'iou': iou,
                'support': tgt_cnt,
            })

        # 排除背景计算平均值
        foreground_indices = []
        for idx in range(NUM_CLASSES):
            if idx < len(CLASS_NAMES):
                if CLASS_NAMES[idx] == "background":
                    continue
            elif idx == 0:
                continue
            foreground_indices.append(idx)
        if not foreground_indices:
            foreground_indices = [idx for idx in range(1, NUM_CLASSES)]

        def mean_on_indices(key):
            values = [per_class_metrics[idx][key] for idx in foreground_indices if not np.isnan(per_class_metrics[idx][key])]
            return float(np.mean(values)) if values else 0.0

        avg_metrics = {
            'accuracy': correct_pixels / total_pixels if total_pixels > 0 else 0.0,
            'precision': mean_on_indices('precision'),
            'recall': mean_on_indices('recall'),
            'f1': mean_on_indices('f1'),
            'dice': mean_on_indices('dice'),
            'iou': mean_on_indices('iou'),
        }

        overall_metrics = {
            'per_class': per_class_metrics,
            'global_accuracy': avg_metrics['accuracy'],
        }

        return avg_metrics, overall_metrics

    def evaluate_dataset(self, test_loader):
        """评估整个数据集"""
        print("开始评估测试集...")

        intersection = np.zeros(NUM_CLASSES, dtype=np.float64)
        pred_area = np.zeros(NUM_CLASSES, dtype=np.float64)
        target_area = np.zeros(NUM_CLASSES, dtype=np.float64)
        total_pixels = 0
        correct_pixels = 0

        with torch.no_grad():
            for batch_idx, (images, masks) in enumerate(test_loader):
                images = images.to(self.device, non_blocking=True)
                masks = masks.to(self.device, non_blocking=True)

                # 预测
                outputs = self.model(images)
                probs = torch.softmax(outputs, dim=1)
                preds = torch.argmax(probs, dim=1)

                correct_pixels += (preds == masks).sum().item()
                total_pixels += masks.numel()

                for cls_idx in range(NUM_CLASSES):
                    pred_cls = preds == cls_idx
                    target_cls = masks == cls_idx

                    inter = torch.logical_and(pred_cls, target_cls).sum().item()
                    pred_cnt = pred_cls.sum().item()
                    target_cnt = target_cls.sum().item()

                    intersection[cls_idx] += inter
                    pred_area[cls_idx] += pred_cnt
                    target_area[cls_idx] += target_cnt

                if batch_idx % 10 == 0:
                    print(f"已处理 {batch_idx * len(images)} 个样本")

        avg_metrics, overall_metrics = self.compute_metrics_from_counts(
            intersection, pred_area, target_area, correct_pixels, total_pixels
        )

        print("评估结果 (类别平均，忽略背景):")
        print(f"- 准确率: {avg_metrics['accuracy']:.4f}")
        print(f"- 精确率: {avg_metrics['precision']:.4f}")
        print(f"- 召回率: {avg_metrics['recall']:.4f}")
        print(f"- F1: {avg_metrics['f1']:.4f}")
        print(f"- Dice: {avg_metrics['dice']:.4f}")
        print(f"- IoU: {avg_metrics['iou']:.4f}")

        print("按类别指标:")
        for cls_metric in overall_metrics['per_class']:
            class_name = cls_metric['class']
            print(f"  {class_name:>12s} | Dice: {cls_metric['dice']:.4f} | IoU: {cls_metric['iou']:.4f} | "
                  f"Precision: {cls_metric['precision']:.4f} | Recall: {cls_metric['recall']:.4f} | "
                  f"F1: {cls_metric['f1']:.4f} | 像素数: {int(cls_metric['support'])}")

        return avg_metrics, overall_metrics

    def predict_single_image(self, image_path):
        """对单张图像进行预测"""
        # 加载图像
        image = Image.open(image_path).convert('RGB')
        original_size = image.size  # (width, height)
        image_resized = image.resize((IMG_WIDTH, IMG_HEIGHT), resample=Image.BILINEAR)
        image_array = np.array(image_resized) / 255.0
        image_tensor = torch.from_numpy(image_array).permute(2, 0, 1).float()

        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
        image_tensor = (image_tensor - mean) / std
        image_tensor = image_tensor.unsqueeze(0).to(self.device)

        # 预测
        with torch.no_grad():
            output = self.model(image_tensor)
            prob = torch.softmax(output, dim=1)[0]  # (C, H, W)
            pred = torch.argmax(prob, dim=0)

        pred_np = pred.cpu().numpy().astype(np.uint8)
        pred_img = Image.fromarray(pred_np, mode='L').resize(original_size, resample=Image.NEAREST)
        pred_resized = np.array(pred_img, dtype=np.uint8)

        max_prob = torch.max(prob, dim=0).values.cpu().numpy()
        max_prob_img = Image.fromarray(max_prob.astype(np.float32), mode='F').resize(original_size, resample=Image.BILINEAR)
        max_prob_resized = np.array(max_prob_img)

        return pred_resized, max_prob_resized

    def visualize_prediction(self, image_path, save_path=None):
        """可视化预测结果"""
        # 预测
        pred_mask, prob_map = self.predict_single_image(image_path)

        # 加载原图
        original_image = Image.open(image_path).convert('RGB')
        original_image_np = np.array(original_image)

        # 叠加可视化
        overlay = overlay_mask_with_prob(original_image_np, pred_mask, prob_map, alpha_min=0.2, alpha_max=0.7)

        # 创建可视化
        fig, axes = plt.subplots(1, 4, figsize=(20, 5))
        cmap = matplotlib.cm.get_cmap('tab10', NUM_CLASSES)

        # 原图
        axes[0].imshow(original_image_np)
        axes[0].set_title('原始图像')
        axes[0].axis('off')

        # 叠加图
        axes[1].imshow(overlay)
        axes[1].set_title('叠加预测 (动态透明度)')
        axes[1].axis('off')

        # 预测掩膜
        im_mask = axes[2].imshow(pred_mask, cmap=cmap, vmin=0, vmax=NUM_CLASSES - 1)
        axes[2].set_title('预测掩膜')
        axes[2].axis('off')
        cbar = fig.colorbar(im_mask, ax=axes[2], fraction=0.046, pad=0.04, ticks=range(NUM_CLASSES))
        cbar.ax.set_yticklabels(CLASS_NAMES[:NUM_CLASSES] if CLASS_NAMES else [str(i) for i in range(NUM_CLASSES)])

        # 最大类别置信度
        axes[3].imshow(prob_map, cmap='viridis')
        axes[3].set_title('最大类别概率')
        axes[3].axis('off')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"可视化结果已保存: {save_path}")
        else:
            plt.show()

        plt.close()

    def batch_visualize(self, test_loader, num_samples=5, save_dir=None):
        """批量可视化预测结果"""
        print(f"批量可视化 {num_samples} 个样本...")

        if save_dir:
            os.makedirs(save_dir, exist_ok=True)

        with torch.no_grad():
            for batch_idx, (images, masks) in enumerate(test_loader):
                if batch_idx * len(images) >= num_samples:
                    break

                images = images.to(self.device, non_blocking=True)
                masks = masks.to(self.device, non_blocking=True)

                # 预测
                outputs = self.model(images)
                probs = torch.softmax(outputs, dim=1)
                preds = torch.argmax(probs, dim=1)
                max_probs = torch.max(probs, dim=1).values

                # 转换为numpy
                images_np = images.cpu().numpy()
                masks_np = masks.cpu().numpy()
                preds_np = preds.cpu().numpy()
                max_probs_np = max_probs.cpu().numpy()

                # 可视化每个样本
                batch_size = images_np.shape[0]
                for i in range(min(batch_size, num_samples - batch_idx * batch_size)):
                    self.visualize_sample(
                        images_np[i], masks_np[i], preds_np[i], max_probs_np[i],
                        save_dir=save_dir, sample_idx=batch_idx * batch_size + i
                    )

    def visualize_sample(self, image, mask, pred, max_prob, save_dir=None, sample_idx=0):
        """可视化单个样本"""
        fig, axes = plt.subplots(1, 5, figsize=(20, 4))
        cmap = matplotlib.cm.get_cmap('tab10', NUM_CLASSES)
        norm = matplotlib.colors.BoundaryNorm(range(NUM_CLASSES + 1), cmap.N)

        # 反归一化图像
        mean = np.array([0.485, 0.456, 0.406])
        std = np.array([0.229, 0.224, 0.225])
        image = image * std[:, None, None] + mean[:, None, None]
        image = np.clip(image, 0, 1)
        image_uint8 = (image.transpose(1, 2, 0) * 255).astype(np.uint8)
        overlay = overlay_mask_with_prob(image_uint8, pred.astype(np.uint8), max_prob, alpha_min=0.2, alpha_max=0.7)

        # 原图
        axes[0].imshow(image.transpose(1, 2, 0))
        axes[0].set_title('原始图像')
        axes[0].axis('off')

        # 叠加预测
        axes[1].imshow(overlay)
        axes[1].set_title('叠加预测')
        axes[1].axis('off')

        # 真实掩膜
        gt_im = axes[2].imshow(mask, cmap=cmap, norm=norm)
        axes[2].set_title('真实掩膜')
        axes[2].axis('off')

        # 预测掩膜
        pred_im = axes[3].imshow(pred, cmap=cmap, norm=norm)
        axes[3].set_title('预测掩膜')
        axes[3].axis('off')

        # 置信度
        axes[4].imshow(max_prob, cmap='viridis')
        axes[4].set_title('最大类别概率')
        axes[4].axis('off')

        # 颜色图例
        cbar = fig.colorbar(pred_im, ax=axes[3], fraction=0.046, pad=0.04, ticks=range(NUM_CLASSES))
        cbar.ax.set_yticklabels(CLASS_NAMES[:NUM_CLASSES] if CLASS_NAMES else [str(i) for i in range(NUM_CLASSES)])

        plt.tight_layout()

        if save_dir:
            save_path = os.path.join(save_dir, f'sample_{sample_idx:04d}.png')
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        else:
            plt.show()

        plt.close()

    def save_evaluation_report(self, avg_metrics, overall_metrics, save_path=None):
        """保存评估报告"""
        if save_path is None:
            save_path = os.path.join(RESULTS_DIR, 'evaluation_report.txt')

        per_class_lines = []
        for metric in overall_metrics['per_class']:
            per_class_lines.append(
                f"  - {metric['class']:<12s} | Precision: {metric['precision']:.4f} | "
                f"Recall: {metric['recall']:.4f} | F1: {metric['f1']:.4f} | "
                f"Dice: {metric['dice']:.4f} | IoU: {metric['iou']:.4f} | 像素数: {int(metric['support'])}"
            )
        per_class_text = "\n".join(per_class_lines)

        report = f"""
U-Net医学图像分割评估报告
=========================

数据集信息:
- 图像尺寸: {IMG_HEIGHT}x{IMG_WIDTH}
- 通道数: {IMG_CHANNELS}
- 类别数: {NUM_CLASSES}

总体指标 (取平均，忽略背景):
- 准确率: {avg_metrics['accuracy']:.4f}
- 精确率: {avg_metrics['precision']:.4f}
- 召回率: {avg_metrics['recall']:.4f}
- F1分数: {avg_metrics['f1']:.4f}
- Dice系数: {avg_metrics['dice']:.4f}
- IoU: {avg_metrics['iou']:.4f}

每类详细指标:
{per_class_text}

评估完成时间: {np.datetime64('now')}
"""

        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"评估报告已保存: {save_path}")

def main():
    """主评估函数"""
    print("开始U-Net模型评估...")

    # 创建评估器
    evaluator = Evaluator('best_model.pth')

    # 创建测试数据加载器
    _, _, test_loader = create_data_loaders()

    # 评估测试集
    avg_metrics, overall_metrics = evaluator.evaluate_dataset(test_loader)

    # 保存评估报告
    evaluator.save_evaluation_report(avg_metrics, overall_metrics)

    # 批量可视化
    viz_dir = os.path.join(RESULTS_DIR, 'visualizations')
    evaluator.batch_visualize(test_loader, num_samples=10, save_dir=viz_dir)

    print("评估完成！")

if __name__ == "__main__":
    main()
