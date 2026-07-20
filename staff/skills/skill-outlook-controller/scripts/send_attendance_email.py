import json

payload = {
    "to": ["shun.li@example-tech.com"],
    "subject": "2026年6月考勤打卡信息",
    "body": "<div>李顺，您好！</div><div><br></div><div>以下是您2026年6月的考勤打卡信息：</div><div><br></div><table border=\"1\" cellpadding=\"5\" cellspacing=\"0\" style=\"border-collapse: collapse; width: 100%;\"><tr><th colspan=\"4\" style=\"background-color: #f2f2f2;\">基本信息</th></tr><tr><td><strong>姓名</strong></td><td>李顺</td><td><strong>工号</strong></td><td>110430</td></tr><tr><td><strong>部门</strong></td><td>人力资源管理部SSC</td><td><strong>职位</strong></td><td>高级HRIS工程师</td></tr><tr><td><strong>考勤月份</strong></td><td colspan=\"3\">2026年6月</td></tr><tr><th colspan=\"4\" style=\"background-color: #f2f2f2;\">考勤统计（2026-06-01）</th></tr><tr><td><strong>补卡次数</strong></td><td>3次</td><td><strong>漏打卡</strong></td><td>0次</td></tr><tr><td><strong>早退</strong></td><td>0次</td><td><strong>迟到</strong></td><td>3次</td></tr><tr><td><strong>迟到和早退合计</strong></td><td>3次</td><td><strong>夜班</strong></td><td>0次</td></tr><tr><td><strong>工作日加班</strong></td><td>0小时</td><td><strong>双休加班</strong></td><td>0小时</td></tr><tr><td><strong>法定加班</strong></td><td>0小时</td><td><strong>旷工</strong></td><td>0小时</td></tr><tr><td><strong>当日加班时长</strong></td><td>18.73小时</td><td><strong>当日出勤率</strong></td><td>95.24%</td></tr></table><div><br></div><div>如有疑问，请联系HR SSC。</div>"
}

with open("staff/skills/skill-outlook-controller/scripts/temp_email.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)

print("JSON file written successfully")