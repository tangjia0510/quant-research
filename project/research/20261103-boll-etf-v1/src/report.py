from pathlib import Path
import os,json,csv,base64,html,hashlib,argparse
parser=argparse.ArgumentParser(description='Rebuild the Chinese BOLL ETF report from frozen study outputs.')
parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[3])
parser.add_argument('--work-dir',type=Path,default=None,help='Study output directory containing summary.json and CSV files; report goes into its report subdirectory.')
parser.add_argument('--font-file',type=Path,default=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'))
parser.add_argument('--draft',action='store_true',help='Force provisional labeling even when archived audit passed.')
args=parser.parse_args(); ROOT=args.project_root.expanduser().resolve()
D=(args.work_dir.expanduser().resolve() if args.work_dir else ROOT/'work/20261103-boll-etf-v1')
OUT=D/'report'; OUT.mkdir(parents=True,exist_ok=True); R=ROOT/'research/20261103-boll-etf-v1' 
os.environ['MPLCONFIGDIR']=str(OUT/'.mpl')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
from datetime import datetime
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def readcsv(name):
    with (D/name).open() as f:return list(csv.DictReader(f))
summary=json.loads((D/'summary.json').read_text());evidence=json.loads((R/'key-evidence.json').read_text())
protocol=json.loads((R/'protocol.json').read_text());amendments=json.loads((R/'amendments.json').read_text())
validation_path=R/'validation.json'
validation=json.loads(validation_path.read_text()) if validation_path.exists() else {}
sealed=not args.draft and validation.get('audit',{}).get('status')=='passed'
if sealed:
    for rel,expected in validation['executed_code_sha256'].items():
        if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=expected:
            raise ValueError(f'Archived audited input changed: {rel}; revalidate before final reporting.')
K=['boll_breakout','boll_reentry','benchmark'];labels={'boll_breakout':'上轨突破','boll_reentry':'重入带内回归','benchmark':'同ETF买入持有'}
lookup={(r['kind'],r['total_friction_bp']):r for r in summary['results']};active={r['kind']:r for r in evidence['primary_active']}
rows={k:readcsv(f'{k}-10bp-daily.csv') for k in K};annual=readcsv('annual-returns.csv')
assert all(len(r)==1897 for r in rows.values());assert all(not d['registry_admitted'] for d in summary['decisions'])
def pct(v,d=2):return f'{v*100:+.{d}f}%'
def pctabs(v,d=2):return f'{v*100:.{d}f}%'
font_manager.fontManager.addfont(str(args.font_file))
plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':10.5,'axes.titlesize':12,'axes.titleweight':'bold','axes.labelsize':10,'xtick.labelsize':9.5,'ytick.labelsize':9.5,'legend.fontsize':10,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#777777','grid.color':'#dddddd','grid.linewidth':.5,'savefig.facecolor':'white'})
C={'boll_breakout':'#245978','boll_reentry':'#1D7663','benchmark':'#AD5A20'}
fig,(ax,dx)=plt.subplots(2,1,figsize=(9,4.25),sharex=True,gridspec_kw={'height_ratios':[1.25,1]},layout='constrained')
for k in K:
    dates=[datetime.fromisoformat(r['date']) for r in rows[k]];eq=np.array([float(r['equity']) for r in rows[k]]);wealth=np.r_[100000,eq];dd=(wealth/np.maximum.accumulate(wealth)-1)[1:]*100
    ax.plot(dates,eq/100000,label=labels[k],color=C[k],lw=1.35);dx.plot(dates,dd,color=C[k],lw=1.15)
ax.axhline(1,color='#888',ls='--',lw=.65);dx.axhline(0,color='#888',ls='--',lw=.65)
ax.set_ylabel('初始本金 = 1');dx.set_ylabel('回撤 %');ax.legend(loc='upper left',ncol=3,frameon=False)
for v in [ax,dx]:v.grid(axis='y');v.margins(x=.01)
dx.set_ylim(-46,3);dx.set_yticks([-40,-20,0]);dx.xaxis.set_major_locator(mdates.YearLocator());dx.xaxis.set_major_formatter(mdates.DateFormatter('%Y'));ax.set_ylim(.82,2.22)
fig.savefig(OUT/'equity-drawdown.png',dpi=240);plt.close(fig)
fig,ax=plt.subplots(figsize=(9,3.1),layout='constrained');years=list(range(2019,2027));x=np.arange(8);w=.25
for i,k in enumerate(K):
    vals=[100*float(next(r['return_net'] for r in annual if r['kind']==k and r['total_friction_bp']=='10' and int(r['year'])==y)) for y in years]
    bars=ax.bar(x+(i-1)*w,vals,width=w,color=C[k],label=labels[k])
    for rect,v in zip(bars,vals):ax.text(rect.get_x()+rect.get_width()/2,v+(.8 if v>=0 else -.8),f'{v:.1f}',ha='center',va='bottom' if v>=0 else 'top',fontsize=8)
