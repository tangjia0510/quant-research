from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1];A=R/'artifacts'
cov=pd.read_csv(A/'daily-quality-coverage.csv',parse_dates=['date'])
plt.style.use('seaborn-v0_8-whitegrid');fig,ax=plt.subplots(figsize=(13,4.5),layout='constrained')
for c in ['lifecycle','observed','bar_good','signal_eligible','signal_labeled']:
 v=cov[c].copy()
 if c=='signal_labeled':v.iloc[-6:]=float('nan')
 ax.plot(cov.date,v,label=c)
ax.set_title('Coverage by date | frozen SH/SZ identifiers, retrospective source snapshot');ax.legend(ncol=3)
ax.text(.01,.02,'2019 first 60 sessions: warmup. Last 6 sessions: future labels not mature (not plotted as zero).',transform=ax.transAxes,fontsize=9)
fig.savefig(A/'coverage-diagnostic.png',dpi=160);plt.close(fig)
