#!/usr/bin/env python3
"""测试分割API接口"""
import requests
import time
import json
from pathlib import Path

BASE_URL = "http://localhost:8000"
TEST_IMAGE = "/data/home/zyx/Ir-UNet/DACG/DACG-Struct/backend/tests/3.png"

def login():
    """登录获取token"""
    url = f"{BASE_URL}/auth/login"
    payload = {
        "login_name": "ADMIN01",
        "password": "pass@ADMIN01",
        "role_name": "管理员"
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        data = response.json()
        print(f"✓ 登录成功: {data['user']['real_name']}")
        return data["access_token"]
    else:
        print(f"✗ 登录失败: {response.status_code} - {response.text}")
        return None

def upload_xray(token):
    """上传X光片"""
    url = f"{BASE_URL}/xray/upload"
    headers = {"Authorization": f"Bearer {token}"}
    
    files = {
        "file": (Path(TEST_IMAGE).name, open(TEST_IMAGE, "rb"), "image/png")
    }
    data = {
        "patient_id": "TEST005",
        "patient_name": "测试患者5",
        "patient_gender": "1",
        "patient_age": "30",
        "xray_format": "PNG"
    }
    
    response = requests.post(url, headers=headers, files=files, data=data)
    files["file"][1].close()
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 上传成功: xray_id={result['xray_id']}")
        return result["xray_id"]
    else:
        print(f"✗ 上传失败: {response.status_code} - {response.text}")
        return None

def wait_for_segmentation(token, xray_id, timeout=120):
    """等待分割完成"""
    url = f"{BASE_URL}/xray/{xray_id}/segment-status"
    headers = {"Authorization": f"Bearer {token}"}
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            status = response.json()["segment_status"]
            print(f"  分割状态: {status} (0=未开始, 1=进行中, 2=完成, 3=失败)")
            if status == 2:
                print("✓ 分割完成")
                return True
            elif status == 3:
                print("✗ 分割失败")
                return False
        time.sleep(2)
    
    print("✗ 等待超时")
    return False

def get_mask(token, xray_id, output_path):
    """获取mask图片"""
    url = f"{BASE_URL}/xray/{xray_id}/mask"
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"✓ Mask已保存到: {output_path}")
        return True
    else:
        print(f"✗ 获取mask失败: {response.status_code} - {response.text}")
        return False

def get_xray_detail(token, xray_id):
    """获取X光片详情"""
    url = f"{BASE_URL}/xray/{xray_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"✓ X光片详情:")
        print(f"  - xray_id: {data['xray']['xray_id']}")
        print(f"  - patient_name: {data['xray']['patient_name']}")
        if data['segment_result']:
            print(f"  - segment_id: {data['segment_result']['segment_id']}")
            print(f"  - heart_area: {data['segment_result']['heart_area']}")
            print(f"  - left_lung_area: {data['segment_result']['left_lung_area']}")
            print(f"  - right_lung_area: {data['segment_result']['right_lung_area']}")
            print(f"  - model_version: {data['segment_result']['model_version']}")
        return data
    else:
        print(f"✗ 获取详情失败: {response.status_code} - {response.text}")
        return None

def main():
    print("=" * 60)
    print("测试分割API接口（纯彩色Mask）")
    print("=" * 60)
    
    # 1. 登录
    token = login()
    if not token:
        return
    
    # 2. 上传X光片
    xray_id = upload_xray(token)
    if not xray_id:
        return
    
    # 3. 等待分割完成
    if not wait_for_segmentation(token, xray_id):
        return
    
    # 4. 获取详情
    detail = get_xray_detail(token, xray_id)
    
    # 5. 获取mask图片
    output_path = f"/data/home/zyx/Ir-UNet/DACG/DACG-Struct/backend/tests/mask_final_{xray_id}.png"
    get_mask(token, xray_id, output_path)
    
    print("=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()