ax.set_xticks(x,[str(y) if y!=2026 else '2026*' for y in years]);ax.set_ylim(-27,47);ax.axhline(0,color='#555',lw=.7);ax.grid(axis='y');ax.set_axisbelow(True);ax.set_ylabel('净收益 %');ax.legend(loc='upper right',frameon=False,ncol=3)
fig.savefig(OUT/'annual-returns.png',dpi=240);plt.close(fig)

pages=[]
def page(title=None):
    p=[];pages.append(p)
    if title:p.append(('h1',title))
    return p
status='独立实现核验通过  研究未准入实盘' if sealed else '待独立核验封版  数字暂定'
p=page();p += [('title','BOLL指标在沪深300ETF的历史验证'),('sub',f'510300 ETF  2019年至2026年10月30日  ｜  {status}'),
('p','结论：两项固定规则均未通过净超额收益门槛。上轨突破与重入带内回归的累计净收益分别为21.49%和24.08%，低于同ETF买入持有的53.25%。两者最大回撤较小，但平均ETF敞口仅28.78%和22.16%，不能据此认定存在alpha或同等风险下更优。'),
('table',(['主口径指标','上轨突破','重入带内回归','同ETF买入持有'],[
['累计净收益']+[pct(lookup[k,10]['total_return']) for k in K],
['年化复合收益']+[pct(lookup[k,10]['cagr']) for k in K],
['日度最大回撤']+[pct(lookup[k,10]['max_drawdown']) for k in K],
['日收益年化波动率']+[pctabs(lookup[k,10]['annualized_volatility']) for k in K],
['Sharpe  无风险利率为0']+[f"{lookup[k,10]['sharpe_rf0']:.3f}" for k in K],
['平均ETF市值占比']+[pctabs(lookup[k,10]['mean_exposure']) for k in K],
['期末净资产  元']+[f"{lookup[k,10]['final_equity']:,.2f}" for k in K]
],[2.4,1.5,1.6,1.6])),
('caption','表1  初始资金10万元；主口径每边总摩擦10bp；日波动与Sharpe按252日年化。'),
('figure',('equity-drawdown.png','图1  逐日净值与回撤  包含全部1897个评估交易日  期末不强制清仓',7.0)),
('p','本次只检验一只真实可交易ETF的两个本地完整策略假设。研究借鉴Bollinger的指标定义和筛选条件，并非原作者已验证策略的收益复现；未筛选参数，也未据结果追加实验。')]

p=page('固定指标与精确交易规则');p += [
('p','2018年仅作指标和目标状态预热，不计持仓与收益。评估从2019年首个交易日开始，初始目标只取2018年最后一个收盘状态。全部历史区间包括2026年均已暴露，不是独立未见样本。'),
('h2','同一套20日布林带'),
('p','令TR为因果总回报收盘指数：TRₜ = TRₜ₋₁ ×（未复权收盘价ₜ + 当日除息现金ₜ）÷ 未复权收盘价ₜ₋₁，初值100。中轨为包含当日在内的最近20个交易日TR简单均值；标准差采用总体口径（ddof = 0），上下轨为中轨 ± 2倍标准差。'),
('p','%B =（TR − 下轨）÷（上轨 − 下轨）；BandWidth =（上轨 − 下轨）÷ 中轨。本轮只将%B用于交易和一个描述性诊断，未另设带宽策略。不足20日或带宽为零时不生成新信号，沿用原目标。'),
('table',(['项目','上轨突破','重入带内回归'],[
['空仓时入场','前日%B ≤ 1 且当日%B > 1','前日%B < 0 且当日0 ≤ %B < 0.5'],
['持仓时退出','当日TR < 当日中轨\n严格低于，不仅检查首次下穿','当日TR ≥ 当日中轨\n触及中轨即满足退出'],
['目标与顺序','全仓ETF或现金；已持仓只判断退出，空仓只判断入场','全仓ETF或现金；同一收盘不先退出再重新入场'],
['实际执行','收盘后目标变更，下一交易日未复权开盘价成交','同左；新收盘目标覆盖未成交旧目标']
],[1.15,2.975,2.975])),
('caption','表2  退出、仓位、总回报输入和开盘执行均为本地研究设定；回归入场上限避免买入时已到退出目标。'),
('h2','账户与分红'),
('p','初始现金100000元；每手100份基金单位，只买可负担的整手，不做空、不加杠杆、现金利息为0。每边10bp由佣金5bp和价格滑点5bp组成，无最低佣金；0bp与30bp是预先固定的压力场景。每日至多一笔交易，禁止卖出当日买入份额。'),
('p','登记日收盘份额确认分红权利，除息日记应收，支付日转现金；支付日或之后首个交易日开盘可用现金是日粒度假设，未验证盘中到账时刻。净资产为现金、未复权收盘市值与应收股利之和，不重复计息或分红，未建模代扣税。'),
('p','月末安排下一开盘的同目标执行；持续持仓时仅用已到账股利和余款补买整手。基准始终持有同一ETF，首个评估开盘买入并使用相同的分红再投资、整手、摩擦与估值规则。')]

