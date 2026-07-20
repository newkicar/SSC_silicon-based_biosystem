"""加班基础数据：日度→月度聚合 + 一致性验证"""
import pandas as pd
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent.parent / "databases"
SRC = DB_DIR / "加班基础数据.xlsx"
OUT = DB_DIR / "加班基础数据_月度聚合.xlsx"

df = pd.read_excel(SRC)
print(f"原始: {len(df):,}行 {len(df.columns)}列, {df['员工编号'].nunique()}员工")

df['ot'] = pd.to_numeric(df['当日加班时长'], errors='coerce').fillna(0.0)
df['month'] = pd.to_numeric(df['考勤月份'], errors='coerce').fillna(0).astype(int)

# 基准统计
emp_m = df.groupby(['员工编号','考勤年份','month'],as_index=False).agg(ot=('ot','sum'))
comp_base = emp_m.groupby('month')['ot'].sum()
dept_base = df[df['month']==1].groupby(['员工编号','部门'],as_index=False).agg(ot=('ot','sum'))
dept_avg_base = dept_base.groupby('部门')['ot'].mean().sort_values(ascending=False)
center_base = df[df['month']==1].groupby(['员工编号','中心'],as_index=False).agg(ot=('ot','sum'))
center_avg_base = center_base.groupby('中心')['ot'].mean().sort_values(ascending=False)

# 聚合规则
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
print(f"聚合: {len(df_agg):,}行 {len(df_agg.columns)}列 (压缩{len(df)/len(df_agg):.1f}倍)")

# 验证
df_agg['ot'] = pd.to_numeric(df_agg['当日加班时长'], errors='coerce').fillna(0.0)
df_agg['month'] = pd.to_numeric(df_agg['考勤月份'], errors='coerce').fillna(0).astype(int)
comp_agg = df_agg.groupby('month')['ot'].sum()
agg_m1 = df_agg[df_agg['month']==1]
dept_avg_agg = agg_m1.groupby('部门')['ot'].mean().sort_values(ascending=False)
center_avg_agg = agg_m1.groupby('中心')['ot'].mean().sort_values(ascending=False)

# 对比
ok = True
print("\n=== 公司月加班总时长 ===")
for m in sorted(comp_base.index):
    d = abs(comp_base[m] - comp_agg[m])
    s = "OK" if d < 0.01 else "FAIL"
    if d >= 0.01: ok = False
    print(f"  {s} {m}月: {comp_base[m]:.2f} -> {comp_agg[m]:.2f}")

print("\n=== 1月部门人均加班TOP5 ===")
for dept in dept_avg_base.head(5).index:
    d = abs(dept_avg_base[dept] - dept_avg_agg.get(dept, 0))
    s = "OK" if d < 0.01 else "FAIL"
    if d >= 0.01: ok = False
    print(f"  {s} {dept}: {dept_avg_base[dept]:.2f} -> {dept_avg_agg.get(dept,0):.2f}")

print("\n=== 1月中心人均加班 ===")
for c in center_avg_base.index:
    d = abs(center_avg_base[c] - center_avg_agg.get(c, 0))
    s = "OK" if d < 0.01 else "FAIL"
    if d >= 0.01: ok = False
    print(f"  {s} {c}: {center_avg_base[c]:.2f} -> {center_avg_agg.get(c,0):.2f}")

print()
if ok:
    print("ALL PASS! Saving...")
    keep = [c for c in df_agg.columns if c not in ('ot','month')]
    df_agg[keep].to_excel(OUT, index=False)
    print(f"Saved: {OUT} ({len(df_agg):,} rows, {OUT.stat().st_size/1024/1024:.1f}MB)")
    print(f"Original: {SRC.stat().st_size/1024/1024:.1f}MB")
else:
    print("FAILED! Check logic.")