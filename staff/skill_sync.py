"""
CLI端 Skill 同步机制

功能：
- 员工终端登录时向服务端检查 Skill 更新
- 下载新增/更新的 Skill zip 包到本地
- 删除服务端已禁用/删除的本地 Skill
- 维护本地版本清单 (staff/skills/local_manifest.json)

本地 Skill 目录结构（staff/skills/）：
  skills/
  ├── local_manifest.json        # 本地版本清单
  ├── outlook-controller/
  │   ├── SKILL.md
  │   └── scripts/
  │       ├── read.py
  │       └── send.py
  └── employment-certificate/
      ├── SKILL.md
      └── scripts/
          └── generate.py
"""

import os
import sys
import json
import shutil
import zipfile
import io
from pathlib import Path

# 本地 skills 目录（staff/skills/）
LOCAL_SKILLS_DIR = str(Path(__file__).resolve().parent / "skills")
LOCAL_MANIFEST_PATH = str(Path(LOCAL_SKILLS_DIR) / "local_manifest.json")


def get_local_manifest() -> dict:
    """
    读取本地版本清单。
    格式: {"outlook-controller": "1.0.0", "employment-certificate": "1.0.0"}
    """
    if os.path.exists(LOCAL_MANIFEST_PATH):
        try:
            with open(LOCAL_MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_local_manifest(manifest: dict):
    """保存本地版本清单"""
    os.makedirs(LOCAL_SKILLS_DIR, exist_ok=True)
    with open(LOCAL_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def check_and_sync(server_url: str, token: str, user_role: str) -> dict:
    """
    向服务端检查更新并同步 Skill。

    返回：
    {
        "success": True,
        "synced": {"new": [...], "updated": [...], "deleted": [...], "skipped": [...]},
        "errors": [...],
    }
    """
    import requests

    result = {
        "success": True,
        "synced": {"new": [], "updated": [], "deleted": [], "skipped": []},
        "errors": [],
    }

    local_manifest = get_local_manifest()

    # 1. 向服务端查询更新
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        resp = requests.post(
            f"{server_url}/api/skills/check-update",
            headers=headers,
            json={"local_versions": local_manifest},
            timeout=10,
        )
        if resp.status_code != 200:
            result["success"] = False
            result["errors"].append(f"检查更新失败: HTTP {resp.status_code}")
            return result

        update_info = resp.json()
    except requests.exceptions.ConnectionError:
        result["success"] = False
        result["errors"].append(f"无法连接到服务器 {server_url}")
        return result
    except Exception as e:
        result["success"] = False
        result["errors"].append(f"检查更新异常: {e}")
        return result

    new_skills = update_info.get("new", [])
    update_skills = update_info.get("update", [])
    delete_skills = update_info.get("delete", [])

    # 2. 下载新增和更新的 skill
    for skill_info in new_skills + update_skills:
        skill_name = skill_info["skill_name"]
        version = skill_info["version"]
        action = skill_info["action"]  # "new" 或 "update"

        try:
            # 检查该 skill 的 target_roles 是否包含当前用户角色
            detail_resp = requests.get(
                f"{server_url}/api/skills/registry/{skill_name}",
                headers=headers,
                timeout=10,
            )
            if detail_resp.status_code == 200:
                skill_detail = detail_resp.json().get("skill", {})
                target_roles = skill_detail.get("target_roles", [])
                if target_roles and user_role not in target_roles:
                    result["synced"]["skipped"].append(
                        {
                            "skill_name": skill_name,
                            "reason": f"角色 {user_role} 无权使用此 Skill",
                        }
                    )
                    continue

            # 下载 zip 包
            download_resp = requests.get(
                f"{server_url}/api/skills/download/{skill_name}",
                headers=headers,
                timeout=30,
            )
            if download_resp.status_code != 200:
                result["errors"].append(
                    f"下载 {skill_name} 失败: HTTP {download_resp.status_code}"
                )
                continue

            # 解压到本地 skills 目录
            skill_dir = os.path.join(LOCAL_SKILLS_DIR, skill_name)

            # 如果是更新，先删除旧目录
            if os.path.exists(skill_dir):
                shutil.rmtree(skill_dir)

            os.makedirs(skill_dir, exist_ok=True)

            zip_buffer = io.BytesIO(download_resp.content)
            with zipfile.ZipFile(zip_buffer, "r") as zf:
                names = zf.namelist()
                has_root_dir = any(
                    n.startswith(skill_name + "/") for n in names if "/" in n
                )

                if has_root_dir:
                    zf.extractall(LOCAL_SKILLS_DIR)
                else:
                    zf.extractall(skill_dir)

            # 更新本地版本清单
            local_manifest[skill_name] = version
            save_local_manifest(local_manifest)

            result["synced"][action].append(
                {
                    "skill_name": skill_name,
                    "version": version,
                    "display_name": skill_info.get("display_name", ""),
                }
            )

        except Exception as e:
            result["errors"].append(f"处理 {skill_name} 异常: {e}")

    # 3. 删除服务端已禁用/删除的 skill
    for skill_info in delete_skills:
        skill_name = skill_info["skill_name"]
        reason = skill_info.get("reason", "")

        try:
            skill_dir = os.path.join(LOCAL_SKILLS_DIR, skill_name)
            if os.path.exists(skill_dir):
                shutil.rmtree(skill_dir)

            if skill_name in local_manifest:
                del local_manifest[skill_name]
                save_local_manifest(local_manifest)

            result["synced"]["deleted"].append(
                {
                    "skill_name": skill_name,
                    "reason": reason,
                }
            )
        except Exception as e:
            result["errors"].append(f"删除 {skill_name} 异常: {e}")

    return result


def get_all_local_skills_info() -> list:
    """获取所有本地已安装 skill 的信息"""
    manifest = get_local_manifest()
    result = []
    for skill_name, version in manifest.items():
        skill_dir = os.path.join(LOCAL_SKILLS_DIR, skill_name)
        if os.path.exists(skill_dir):
            result.append(
                {
                    "skill_name": skill_name,
                    "version": version,
                    "path": skill_dir,
                }
            )
    return result
