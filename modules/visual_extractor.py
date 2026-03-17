import torch
import torch.nn as nn
import torchvision.models as models
from types import SimpleNamespace

def build_backbone(name: str, pretrained: bool) -> nn.Module:
    """
    构建 torchvision backbone，并去掉最后两层（通常是 avgpool 和 fc），输出特征图 (B, C, H', W')
    同时兼容 torchvision 新旧 API（pretrained / weights）。
    """
    ctor = getattr(models, name)

    # 兼容 torchvision 新版本：pretrained -> weights
    try:
        if pretrained:
            # 例如 ResNet50_Weights.DEFAULT
            weights_enum = getattr(models, f"{name.split('_')[0].capitalize()}{name.split('_')[1]}_Weights", None)
            weights = weights_enum.DEFAULT if weights_enum is not None else "DEFAULT"
        else:
            weights = None
        model = ctor(weights=weights)
    except TypeError:
        # 旧版本 torchvision
        model = ctor(pretrained=pretrained)

    modules = list(model.children())[:-2]
    return nn.Sequential(*modules)


class VisualExtractor(nn.Module):
    def __init__(self, args=None):
        super().__init__()
        if args is None:
            args = SimpleNamespace(
                visual_extractor="resnet50",
                visual_extractor_pretrained=False,
            )
        if not hasattr(args, "visual_extractor"):
            args.visual_extractor = "resnet50"

        if not hasattr(args, "visual_extractor_pretrained"):
            args.visual_extractor_pretrained = False

        self.model = build_backbone(
            args.visual_extractor,
            args.visual_extractor_pretrained
        )

    def forward(self, images_list):
        """
        Args:
            images_list: 长度为5的列表，每个元素形状 (B, C, H, W)
        Returns:
            global_features: (B, C, H', W')
            partition_features: list长度4，每个 (B, C, H', W')
        """
        if len(images_list) != 5:
            raise ValueError(f"images_list 必须包含 5 张图像，但实际为 {len(images_list)}")

        feats = [self.model(img) for img in images_list]
        return feats[0], feats[1:]


if __name__ == "__main__":
    # ----------- 测试代码 -----------
    class Args:
        visual_extractor = "resnet101"
        visual_extractor_pretrained = False  # 测试时用 False，避免下载权重

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = VisualExtractor(Args()).to(device)
    model.eval()

    B, C, H, W = 2, 3, 224, 224
    images_list = [torch.randn(B, C, H, W, device=device) for _ in range(5)]

    with torch.no_grad():
        global_feat, part_feats = model(images_list)

    print("global_feat shape:", tuple(global_feat.shape))
    print("num part feats:", len(part_feats))
    print("part_feat[0] shape:", tuple(part_feats[0].shape))
