from PIL import Image, ImageDraw, ImageFont
from io import BytesIO


def render_report(data):
    s, risk = data['snapshot'], data['risk']
    positions = [(a, p) for a in s['accounts'] for p in a.get('positions', []) if p.get('quantity', 0) > 0]
    positions.sort(key=lambda ap: float(ap[1].get('market_value_base') or 0), reverse=True)
    stop_items = risk['stop_loss'].get('items', [])
    W, H = 1200, 1750 + max(0, len(positions)-6)*93 + max(0, len(stop_items)-3)*48
    im = Image.new('RGB', (W,H), '#f2f5fa')
    d = ImageDraw.Draw(im)
    regular = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    bold = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
    def font(n, heavy=False): return ImageFont.truetype(bold if heavy else regular, n)
    def txt(x,y,t,n=24,color='#14213a',heavy=False,anchor=None): d.text((x,y),str(t),font=font(n,heavy),fill=color,anchor=anchor)
    def card(x1,y1,x2,y2,fill='#ffffff'): d.rounded_rectangle((x1,y1,x2,y2), radius=22, fill=fill)
    def money(v): return '—' if v is None else f'{float(v):,.0f}'
    def pct(v): return '—' if v is None else f'{float(v):+.2f}%'
    def badge(x,y,label,color,bg):
        b=d.textbbox((0,0),label,font=font(19,True)); w=b[2]-b[0]+24
        d.rounded_rectangle((x,y,x+w,y+34),radius=9,fill=bg); txt(x+12,y+6,label,19,color,True)
        return w

    card(25,25,1175,188,'#14243e')
    txt(58,50,'每日持仓概览',42,'#ffffff',True)
    txt(60,112,'全部账户  /  先进先出 FIFO  /  人民币汇总',21,'#b9c9dc')
    txt(1137,67,'每日更新',21,'#bcd4ef',False,'ra')
    txt(1137,111,data['generated']+'  北京时间',20,'#b9c9dc',False,'ra')

    for i,(label,key) in enumerate([('总权益','total_equity'),('持仓市值','total_market_value'),('总现金','total_cash')]):
        x=25+i*390; card(x,210,x+370,350); txt(x+24,234,label,23,'#6b7890'); txt(x+24,278,'¥ '+money(s.get(key)),34,'#17253d',True)

    txt(30,383,'风险与暴露',29,'#18283e',True)
    txt(1167,391,'红色表示达到预警条件',19,'#8592a5',False,'ra')
    card(25,430,1175,696)
    conc=risk['concentration']; sector=risk['sector_concentration']; dd=risk['drawdown']; stop=risk['stop_loss']
    drawdown_available = dd.get('series_points', 0) >= 2 and dd.get('current_drawdown_pct') is not None
    blocks=[('个股集中度',f"{conc.get('top_weight_pct',0):.2f}%",'最大持仓权重',bool(conc.get('alert'))),('行业集中度',f"{sector.get('top_weight_pct',0):.2f}%",'最大行业权重',bool(sector.get('alert'))),('当前回撤',f"{dd['current_drawdown_pct']:.2f}%" if drawdown_available else '不可用',f"历史最大 {dd.get('max_drawdown_pct',0):.2f}%" if drawdown_available else '历史数据不足',bool(drawdown_available and dd['current_drawdown_pct'] >= risk['thresholds']['drawdown_alert_pct'])),('止损预警',f"{stop.get('triggered_count',0)} 项",f"另有 {max(0,stop.get('near_count',0)-stop.get('triggered_count',0))} 项接近",bool(stop.get('triggered_count')))]
    for i,(label,value,caption,alert) in enumerate(blocks):
        x=52+i*280; txt(x,462,label,22,'#6b7890'); txt(x,510,value,37,'#dc4b42' if alert else '#153858',True); txt(x,570,caption,20,'#8995a6')
        if i<3:d.line((x+255,460,x+255,605),fill='#e9eef4',width=2)
    warnings = []
    if data.get('fx_failed') or s.get('fx_stale'): warnings.append('当前汇率未更新')
    if dd.get('fx_stale'): warnings.append('历史回撤含旧汇率')
    if any(p.get('price_stale') or p.get('price_available') is False for _, p in positions): warnings.append('部分行情未更新')
    txt(52,643,'数据提示：' + '；'.join(warnings) if warnings else '回撤依据历史资产快照计算',19,'#b07b24')

    y=735; txt(30,y,'持仓明细',29,'#18283e',True); txt(1167,y+7,f'共 {len(positions)} 项 · 市值按账户币种',19,'#8592a5',False,'ra')
    top=y+47; bottom=top+66+len(positions)*93+18; card(25,top,1175,bottom)
    for x,label in [(55,'持仓 / 账户'),(460,'数量'),(645,'最新价'),(825,'持仓市值'),(1136,'盈亏比例')]:txt(x,top+22,label,19,'#8491a4',False,'ra' if x>55 else None)
    d.line((52,top+61,1148,top+61),fill='#e8edf4',width=2)
    for i,(a,p) in enumerate(positions):
        yy=top+72+i*93; val=p.get('unrealized_pnl_pct') if p.get('price_available') is not False else None; color='#dc5149' if val is not None and val<0 else '#19a275'; curr=p.get('valuation_currency') or p.get('currency') or ''
        txt(55,yy,p.get('name') or p.get('symbol'),25,'#18283e',True); txt(55,yy+35,f"{p.get('symbol')} · {a.get('account_name','')}",18,'#8d9bad')
        price = p.get('last_price') if p.get('price_available') is not False else None
        txt(460,yy+12,f"{p.get('quantity',0):,.0f}",22,'#283750',False,'ra'); txt(645,yy+8,f"{price:,.3f}" if price is not None else '—',22,'#283750',False,'ra')
        price_date = str(p.get('price_date') or '')[:10]
        if price_date: txt(645,yy+40,price_date + (' 旧' if p.get('price_stale') else ''),14,'#9a7b48' if p.get('price_stale') else '#9aa7b7',False,'ra')
        txt(825,yy+12,money(p.get('market_value_base') if price is not None else None),22,'#283750',False,'ra'); txt(825,yy+39,curr,16,'#9aa7b7',False,'ra'); txt(1136,yy+12,pct(val),25,color,True,'ra')
        if i<len(positions)-1:d.line((52,yy+79,1148,yy+79),fill='#eff2f6',width=1)

    yy=bottom+35; txt(30,yy,'止损与回撤提示',29,'#18283e',True); yy+=50
    items=stop_items; stop_height=190+max(0,len(items)-3)*48; card(25,yy,1175,yy+stop_height)
    if items:
        for i,p in enumerate(items):
            row=yy+22+i*48; trig=p.get('is_triggered'); name=next((v.get('name') for a,v in positions if v.get('symbol')==p['symbol']),None) or p['symbol']
            badge(48,row,'已触发' if trig else '接近阈值','#c4493e' if trig else '#ad741b','#fff0ed' if trig else '#fff6e6')
            txt(175,row+5,f"{name}  {p['symbol']}  ·  {p.get('account_name','')}",21,'#33435a'); txt(1137,row+5,f"较成本 -{p.get('loss_pct',0):.2f}%",22,'#d25049',True,'ra')
    else:txt(52,yy+28,'当前没有接近或达到止损阈值的持仓',22,'#687991')
    txt(52,yy+stop_height-27,'止损提示按持仓成本和亏损阈值计算，并非个股预设止损价。',18,'#8a98a9')
    if yy+stop_height+15 < H: txt(600, H-37,'数据来源：持仓账户与行情快照',18,'#a1adbb',False,'ma')
    out = BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()
