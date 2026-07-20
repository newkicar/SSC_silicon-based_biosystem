#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""临时脚本：发送专家岗位任命邮件"""

import json
from outlook_service import OutlookService

def main():
    email_data = {
        "to": ["shun.li@example-tech.com"],
        "subject": "专家岗位任命要求及建议",
        "body": """<html><body>
<p>李顺：</p>
<p>你好！</p>
<p>以下为你详细介绍专家岗位任命的相关要求及建议，供你参考。</p>

<h3>一、专家岗位任命条件（根据CSpec-{{EXCEL_PASSWORD_CC}}-003）</h3>
<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width:100%;">
<tr style="background-color:#f0f0f0;">
<th style="text-align:left;">序号</th>
<th style="text-align:left;">条件</th>
</tr>
<tr>
<td>1</td>
<td><b>有专家岗位编制</b>：所在部门需有专家岗位编制名额</td>
</tr>
<tr>
<td>2</td>
<td><b>通过专家委员会任职资格评定</b>：当前岗位得分≥4分，目标岗位得分≥3分</td>
</tr>
<tr>
<td>3</td>
<td><b>在研发领域具备丰富的实际研发工作经验</b>或在某一或多个技术领域有专长</td>
</tr>
<tr>
<td>4</td>
<td><b>承接过或参与过公司的战略课题</b></td>
</tr>
<tr>
<td>5</td>
<td><b>能够带领相关人员进行战略课题跟踪调研</b></td>
</tr>
</table>

<br>
<h3>二、专家岗位任命流程</h3>
<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width:100%;">
<tr style="background-color:#f0f0f0;">
<th style="text-align:left;">步骤</th>
<th style="text-align:left;">环节</th>
<th style="text-align:left;">说明</th>
</tr>
<tr>
<td>1</td>
<td><b>部门推荐</b></td>
<td>由所在部门进行推荐</td>
</tr>
<tr>
<td>2</td>
<td><b>HR审核</b></td>
<td>人力资源部对推荐人选进行审核</td>
</tr>
<tr>
<td>3</td>
<td><b>答辩评审</b></td>
<td>通过专家委员会答辩评审</td>
</tr>
<tr>
<td>4</td>
<td><b>管理层批准</b></td>
<td>管理层最终批准</td>
</tr>
<tr>
<td>5</td>
<td><b>公示15天</b></td>
<td>任命结果公示15天</td>
</tr>
<tr>
<td>6</td>
<td><b>发布任命</b></td>
<td>正式发布任命通知</td>
</tr>
<tr>
<td>7</td>
<td><b>3个月后转正</b></td>
<td>试用期3个月，期满转正</td>
</tr>
</table>

<br>
<h3>三、结合你个人情况的建议</h3>

<h4>1. 基本信息</h4>
<ul>
<li><b>当前职位</b>：高级HRIS工程师</li>
<li><b>职级通道</b>：T通道（技术通道）</li>
<li><b>所属部门</b>：人力资源管理部 SSC</li>
<li><b>工龄</b>：4年</li>
<li><b>学历</b>：本科</li>
</ul>

<h4>2. 优势分析</h4>
<ul>
<li>具备HR系统专业背景，对HCM系统非常熟悉</li>
<li>有技术通道发展基础，T通道与专家岗位方向匹配</li>
<li>在HR信息化领域有实际工作经验和技术专长</li>
</ul>

<h4>3. 建议方向</h4>
<ul>
<li>可考虑<b>HR信息化方向</b>的专家岗位</li>
<li>充分发挥你在系统专业方面的优势</li>
<li>结合HR业务理解与技术能力，形成差异化竞争力</li>
</ul>

<h4>4. 下一步行动</h4>
<ul>
<li>与上级<b>刘南南</b>沟通专家岗位编制情况</li>
<li>准备任职资格评定相关材料</li>
<li>了解公司战略课题参与机会，争取承接或参与</li>
</ul>

<br>
<p>以上建议供你参考，如有任何问题欢迎随时沟通。</p>
<p>祝好！</p>
</body></html>"""
    }

    service = OutlookService()
    try:
        service.send_email(
            to=email_data["to"],
            cc=email_data.get("cc", []),
            bcc=email_data.get("bcc", []),
            subject=email_data["subject"],
            body=email_data.get("body", ""),
            attachment=None,
        )
        print(json.dumps({"success": True, "message": "邮件发送成功"}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
    finally:
        service.close()

if __name__ == "__main__":
    main()
