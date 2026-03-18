
def generate_findings(areas: dict) -> str:
    """
    根据分割面积指标生成英文结构化诊断描述条目。
    """
    heart = float(areas.get("heart_area", 0.0) or 0.0)
    left = float(areas.get("left_lung_area", 0.0) or 0.0)
    right = float(areas.get("right_lung_area", 0.0) or 0.0)

    lung_total = left + right
    ctr = heart / lung_total if lung_total > 0 else 0.0

    lines = []
    if ctr > 0.50:
        lines.append(f"- Cardiothoracic ratio is {ctr:.2f}, suggesting possible cardiomegaly.")
    else:
        lines.append(f"- Cardiothoracic ratio is {ctr:.2f}, within normal limits.")

    diff = abs(left - right)
    if lung_total == 0:
        ratio_diff = 0.0
    else:
        ratio_diff = diff / max(left, right)

    if ratio_diff > 0.15:
        lines.append(
            f"- Asymmetric lung volumes noted (left: {left:.2f}px, right: {right:.2f}px)."
        )
    else:
        lines.append("- Bilateral lung volumes appear symmetric.")

    return "\n".join(lines)