p=page('年度表现与预设统计门槛');p += [
('figure',('annual-returns.png','图2  每边10bp下的逐年净收益  2026年仅截至10月30日  数值为百分比',7.0)),
('p','两策略在2022年和2023年的年度表现好于基准，但较低敞口也错过部分上涨。2024年突破策略盈利13.50%、回归策略盈利4.16%，均低于基准17.41%；2026年前10个月两策略与基准均为负收益。'),
('h2','净超额收益检验未通过'),
('table',(['94个月的策略减基准','上轨突破','重入带内回归'],[
['月均净超额  百分点']+[f"{active[k]['mean']*100:+.3f}" for k in K[:2]],
['HAC 95%区间  百分点']+[f"[{active[k]['ci95'][0]*100:+.3f}, {active[k]['ci95'][1]*100:+.3f}]" for k in K[:2]],
['Holm校正后双侧p值']+[f"{active[k]['holm_p_two_strategies']:.5f}" for k in K[:2]],
['预设净收益门槛','未通过','未通过']
],[3.0,2.05,2.05])),
('caption','表3  月收益使用同一持续账本；Bartlett HAC滞后3阶，正态近似双侧p值，Holm校正覆盖2个策略。'),
('p','通过须同时满足：月均超额为正、95%区间下限大于0、Holm p < 0.05，以及10bp下策略年化复合收益高于基准。本轮月均超额为负、区间跨0且年化落后。较小回撤不替代该门槛；未增加等风险或等敞口实验来补救失败结果。'),
('h2','持仓与执行负担'),
('p','主口径突破策略72笔成交、36段持仓，平均每段15.19个交易日；回归策略68笔成交、34段持仓，平均12.38日。全期成交额分别约838.59万元与828.69万元，为平均净资产的72.14倍和67.72倍，均未年化。'),
('p','突破策略佣金4192.94元、滑点4192.95元；回归策略佣金4143.45元、滑点4143.42元。成交数包含再投资买单，不能直接等同于完整往返次数。基准9笔成交，佣金与滑点合计约120.75元。')]

