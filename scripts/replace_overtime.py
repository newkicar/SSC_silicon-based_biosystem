"""聚合加班数据并替换原文件"""
import pandas as pd
import shutil
from pathlib import Path
import sys

db = Path(__file__).resolve().parent.parent / "databases"
src = db / "加班基础数据.xlsx"
log = db.parent / "data" / "replace_log.txt"
lines = []

def p(msg):
    print(msg)
    lines.append(msg)

df = pd.read_excel(src)
p(f"原始: {len(df):,}行 {len(df.columns)}列 {src.stat().st_size/1024/1024:.1f}MB")

df['ot'] = pd.to_numeric(df['当日加班时长'], errors='coerce').fillna(0.0)
df['month'] = pd.to_numeric(df['考勤月份'], errors='coerce').fillna(0).astype(int)

# Baseline
emp_m = df.groupby(['员工编号','考勤年份','month'],as_index=False).agg(ot=('ot','sum'))
comp_base = emp_m.groupby('month')['ot'].sum()

# Aggregate
identity = ['地区','公司','中心','部门','二级部门','三级部门','编制类型','蓝领白领',
    '员工职级','员工编号','姓名','工号姓名','岗级','大级别','白领蓝领','岗位',
    '入职日期','考勤日期','考勤年份','白领员工月人均加班时长','蓝领员工月人均加班时长',
    '部门月加班人数占比','中心月加班人数占比','部门月总人数','中心月总人数',
    '公司月总人数','白领蓝领月总人数','日均小于半小时','日均小于一小时',
    '近两个月加班时长大于60小时']
sum_cols = ['补卡次数','漏打卡次数','早退次数','迟到次数','迟到和早退',
    '夜班次数','工作日加班','双休加班','法定加班','旷工小时数','当日加班时长',
    '加班时长小于1小时的日均时长']
mean_cols = ['员工当日出勤率','部门当日出勤率']

agg = {}
for c in identity + ['考勤月份']:
    if c in df.columns: agg[c] = 'first'
for c in sum_cols:
    if c in df.columns: agg[c] = 'sum'
for c in mean_cols:
    if c in df.columns: agg[c] = 'mean'

df_agg = df.groupby(['员工编号','考勤月份'],as_index=False).agg(agg)
keep = [c for c in df_agg.columns if c not in ('ot','month')]
df_agg = df_agg[keep]
p(f"聚合: {len(df_agg):,}行 {len(df_agg.columns)}列")

# Verify
df_agg['ot'] = pd.to_numeric(df_agg['当日加班时长'], errors='coerce').fillna(0.0)
df_agg['month'] = pd.to_numeric(df_agg['考勤月份'], errors='coerce').fillna(0).astype(int)
comp_agg = df_agg.groupby('month')['ot'].sum()
ok = True
for m in sorted(comp_base.index):
    d = abs(comp_base[m] - comp_agg[m])
    s = "OK" if d < 0.01 else "FAIL"
    if d >= 0.01: ok = False
    p(f"  {s} {m}月: {comp_base[m]:.2f} vs {comp_agg[m]:.2f}")

if not ok:
    p("VERIFICATION FAILED!")
    log.write_text("\n".join(lines), encoding="utf-8")
    sys.exit(1)

p("ALL PASS - replacing file...")

# Save aggregated to temp, then replace
tmp = db / "_tmp_agg.xlsx"
df_agg_save = df_agg[keep]
df_agg_save.to_excel(tmp, index=False)
p(f"Temp saved: {tmp.stat().st_size/1024/1024:.1f}MB")

# Backup original
bak = db / "加班基础数据_明细备份.xlsx"
if not bak.exists():
    shutil.copy2(src, bak)
    p(f"Backup: {bak.name}")

# Replace
shutil.copy2(tmp, src)
p(f"Replaced: {src.stat().st_size/1024/1024:.1f}MB")

# Cleanup
tmp.unlink()
p("DONE!")

log.write_text("\n".join(lines), encoding="utf-8")
p(f"Log: {log}")