"""验证替换后的加班基础数据"""
import pandas as pd
from pathlib import Path

f = Path(__file__).resolve().parent.parent / "databases" / "加班基础数据.xlsx"
df = pd.read_excel(f)
print(f"行数: {len(df):,}  列数: {len(df.columns)}  大小: {f.stat().st_size/1024/1024:.1f}MB")

needed = ['员工编号','部门','中心','考勤年份','考勤月份','当日加班时长',
          '员工当日出勤率','部门当日出勤率','部门月总人数','中心月总人数',
          '公司月总人数','白领员工月人均加班时长','蓝领员工月人均加班时长']
for c in needed:
    print(f"  {c}: {'OK' if c in df.columns else 'MISSING'}")

print(f"\n当日加班时长(月总): min={df['当日加班时长'].min():.2f}, max={df['当日加班时长'].max():.2f}, mean={df['当日加班时长'].mean():.2f}")
print(f"员工数: {df['员工编号'].nunique()}")
print(f"月份: {sorted(df['考勤月份'].unique())}")