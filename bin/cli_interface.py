#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行接口 - 医疗图像报告生成工具
使用方法:
    python cli_interface.py --image path/to/image.jpg
    python cli_interface.py --image-dir path/to/images/
    python cli_interface.py --image path/to/image.jpg --output report.json
"""

import argparse
import os
import json
import glob
from pathlib import Path
from integrated_report_generator import IntegratedMedicalReportGenerator


def main():
    parser = argparse.ArgumentParser(description="医疗图像报告生成命令行工具")
    parser.add_argument('--image', type=str, help='单张图像路径')
    parser.add_argument('--image-dir', type=str, help='图像文件夹路径')
    parser.add_argument('--output', type=str, help='输出文件路径（单张图像时）')
    parser.add_argument('--output-dir', type=str, default='outputs', help='输出文件夹路径（批量处理时）')
    parser.add_argument('--format', type=str, default='json', choices=['json', 'txt'], help='输出格式')
    parser.add_argument('--findings-only', action='store_true', help='只生成findings')
    parser.add_argument('--impressions-only', action='store_true', help='只生成impressions')
    parser.add_argument('--lang', type=str, default='auto', choices=['auto', 'zh', 'en'],
                        help='输出语言（auto: 优先中文，缺失则英文）')

    args = parser.parse_args()

    if not args.image and not args.image_dir:
        print("❌ 请提供图像路径或图像文件夹路径")
        parser.print_help()
        return

    # 初始化生成器
    print("🔄 正在初始化医疗报告生成器...")
    translate_to_zh = args.lang != 'en'
    generator = IntegratedMedicalReportGenerator(translate_to_zh=translate_to_zh)

    # 处理单张图像
    if args.image:
        if not os.path.exists(args.image):
            print(f"❌ 图像文件不存在: {args.image}")
            return

        print(f"🔍 处理图像: {args.image}")
        report = generator.generate_report(args.image)

        # 根据参数过滤输出
        if args.findings_only:
            report = {
                "findings": report.get("findings"),
                "findings_zh": report.get("findings_zh"),
                "image_path": report["image_path"]
            }
        elif args.impressions_only:
            report = {
                "impressions": report.get("impressions"),
                "impressions_zh": report.get("impressions_zh"),
                "image_path": report["image_path"]
            }

        # 输出结果
        if args.output:
            # 保存到文件
            if args.format == 'json':
                generator.save_report(report, args.output)
            else:  # txt格式
                txt_output = args.output.replace('.json', '.txt')
                save_report_as_txt(report, txt_output)
        else:
            # 打印到控制台
            print_report(report, args.format, lang=args.lang)

    # 处理文件夹中的图像
    elif args.image_dir:
        if not os.path.exists(args.image_dir):
            print(f"❌ 图像文件夹不存在: {args.image_dir}")
            return

        # 创建输出文件夹
        os.makedirs(args.output_dir, exist_ok=True)

        # 查找所有图像文件
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp']
        image_files = []
        for ext in image_extensions:
            image_files.extend(glob.glob(os.path.join(args.image_dir, ext)))
            image_files.extend(glob.glob(os.path.join(args.image_dir, ext.upper())))

        if not image_files:
            print(f"❌ 在文件夹中未找到图像文件: {args.image_dir}")
            return

        print(f"🔍 找到 {len(image_files)} 张图像，开始批量处理...")

        # 批量处理
        reports = generator.generate_batch_reports(image_files)

        # 保存报告
        for i, report in enumerate(reports):
            # 根据参数过滤输出
            if args.findings_only:
                filtered_report = {
                    "findings": report.get("findings"),
                    "findings_zh": report.get("findings_zh"),
                    "image_path": report["image_path"]
                }
            elif args.impressions_only:
                filtered_report = {
                    "impressions": report.get("impressions"),
                    "impressions_zh": report.get("impressions_zh"),
                    "image_path": report["image_path"]
                }
            else:
                filtered_report = report

            # 生成输出文件名
            image_name = Path(report["image_path"]).stem
            if args.format == 'json':
                output_path = os.path.join(args.output_dir, f"{image_name}_report.json")
                generator.save_report(filtered_report, output_path)
            else:  # txt格式
                output_path = os.path.join(args.output_dir, f"{image_name}_report.txt")
                save_report_as_txt(filtered_report, output_path, lang=args.lang)

        print(f"✅ 批量处理完成，报告已保存到: {args.output_dir}")


def select_by_lang(report, field, lang):
    """根据语言偏好从报告中选择字段"""
    zh_key = f"{field}_zh"
    if lang == 'zh':
        return report.get(zh_key) or report.get(field) or ''
    if lang == 'en':
        return report.get(field) or ''
    # auto: 优先中文
    return report.get(zh_key) or report.get(field) or ''


def print_report(report, format_type='json', lang='auto'):
    """打印报告到控制台"""
    print("\n" + "="*60)
    print("🏥 医疗图像报告")
    print("="*60)
    print(f"图像路径: {report['image_path']}")

    if 'findings' in report:
        print(f"\n📋 检查发现 (Findings):")
        print("-" * 40)
        print(select_by_lang(report, 'findings', lang))

    if 'impressions' in report:
        print(f"\n💭 诊断印象 (Impressions):")
        print("-" * 40)
        print(select_by_lang(report, 'impressions', lang))

    print("="*60)

    if format_type == 'json':
        print("\n📄 JSON格式:")
        print(json.dumps(report, ensure_ascii=False, indent=2))


def save_report_as_txt(report, output_path, lang='auto'):
    """保存报告为文本格式"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("医疗图像报告\n")
            f.write("="*60 + "\n")
            f.write(f"图像路径: {report['image_path']}\n\n")

            if 'findings' in report:
                f.write("检查发现 (Findings):\n")
                f.write("-" * 40 + "\n")
                f.write(select_by_lang(report, 'findings', lang) + "\n\n")

            if 'impressions' in report:
                f.write("诊断印象 (Impressions):\n")
                f.write("-" * 40 + "\n")
                f.write(select_by_lang(report, 'impressions', lang) + "\n")

            f.write("="*60 + "\n")

        print(f"✅ 报告已保存到: {output_path}")
    except Exception as e:
        print(f"❌ 保存报告失败: {e}")


if __name__ == "__main__":
    main()
