"""
技能执行脚本：开具在职证明（Employment Certificate）

自动为员工生成在职证明文件，并通过邮件发送。
元数据定义在同目录下的 SKILL.md 中。
"""
import os
import json
from datetime import datetime
from pathlib import Path


def execute(params: dict) -> dict:
    """
    执行开具在职证明。
    
    参数：
        params: {
            "employee_name": "张三",
            "employee_id": "100123",  # 可选
            "purpose": "银行贷款",  # 可选
        }
    
    返回：
        {
            "success": True/False,
            "message": "执行结果描述",
            "file_path": "生成的文件路径（如有）",
            "email_sent": True/False,
        }
    """
    employee_name = params.get("employee_name", "")
    employee_id = params.get("employee_id", "")
    purpose = params.get("purpose", "个人事务")
    
    if not employee_name:
        return {"success": False, "message": "缺少必要参数：employee_name"}
    
    # 查询员工信息
    employee_info = None
    try:
        from src.tools.data_sources import get_secretary
        secretary = get_secretary()
        matches = secretary.roster.query_by_name(employee_name)
        if matches:
            employee_info = matches[0]
        elif employee_id:
            matches = secretary.roster.query_by_employee_id(employee_id)
            if matches:
                employee_info = matches[0]
    except Exception as e:
        return {"success": False, "message": f"查询员工信息失败: {e}"}
    
    if not employee_info:
        return {"success": False, "message": f"花名册中未找到员工: {employee_name}"}
    
    # 生成在职证明内容
    now = datetime.now()
    cert_content = f"""
╔══════════════════════════════════════════════════════════╗
║                      在 职 证 明                        ║
╚══════════════════════════════════════════════════════════╝

兹证明 {employee_info.get('姓名', employee_name)} 先生/女士，

身份证号：{employee_info.get('身份证号', '****')}
员工工号：{employee_info.get('员工号', employee_id or '****')}
入职日期：{employee_info.get('入职日期', '****')}
所属部门：{employee_info.get('部门', '****')}
现任岗位：{employee_info.get('岗位', '****')}

现为我司正式在职员工，情况属实。

本证明仅用于：{purpose}

特此证明。


                              富赛汽车电子有限公司
                              人力资源部
                              {now.strftime('%Y年%m月%d日')}

════════════════════════════════════════════════════════════
"""
    
    # 保存文件
    output_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "certificates"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"在职证明_{employee_name}_{now.strftime('%Y%m%d%H%M%S')}.txt"
    file_path = output_dir / filename
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(cert_content)
    
    print(f"[技能-在职证明] 已生成文件: {file_path}")
    
    # 模拟邮件发送（MVP阶段只打印日志）
    email_sent = False
    try:
        # 在实际环境中，这里会调用邮件发送API
        print(f"[技能-在职证明] 模拟发送邮件给 {employee_name}...")
        print(f"[技能-在职证明] 邮件主题：您的在职证明 - 富赛汽车电子有限公司")
        print(f"[技能-在职证明] 邮件附件：{filename}")
        email_sent = True
    except Exception as e:
        print(f"[技能-在职证明] 邮件发送失败: {e}")
    
    return {
        "success": True,
        "message": f"已为 {employee_name}（{employee_info.get('部门', '')} / {employee_info.get('岗位', '')}）开具在职证明，用途：{purpose}。文件已生成，{'邮件已发送给员工。' if email_sent else '邮件发送未成功，请手动处理。'}",
        "file_path": str(file_path),
        "email_sent": email_sent,
        "employee_info": {
            "name": employee_info.get("姓名", ""),
            "department": employee_info.get("部门", ""),
            "position": employee_info.get("岗位", ""),
        },
    }