p=page('成本压力与证据边界');p += [
('table',(['每边总摩擦','突破累计收益','回归累计收益','基准累计收益'],[[f'{bp}bp']+[pct(lookup[k,bp]['total_return']) for k in K] for bp in [0,10,30]],[1.6,1.8,1.8,1.9])),
('caption','表4  三个固定成本口径全部保留。零成本时两策略仍落后基准；压力场景不是择优候选。'),
('h2','%B只作时序描述'),
('p','%B与未来5个交易日TR收益的Pearson约0.0082、Spearman约−0.0219，共1892对观测，期末5个无标签日不参与。这里是单ETF时序关联，5日标签相互重叠，既非横截面IC，也非可执行组合收益；不作显著性、选方向或策略准入依据。'),
('h2','开盘成交与数据时点仍有缺口'),
('p','开盘检查只使用开盘价、已知前收盘与除息现金参考价。无效开盘或接近保守正负10%边界一个0.001元价位以内时延后，不使用当天收盘后才知道的高低价或全天成交量决定成交。三个10bp账户各记录一次本地边界检查阻挡，不能称为交易所拒单或真实未成交证明。'),
('p','行情来自腾讯公开历史快照，分红来自东方财富。2140日价格与日历完整性及原始缓存重建一致性已检查，但较早分红缺完整公告时点链，历史盘口与涨跌停状态也不完整。结果依赖固定摩擦、零现金收益和开盘成交假设，不构成实盘成交认证。'),
('h2','来源与核验范围'),
('p','Bollinger官方规则说明：触带本身不是交易信号，带外收盘可提示趋势延续，20期与2倍标准差仅是默认值。官方筛选提供从下轨外重回带内的候选条件。本报告的中轨退出、回归入场上限、仓位与执行均为本地补全，不把筛选条件包装成原作者已证明有效的完整策略。'),
('p',('独立实现已复核2140日BOLL与目标状态，以及9个固定情景的账户、交易和统计，未发现实现差异。该核验只检查模型实现，不补足历史成交与分红时点证据。两策略均不进入实盘策略库，也未发送实盘订单。' if sealed else '独立实现核验正在完成，当前为待审稿。只有最终核验通过后才封版；核验只检查模型实现，不补足历史成交与分红时点证据。两策略均不进入实盘策略库，也未发送实盘订单。')),
('sources',[
('Bollinger官方指标介绍','https://www.bollingerbands.com/bollinger-bands'),
('Bollinger官方使用规则 第6至9及12至18条','https://www.bollingerbands.com/bollinger-band-rules'),
('Bollinger Bands官方筛选说明 %b与BandWidth','https://bollingerbands.us/help-screening.php')]),
('caption','复现依据：冻结协议及预结果修订、summary.json、逐日账户与成交、annual-returns.csv、holding-episodes.csv。报告与图表可重建，不放入轻量迁移包；保留精简结论与关键证据。研究编号 20261103-boll-etf-v1。')]

# DOCX: restrained Letter report, black headings, bounded data tables, no callout boxes.
doc=Document();sec=doc.sections[0]
sec.page_width=Inches(8.5);sec.page_height=Inches(11)
sec.top_margin=Inches(.64);sec.bottom_margin=Inches(.62);sec.left_margin=Inches(.7);sec.right_margin=Inches(.7)
sec.footer_distance=Inches(.28)
fontname='Noto Sans CJK SC'
for name in ['Normal','Title','Subtitle','Heading 1','Heading 2','Caption']:
    st=doc.styles[name];st.font.name=fontname;st.font.color.rgb=RGBColor(0,0,0)
    st._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),fontname)
    for attr in ['ascii','hAnsi','cs']:st._element.rPr.rFonts.set(qn('w:'+attr),fontname)
    st.paragraph_format.space_after=Pt(5)
doc.styles['Normal'].font.size=Pt(10.5);doc.styles['Normal'].paragraph_format.line_spacing=1.12
for name,size in [('Title',19),('Subtitle',10),('Heading 1',14),('Heading 2',11.5),('Caption',9)]:doc.styles[name].font.size=Pt(size)
doc.styles['Title'].paragraph_format.space_after=Pt(7)
doc.styles['Subtitle'].paragraph_format.space_after=Pt(12)
doc.styles['Heading 1'].paragraph_format.space_before=Pt(9);doc.styles['Heading 1'].paragraph_format.space_after=Pt(7)
doc.styles['Heading 2'].paragraph_format.space_before=Pt(7);doc.styles['Heading 2'].paragraph_format.space_after=Pt(4)
doc.styles['Subtitle'].font.italic=False
doc.styles['Caption'].font.bold=False
doc.styles['Caption'].font.italic=False
doc.styles['Caption'].paragraph_format.line_spacing=1.1
doc.styles['Caption'].paragraph_format.space_after=Pt(8)
# No title paragraph rules or theme color overrides.
for sty in doc.styles:
    if sty.type==1:
        ppr=sty._element.find(qn('w:pPr'))
        if ppr is not None:
            for child in list(ppr):
                if child.tag==qn('w:pBdr'):ppr.remove(child)
footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
r=footer.add_run('BOLL指标在沪深300ETF的历史验证  ');r.font.size=Pt(8)
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');footer._p.append(fld)
doc.core_properties.title='BOLL指标在沪深300ETF的历史验证';doc.core_properties.subject='510300 ETF 固定BOLL规则历史验证';doc.core_properties.author='';doc.core_properties.keywords='BOLL, 510300, 历史验证'

