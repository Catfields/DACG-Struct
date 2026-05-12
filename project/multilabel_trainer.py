"""
Trainer for single-task multi-label DACG training.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.amp import GradScaler, autocast
from torch.utils.data import DataLoader

if TYPE_CHECKING:
    from project.multilabel_model import MultiLabelDACGModel

try:
    from tqdm.auto import tqdm
except Exception:
    tqdm = None


@dataclass
class MultiLabelTrainerConfig:
    learning_rate: float = 1e-4
    weight_decay: float = 1e-5
    max_grad_norm: float = 1.0
    num_epochs: int = 100
    eval_interval: int = 1
    log_interval: int = 50
    threshold: float = 0.5
    save_dir: str = "./checkpoints_multilabel"
    log_dir: str = "./logs"
    experiment_name: str = "dacg_multilabel"
    device: str = "auto"
    use_amp: bool = True
    patience: int = 10
    min_delta: float = 1e-4
    pos_weight: Optional[List[float]] = None
    loss_type: str = "focal"
    focal_alpha: Optional[float] = None
    focal_gamma: float = 2.0
    logit_clip: float = 20.0
    progress_bar: bool = True


class MultiLabelFocalLoss(nn.Module):
    """Numerically stable focal loss for multi-label classification."""

    def __init__(
        self,
        alpha: Optional[float] = 0.25,
        gamma: float = 2.0,
        pos_weight: Optional[torch.Tensor] = None,
    ):
        super().__init__()
        self.alpha = alpha
        self.gamma = float(gamma)
        if pos_weight is not None:
            self.register_buffer("pos_weight", pos_weight)
        else:
            self.pos_weight = None

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        bce_loss = F.binary_cross_entropy_with_logits(
            logits,
            targets,
            reduction="none",
            pos_weight=self.pos_weight,
        )
        probs = torch.sigmoid(logits)
        p_t = probs * targets + (1.0 - probs) * (1.0 - targets)
        focal_weight = torch.pow(torch.clamp(1.0 - p_t, min=0.0, max=1.0), self.gamma)

        if self.alpha is not None:
            alpha_t = self.alpha * targets + (1.0 - self.alpha) * (1.0 - targets)
            focal_weight = focal_weight * alpha_t

        return (focal_weight * bce_loss).mean()


class MultiLabelDACGTrainer:
    def __init__(
        self,
        model: MultiLabelDACGModel,
        train_loader: DataLoader,
        val_loader: DataLoader,
        config: MultiLabelTrainerConfig,
        label_names: List[str],
        test_loader: Optional[DataLoader] = None,
    ):
        self.model = model
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.test_loader = test_loader
        self.config = config
        self.label_names = list(label_names)

        self.device = self._resolve_device(config.device)
        self.model.to(self.device)

        pos_weight = None
        if config.pos_weight is not None:
            pos_weight = torch.tensor(config.pos_weight, dtype=torch.float32, device=self.device)
        self.criterion = self._build_criterion(pos_weight)

        self.optimizer = optim.AdamW(
            self.model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
            betas=(0.9, 0.999),
            eps=1e-8,
        )
        self.scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
            self.optimizer,
            T_0=10,
            T_mult=2,
            eta_min=1e-6,
        )

        self.use_amp = config.use_amp and self.device.type == "cuda"
        self.scaler = GradScaler("cuda") if self.use_amp else None

        self.current_epoch = 0
        self.best_val_loss = float("inf")
        self.epochs_without_improvement = 0
        self.training_history = {"train": [], "val": []}

        Path(config.save_dir).mkdir(parents=True, exist_ok=True)
        Path(config.log_dir).mkdir(parents=True, exist_ok=True)

        print("多标签训练器初始化完成")
        print(f"设备: {self.device}")
        print(f"混合精度: {self.use_amp}")
        print(f"标签数量: {len(self.label_names)}")
        print(f"损失函数: {self.config.loss_type}")

    def _build_criterion(self, pos_weight: Optional[torch.Tensor]) -> nn.Module:
        loss_type = str(self.config.loss_type).lower()
        if loss_type in {"bce", "bce_with_logits"}:
            return nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        if loss_type in {"focal", "focal_loss"}:
            return MultiLabelFocalLoss(
                alpha=self.config.focal_alpha,
                gamma=self.config.focal_gamma,
                pos_weight=pos_weight,
            )
        raise ValueError(f"不支持的多标签 loss_type={self.config.loss_type}")

    def _resolve_device(self, device: str) -> torch.device:
        if device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device(device)

    def _prepare_masks(self, images: torch.Tensor) -> torch.Tensor:
        batch_size, _, height, width = images.shape
        return torch.zeros(batch_size, 4, height, width, dtype=images.dtype, device=self.device)

    def _batch_to_device(self, batch: Dict) -> Tuple[torch.Tensor, torch.Tensor]:
        images = batch["images"].to(self.device, non_blocking=True)
        labels = batch["labels"].to(self.device, non_blocking=True)
        return images, labels

    def _sanitize_logits(self, logits: torch.Tensor) -> torch.Tensor:
        clip = float(self.config.logit_clip)
        if not torch.isfinite(logits).all():
            logits = torch.nan_to_num(logits, nan=0.0, posinf=clip, neginf=-clip)
        if clip > 0:
            logits = torch.clamp(logits, min=-clip, max=clip)
        return logits

    def _batch_acc_from_logits(self, logits: torch.Tensor, labels: torch.Tensor) -> float:
        logits = self._sanitize_logits(logits.detach())
        labels = labels.detach()
        preds = (torch.sigmoid(logits) >= self.config.threshold).to(labels.dtype)
        return float((preds == labels).float().mean().detach().cpu())

    def _use_progress_bar(self) -> bool:
        return bool(self.config.progress_bar and tqdm is not None)

    def _metrics_from_logits(self, logits: torch.Tensor, labels: torch.Tensor) -> Dict[str, float]:
        logits = self._sanitize_logits(logits)
        probs = torch.sigmoid(logits)
        preds = (probs >= self.config.threshold).to(labels.dtype)
        labels = labels.to(preds.dtype)

        tp = (preds * labels).sum(dim=0)
        fp = (preds * (1.0 - labels)).sum(dim=0)
        fn = ((1.0 - preds) * labels).sum(dim=0)
        tn = ((1.0 - preds) * (1.0 - labels)).sum(dim=0)

        eps = 1e-8
        micro_tp = tp.sum()
        micro_fp = fp.sum()
        micro_fn = fn.sum()
        micro_tn = tn.sum()
        micro_precision = micro_tp / (micro_tp + micro_fp + eps)
        micro_recall = micro_tp / (micro_tp + micro_fn + eps)
        micro_specificity = micro_tn / (micro_tn + micro_fp + eps)
        micro_f1 = 2 * micro_precision * micro_recall / (micro_precision + micro_recall + eps)
        balanced_acc = 0.5 * (micro_recall + micro_specificity)

        precision = tp / (tp + fp + eps)
        recall = tp / (tp + fn + eps)
        f1 = 2 * precision * recall / (precision + recall + eps)

        element_acc = (preds == labels).float().mean()
        exact_match = (preds == labels).all(dim=1).float().mean()
        pred_pos_rate = preds.float().mean()
        true_pos_rate = labels.float().mean()

        return {
            "acc": float(element_acc.detach().cpu()),
            "balanced_acc": float(balanced_acc.detach().cpu()),
            "precision": float(micro_precision.detach().cpu()),
            "recall": float(micro_recall.detach().cpu()),
            "specificity": float(micro_specificity.detach().cpu()),
            "micro_f1": float(micro_f1.detach().cpu()),
            "macro_f1": float(f1.mean().detach().cpu()),
            "element_acc": float(element_acc.detach().cpu()),
            "exact_match": float(exact_match.detach().cpu()),
            "pred_pos_rate": float(pred_pos_rate.detach().cpu()),
            "true_pos_rate": float(true_pos_rate.detach().cpu()),
        }

    def train_epoch(self) -> Dict[str, float]:
        self.model.train()
        total_loss = 0.0
        total_acc = 0.0
        processed_batches = 0
        all_logits = []
        all_labels = []
        num_batches = len(self.train_loader)

        iterator = self.train_loader
        progress = None
        if self._use_progress_bar():
            progress = tqdm(
                iterator,
                total=num_batches,
                desc=f"Train {self.current_epoch + 1}/{self.config.num_epochs}",
                dynamic_ncols=True,
                leave=True,
            )
            iterator = progress

        for batch_idx, batch in enumerate(iterator):
            images, labels = self._batch_to_device(batch)
            masks = self._prepare_masks(images)

            self.optimizer.zero_grad(set_to_none=True)
            with autocast("cuda", enabled=self.use_amp):
                outputs = self.model(images, masks)
                logits = self._sanitize_logits(outputs["logits"])
                loss = self.criterion(logits, labels)

            if not torch.isfinite(loss):
                print("Warning: non-finite multilabel loss after logit sanitization; skipping batch")
                continue

            if self.use_amp:
                self.scaler.scale(loss).backward()
                if self.config.max_grad_norm > 0:
                    self.scaler.unscale_(self.optimizer)
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)
                self.scaler.step(self.optimizer)
                self.scaler.update()
            else:
                loss.backward()
                if self.config.max_grad_norm > 0:
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)
                self.optimizer.step()

            batch_loss = float(loss.detach().cpu())
            batch_acc = self._batch_acc_from_logits(logits, labels)
            total_loss += batch_loss
            total_acc += batch_acc
            processed_batches += 1
            all_logits.append(logits.detach().cpu())
            all_labels.append(labels.detach().cpu())

            current_lr = self.optimizer.param_groups[0]["lr"]
            running_loss = total_loss / max(1, processed_batches)
            running_acc = total_acc / max(1, processed_batches)
            if progress is not None:
                progress.set_postfix(
                    loss=f"{running_loss:.4f}",
                    acc=f"{running_acc:.4f}",
                    lr=f"{current_lr:.2e}",
                )
            elif batch_idx % self.config.log_interval == 0:
                print(
                    f"Epoch [{self.current_epoch + 1}/{self.config.num_epochs}] "
                    f"Batch [{batch_idx}/{num_batches}] "
                    f"Loss: {batch_loss:.4f} "
                    f"Acc: {batch_acc:.4f} "
                    f"LR: {current_lr:.6f}"
                )

        metrics = {
            "loss": total_loss / max(1, processed_batches),
            "acc": total_acc / max(1, processed_batches),
        }
        if all_logits:
            metrics.update(self._metrics_from_logits(torch.cat(all_logits, dim=0), torch.cat(all_labels, dim=0)))
        return metrics

    def evaluate(self, loader: DataLoader, split_name: str) -> Dict[str, float]:
        self.model.eval()
        total_loss = 0.0
        total_acc = 0.0
        all_logits = []
        all_labels = []
        num_batches = len(loader)
        processed_batches = 0

        with torch.no_grad():
            iterator = loader
            progress = None
            if self._use_progress_bar():
                progress = tqdm(
                    iterator,
                    total=num_batches,
                    desc=split_name.capitalize(),
                    dynamic_ncols=True,
                    leave=False,
                )
                iterator = progress

            for batch_idx, batch in enumerate(iterator):
                images, labels = self._batch_to_device(batch)
                masks = self._prepare_masks(images)

                with autocast("cuda", enabled=self.use_amp):
                    outputs = self.model(images, masks)
                    logits = self._sanitize_logits(outputs["logits"])
                    loss = self.criterion(logits, labels)

                batch_loss = float(loss.detach().cpu())
                batch_acc = self._batch_acc_from_logits(logits, labels)
                total_loss += batch_loss
                total_acc += batch_acc
                processed_batches += 1
                all_logits.append(logits.detach().cpu())
                all_labels.append(labels.detach().cpu())

                running_loss = total_loss / max(1, processed_batches)
                running_acc = total_acc / max(1, processed_batches)
                if progress is not None:
                    progress.set_postfix(loss=f"{running_loss:.4f}", acc=f"{running_acc:.4f}")
                elif split_name == "test" and batch_idx % 50 == 0:
                    print(f"测试批次 [{batch_idx}/{num_batches}]")

        metrics = {
            "loss": total_loss / max(1, processed_batches),
            "acc": total_acc / max(1, processed_batches),
        }
        if all_logits:
            metrics.update(self._metrics_from_logits(torch.cat(all_logits, dim=0), torch.cat(all_labels, dim=0)))
        return metrics

    def _print_epoch_summary(self, train_metrics: Dict[str, float], val_metrics: Dict[str, float]) -> None:
        print(f"\nEpoch [{self.current_epoch + 1}/{self.config.num_epochs}] 完成:")
        print(f"  训练损失: {train_metrics['loss']:.4f}")
        print(f"  训练 acc: {train_metrics.get('acc', 0.0):.4f}")
        print(f"  验证损失: {val_metrics['loss']:.4f}")
        print(f"  验证 acc: {val_metrics.get('acc', 0.0):.4f}")
        print(f"  验证 balanced_acc: {val_metrics.get('balanced_acc', 0.0):.4f}")
        print(f"  验证 micro-F1: {val_metrics.get('micro_f1', 0.0):.4f}")
        print(f"  验证 macro-F1: {val_metrics.get('macro_f1', 0.0):.4f}")
        print(f"  验证 precision/recall: {val_metrics.get('precision', 0.0):.4f}/{val_metrics.get('recall', 0.0):.4f}")
        print(f"  验证 pred_pos_rate/true_pos_rate: {val_metrics.get('pred_pos_rate', 0.0):.4f}/{val_metrics.get('true_pos_rate', 0.0):.4f}")
        print(f"  最佳验证损失: {self.best_val_loss:.4f}")

    def save_checkpoint(self, is_best: bool = False) -> None:
        checkpoint = {
            "epoch": self.current_epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict(),
            "best_val_loss": self.best_val_loss,
            "training_history": self.training_history,
            "config": self.config,
            "label_names": self.label_names,
        }
        if self.use_amp:
            checkpoint["scaler_state_dict"] = self.scaler.state_dict()

        torch.save(checkpoint, Path(self.config.save_dir) / "last.pth")
        if is_best:
            best_path = Path(self.config.save_dir) / "best.pth"
            torch.save(checkpoint, best_path)
            print(f"保存最佳模型: {best_path}")

    def load_checkpoint(self, checkpoint_path: str) -> None:
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        if "scaler_state_dict" in checkpoint and self.use_amp:
            self.scaler.load_state_dict(checkpoint["scaler_state_dict"])
        self.current_epoch = int(checkpoint["epoch"])
        self.best_val_loss = float(checkpoint["best_val_loss"])
        self.training_history = checkpoint.get("training_history", self.training_history)
        print(f"加载检查点: {checkpoint_path}")
        print(f"恢复到epoch {self.current_epoch}")

    def should_early_stop(self, current_val_loss: float) -> bool:
        if current_val_loss < self.best_val_loss - self.config.min_delta:
            self.best_val_loss = current_val_loss
            self.epochs_without_improvement = 0
            return False
        self.epochs_without_improvement += 1
        return self.epochs_without_improvement >= self.config.patience

    def train(self) -> None:
        print("开始多标签训练...")
        print(f"总epoch数: {self.config.num_epochs}")
        start_time = time.time()

        for epoch in range(self.current_epoch, self.config.num_epochs):
            self.current_epoch = epoch
            train_metrics = self.train_epoch()
            self.scheduler.step()

            if (epoch + 1) % self.config.eval_interval == 0:
                val_metrics = self.evaluate(self.val_loader, "valid")
                self.training_history["train"].append(train_metrics)
                self.training_history["val"].append(val_metrics)
                self._print_epoch_summary(train_metrics, val_metrics)

                improved = val_metrics["loss"] < self.best_val_loss - self.config.min_delta
                self.save_checkpoint(is_best=improved)
                if self.should_early_stop(val_metrics["loss"]):
                    print(f"早停触发，在epoch {epoch + 1}")
                    break
            else:
                self.training_history["train"].append(train_metrics)

        total_time = time.time() - start_time
        print(f"\n多标签训练完成! 总用时: {total_time / 3600:.2f}小时")

        history_path = Path(self.config.log_dir) / f"{self.config.experiment_name}_history.json"
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(self.training_history, f, indent=2)
        print(f"训练历史保存到: {history_path}")

    def test(self) -> Dict[str, float]:
        if self.test_loader is None:
            print("没有测试数据加载器")
            return {}
        print("开始多标签测试...")
        metrics = self.evaluate(self.test_loader, "test")
        print("\n测试结果:")
        for key, value in metrics.items():
            print(f"  {key}: {value:.4f}")
        return metrics


def create_multilabel_trainer(
    model: MultiLabelDACGModel,
    train_loader: DataLoader,
    val_loader: DataLoader,
    label_names: List[str],
    config: Optional[MultiLabelTrainerConfig] = None,
    test_loader: Optional[DataLoader] = None,
) -> MultiLabelDACGTrainer:
    if config is None:
        config = MultiLabelTrainerConfig()
    return MultiLabelDACGTrainer(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        config=config,
        label_names=label_names,
        test_loader=test_loader,
    )