def addtable(headers,data,widths):
    table=doc.add_table(rows=1,cols=len(headers));table.alignment=WD_TABLE_ALIGNMENT.CENTER;table.autofit=False
    for col,width in zip(table.columns,widths):col.width=Inches(width)
    tblpr=table._tbl.tblPr;borders=OxmlElement('w:tblBorders')
    for edge in ['top','left','bottom','right','insideH','insideV']:
        node=OxmlElement('w:'+edge);node.set(qn('w:val'),'single');node.set(qn('w:sz'),'5');node.set(qn('w:color'),'D9D9D9');borders.append(node)
    tblpr.append(borders)
    for i,rowdata in enumerate([headers]+data):
        cells=table.rows[0].cells if i==0 else table.add_row().cells
        for j,(cell,txt) in enumerate(zip(cells,rowdata)):
            cell.width=Inches(widths[j]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr=cell._tc.get_or_add_tcPr();marg=OxmlElement('w:tcMar')
            for edge,val in [('top',65),('bottom',65),('left',100),('right',100)]:
                el=OxmlElement('w:'+edge);el.set(qn('w:w'),str(val));el.set(qn('w:type'),'dxa');marg.append(el)
            tcpr.append(marg)
            shd=OxmlElement('w:shd');shd.set(qn('w:fill'),'444444' if i==0 else ('F5F5F5' if i%2==0 else 'FFFFFF'));tcpr.append(shd)
            pp=cell.paragraphs[0];pp.alignment=WD_ALIGN_PARAGRAPH.LEFT if j==0 else WD_ALIGN_PARAGRAPH.CENTER
            pp.paragraph_format.space_after=Pt(0);pp.paragraph_format.line_spacing=1.08
            run=pp.add_run(str(txt));run.font.size=Pt(9.5);run.bold=(i==0);run.font.color.rgb=RGBColor(255,255,255) if i==0 else RGBColor(0,0,0)
        trpr=table.rows[i]._tr.get_or_add_trPr();cant=OxmlElement('w:cantSplit');trpr.append(cant)
        if i==0:
            rep=OxmlElement('w:tblHeader');trpr.append(rep)
    doc.add_paragraph().paragraph_format.space_after=Pt(0)

def addlink(p,text,url):
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    h=OxmlElement('w:hyperlink');h.set(qn('r:id'),p.part.relate_to(url,RT.HYPERLINK,is_external=True))
    rr=OxmlElement('w:r');prop=OxmlElement('w:rPr');c=OxmlElement('w:color');c.set(qn('w:val'),'244F70');prop.append(c)
    size=OxmlElement('w:sz');size.set(qn('w:val'),'18');prop.append(size);rr.append(prop);t=OxmlElement('w:t');t.text=text;rr.append(t);h.append(rr);p._p.append(h)

for pi,blocks in enumerate(pages):
    # Page breaks belong to the next heading, avoiding a trailing blank page.
    for typ,v in blocks:
        if typ in ['title','sub','h1','h2','p','caption']:
            style={'title':'Title','sub':'Subtitle','h1':'Heading 1','h2':'Heading 2','p':'Normal','caption':'Caption'}[typ]
            pp=doc.add_paragraph(v,style)
            if pi and typ=='h1' and v==blocks[0][1]:pp.paragraph_format.page_break_before=True
            if typ=='p' and v.startswith('结论：'):
                pp.runs[0].bold=True
        elif typ=='table':addtable(*v)
        elif typ=='figure':
            name,caption,width=v;pp=doc.add_paragraph();pp.paragraph_format.space_after=Pt(3);pp.paragraph_format.keep_with_next=True
            rr=pp.add_run();inline=rr.add_picture(str(OUT/name),width=Inches(width))
            inline._inline.docPr.set('descr',caption)
            doc.add_paragraph(caption,'Caption')
        elif typ=='sources':
            for label,url in v:
                pp=doc.add_paragraph(style='Caption');pp.paragraph_format.space_after=Pt(3);addlink(pp,label,url)

doc.save(OUT/'report.docx')

# Self-contained HTML, same authored narrative and data; PNGs embedded as data URIs.
parts=['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>BOLL指标在沪深300ETF的历史验证</title><style>']
parts.append('''*{box-sizing:border-box}body{margin:0;background:#eee;color:#111;font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;line-height:1.65;font-size:16px}.page{max-width:900px;margin:24px auto;background:#fff;padding:48px 58px}h1{font-size:30px;line-height:1.4;margin:0 0 10px;color:#000}h2{font-size:22px;margin:16px 0 12px;color:#000}h3{font-size:17px;margin:16px 0 6px;color:#000}p{margin:10px 0}.subtitle,.caption{font-size:13px}.subtitle{margin-bottom:20px}.caption{line-height:1.5;color:#333}figure{margin:12px 0}figure img{width:100%;height:auto;display:block}figcaption{font-size:13px;line-height:1.5;margin-top:8px}table{width:100%;border-collapse:collapse;font-size:14px;margin:14px 0 7px}th,td{border:1px solid #d9d9d9;padding:9px 12px;text-align:center;vertical-align:middle}th:first-child,td:first-child{text-align:left}th{background:#444;color:#fff}tbody tr:nth-child(even){background:#f5f5f5}a{color:#244f70} @media(max-width:640px){.page{padding:24px 20px;margin:12px auto}body{font-size:15px}h1{font-size:25px}h2{font-size:20px}th,td{padding:7px 6px;font-size:12px}}@media print{body{background:white;font-size:11pt}.page{margin:0;max-width:none;padding:0;break-after:page}.page:last-child{break-after:auto}h1{font-size:20pt}h2{font-size:14pt}h3{font-size:11.5pt}table{font-size:9.5pt}figure{break-inside:avoid}p{orphans:3;widows:3}@page{size:Letter;margin:.65in .7in}}''')
parts.append('</style></head><body>');plain=[]
for pi,blocks in enumerate(pages):
    parts.append(f'<section class="page" aria-label="第{pi+1}部分">')
    for typ,v in blocks:
        if typ in ['title','sub','h1','h2','p','caption']:
            tag={'title':'h1','sub':'p','h1':'h2','h2':'h3','p':'p','caption':'p'}[typ];cl={'sub':' class="subtitle"','caption':' class="caption"'}.get(typ,'')
            txt=html.escape(v)
            if v.startswith('结论：'):txt=f'<strong>{txt}</strong>'
            parts.append(f'<{tag}{cl}>{txt}</{tag}>');plain.append(v+'\n')
        elif typ=='table':
            headers,data,widths=v;parts.append('<table><thead><tr>'+''.join(f'<th scope="col">{html.escape(x)}</th>' for x in headers)+'</tr></thead><tbody>')
            for row in data:parts.append('<tr>'+''.join(f'<td>{html.escape(str(x))}</td>' for x in row)+'</tr>')
            parts.append('</tbody></table>');plain.append(' | '.join(headers)+'\n'+'\n'.join(' | '.join(row) for row in data)+'\n')
        elif typ=='figure':
            name,cap,width=v;data=base64.b64encode((OUT/name).read_bytes()).decode()
            parts.append(f'<figure><img src="data:image/png;base64,{data}" alt="{html.escape(cap)}"><figcaption>{html.escape(cap)}</figcaption></figure>');plain.append(cap+'\n')
        elif typ=='sources':
            for label,url in v:parts.append(f'<p class="caption"><a href="{html.escape(url)}">{html.escape(label)}</a></p>');plain.append(label+' '+url+'\n')
    parts.append('</section>')
parts.append('</body></html>')
(OUT/'report.html').write_text('\n'.join(parts))
(OUT/'report-text.txt').write_text('\n'.join(plain))

source_files=[R/'protocol.json',R/'amendments.json',R/'key-evidence.json',D/'summary.json',D/'annual-returns.csv',D/'holding-episodes.csv']+[D/f'{k}-10bp-daily.csv' for k in K]
(OUT/'author-inputs.json').write_text(json.dumps({'sealed':sealed,'validation_sha256':hashlib.sha256(validation_path.read_bytes()).hexdigest() if validation_path.exists() else None,'source_files':{os.path.relpath(p,ROOT):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},'daily_rows_per_series':1897,'charts':'Every source daily observation, no smoothing; peak includes initial 100000 cash. Annual values from CSV.','runtime_python':os.environ.get('CODEX_PRIMARY_RUNTIME_PYTHON')},ensure_ascii=False,indent=2))
print('Created draft' if not sealed else 'Created sealed report')
