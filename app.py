"""Dash site: borough-year integration of HPD affordable housing starts and DOT SIRTA.
To start: python pipeline.py && python app.py (or gunicorn app:server).
"""
from pathlib import Path
import re
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State
from pipeline import DATA, BOROUGHS, run

CHART_QUESTIONS = [
 'Q1 · Do borough-years with more affordable units started also have more SIRTA records?',
 'Q2 · How do housing starts relate to severe traffic injuries by borough-year?',
 'Q3 · Are new-construction housing units associated with more road fatalities?',
 'Q4 · Does housing preservation occur alongside higher serious-crash reporting?',
 'Q5 · Do borough-years with more distinct housing projects also report more severe injuries?',
 'Q6 · How does building-level project activity align with road fatalities?',
 'Q7 · Which borough-years combine substantial housing activity with severe-injury burden?',
 'Q8 · Do citywide housing start and severe-injury trends move together over time?',
 'Q9 · Where do housing starts and severe injuries diverge most in relative intensity?',
 'Q10 · Which boroughs carry different shares of housing production and SIRTA records?',
 'Q11 · Do year-on-year changes in housing starts match changes in SIRTA records?',
 'Q12 · Do larger housing projects coincide with more severe injuries per SIRTA record?'
]
COLORS = px.colors.qualitative.Bold


def fetch_local_or_download():
    housing_file, transport_file = DATA/'housing_clean.csv', DATA/'transport_clean.csv'
    if not housing_file.exists() or not transport_file.exists():
        run()
    housing, transport = pd.read_csv(housing_file), pd.read_csv(transport_file)
    for df in (housing, transport):
        df['year'] = pd.to_numeric(df['year'], errors='coerce').astype('Int64')
    return housing, transport


def selection_data(housing, transport, borough='All', year='All', construction='All', severity='All'):
    hh, tt = housing.copy(), transport.copy()
    if borough != 'All':
        hh = hh[hh['borough'].eq(borough)]; tt = tt[tt['borough'].eq(borough)]
    if year != 'All':
        hh = hh[hh['year'].eq(int(year))]; tt = tt[tt['year'].eq(int(year))]
    if construction != 'All':
        hh = hh[hh['construction_type'].eq(construction)]
    if severity != 'All':
        tt = tt[tt['severity_band'].eq(severity)]
    keys = ['borough','year']
    ha = (hh.groupby(keys).agg(housing_units=('all_counted_units','sum'),
              housing_records=('building_id','size'), housing_projects=('project_id','nunique'))
          .reset_index())
    new = (hh.assign(new_units=np.where(hh['construction_type'].eq('New Construction'),hh['all_counted_units'],0),
                     preservation_units=np.where(hh['construction_type'].eq('Preservation'),hh['all_counted_units'],0))
           .groupby(keys)[['new_units','preservation_units']].sum().reset_index())
    ha = ha.merge(new, on=keys, how='left')
    ta = (tt.groupby(keys).agg(sirta_records=('crash_date','size'),
            severe_injuries=('total_severe_injuries','sum'), fatalities=('total_fatalities','sum'),
            nonsevere_injuries=('total_non_severe_injuries','sum')).reset_index())
    # Compare only key pairs represented in both selected sets; zero-filled rows could mislead.
    m = ha.merge(ta, on=keys, how='inner', validate='one_to_one').sort_values(keys)
    return m, hh, tt


def query_parser(query, borough, year, construction, severity):
    if not query or not query.strip(): return borough, year, construction, severity
    q = query.lower()
    for b in BOROUGHS:
        if b.lower() in q: borough = b
    years = re.findall(r'\b20(?:2[2-5])\b', q)
    if years: year = int(years[-1])
    if 'new construction' in q or 'new building' in q: construction = 'New Construction'
    if 'preservation' in q or 'preserved' in q: construction = 'Preservation'
    if 'fatal' in q or 'death' in q: severity = 'Fatality recorded'
    elif 'severe' in q: severity = 'Severe injury recorded'
    return borough, year, construction, severity


def style(fig, title, x=None, y=None):
    fig.update_layout(title={'text':title,'font':{'size':13}},
        paper_bgcolor='#FFFFFF', plot_bgcolor='#FAFCFF',
        font={'family':'Arial, sans-serif','color':'#1C3350'},
        height=390, margin=dict(l=37,r=25,t=70,b=45),
        legend=dict(orientation='h',y=-.25,x=0))
    fig.update_xaxes(showgrid=True,gridcolor='#E8EFF7',title_text=x)
    fig.update_yaxes(showgrid=True,gridcolor='#E8EFF7',title_text=y)
    return fig


def unavailable(title):
    f=go.Figure();f.add_annotation(text='No overlapping observations for this selection',
        x=.5,y=.5,xref='paper',yref='paper',showarrow=False)
    return style(f,title)


def figures(m):
    if m.empty: return [unavailable(q) for q in CHART_QUESTIONS]
    d = m.copy()
    for c in d.columns.difference(['borough','year']):d[c] = pd.to_numeric(d[c],errors='coerce').fillna(0)
    d['year_label']=d['year'].astype(str)
    d['units_per_project'] = d['housing_units'] / d['housing_projects'].replace(0,np.nan)
    d['severe_per_record'] = d['severe_injuries'] / d['sirta_records'].replace(0,np.nan)
    common=dict(color='borough',hover_data=['year'])
    fig=[]
    scatter_specs=[
        ('housing_units','sirta_records','Affordable units started','SIRTA records'),
        ('housing_units','severe_injuries','Affordable units started','Severe injuries'),
        ('new_units','fatalities','New-construction affordable units','Fatalities'),
        ('preservation_units','sirta_records','Preservation affordable units','SIRTA records'),
        ('housing_projects','severe_injuries','Distinct housing projects','Severe injuries'),
        ('housing_records','fatalities','Housing building-project records','Fatalities'),
    ]
    for i, (x,y,xname,yname) in enumerate(scatter_specs):
        p=px.scatter(d,x=x,y=y,**common,hover_name='year_label',color_discrete_sequence=COLORS)
        p.update_traces(marker={'size':12,'opacity':.85,'line':{'width':1,'color':'white'}})
        fig.append(style(p,CHART_QUESTIONS[i],xname,yname))
    p=px.scatter(d,x='housing_units',y='sirta_records',color='borough',
         size=d['severe_injuries'].clip(lower=0)+1,size_max=36,
         hover_data=['year','severe_injuries','fatalities'],color_discrete_sequence=COLORS)
    fig.append(style(p,CHART_QUESTIONS[6],'Affordable units started','SIRTA records (size = severe injuries + 1)'))
    annual=d.groupby('year',as_index=False)[['housing_units','severe_injuries','sirta_records']].sum().sort_values('year')
    norm=annual[['year','housing_units','severe_injuries']].melt('year',var_name='Metric',value_name='Value')
    norm['Index (max = 100)']=norm.groupby('Metric')['Value'].transform(lambda s:100*s/s.max() if s.max()>0 else s*0)
    p=px.line(norm,x='year',y='Index (max = 100)',color='Metric',markers=True,
              color_discrete_sequence=['#067A91','#E6813F'])
    fig.append(style(p,CHART_QUESTIONS[7],'Year','Within-selection relative index (max=100)'))
    # Relative z-score difference is descriptive only, NOT a safety risk rate.
    for key in ['housing_units','severe_injuries']:
        sd=d[key].std(ddof=0)
        d[key+'_z']=(d[key]-d[key].mean())/sd if sd and np.isfinite(sd) else 0
    d['difference_z']=d['housing_units_z']-d['severe_injuries_z']
    pivot=d.pivot(index='borough',columns='year',values='difference_z')
    p=go.Figure(data=go.Heatmap(z=pivot.values,x=[str(x) for x in pivot.columns],
              y=list(pivot.index),zmid=0,colorscale='RdBu',reversescale=False,
              colorbar={'title':'Housing z − injury z'},hovertemplate='Year %{x}<br>Borough %{y}<br>Z-score difference %{z:.2f}<extra></extra>'))
    fig.append(style(p,CHART_QUESTIONS[8],'Year','Borough'))
    borough=d.groupby('borough',as_index=False)[['housing_units','sirta_records']].sum()
    for field in ['housing_units','sirta_records']:
        total=borough[field].sum()
        borough[field+'_share']=100*borough[field]/total if total>0 else 0
    br=borough.melt('borough',value_vars=['housing_units_share','sirta_records_share'],
                    var_name='Measure',value_name='Share of selected total (%)')
    br['Measure']=br['Measure'].replace({'housing_units_share':'Share of housing units',
                                      'sirta_records_share':'Share of SIRTA records'})
    p=px.bar(br,x='borough',y='Share of selected total (%)',color='Measure',barmode='group',
             color_discrete_sequence=['#067A91','#E6813F'])
    fig.append(style(p,CHART_QUESTIONS[9],'Borough','Percentage of selected domain total'))
    growth=annual[['year','housing_units','sirta_records']].copy()
    for key in ['housing_units','sirta_records']:
        growth[key+'_growth']=growth[key].pct_change(fill_method=None)*100
    gr=growth.melt('year',value_vars=['housing_units_growth','sirta_records_growth'],
                   var_name='Metric',value_name='Change (%)').dropna()
    if len(gr):
        p=px.line(gr,x='year',y='Change (%)',color='Metric',markers=True,
                  color_discrete_sequence=['#067A91','#E6813F'])
        p.add_hline(y=0,line_dash='dot',line_color='gray')
        fig.append(style(p,CHART_QUESTIONS[10],'Year','Year-on-year change (%)'))
    else: fig.append(unavailable(CHART_QUESTIONS[10]+' · requires multiple years'))
    p=px.scatter(d,x='units_per_project',y='severe_per_record',color='borough',
           hover_data=['year','housing_units','housing_projects','severe_injuries','sirta_records'],
           color_discrete_sequence=COLORS)
    p.update_traces(marker={'size':12})
    fig.append(style(p,CHART_QUESTIONS[11],'Affordable units per housing project',
                      'Severe injuries per SIRTA record'))
    return fig


def story_text(m):
    if m.empty:
        return 'The selected filters produce no borough-year pairs observed in both datasets. Try a wider selection; unmatched pairs are not silently treated as zero.'
    total_units=int(m['housing_units'].sum()); events=int(m['sirta_records'].sum()); severe=int(m['severe_injuries'].sum())
    h=m.groupby('borough')['housing_units'].sum().sort_values(ascending=False)
    t=m.groupby('borough')['sirta_records'].sum().sort_values(ascending=False)
    return (f'Question: Where do affordable housing project starts and serious-road-injury records overlap? '
            f'In the selected {len(m)} borough-year observations, HPD reports {total_units:,} affordable '
            f'units associated with project starts, while DOT SIRTA contains {events:,} records and '
            f'{severe:,} recorded severe injuries. {h.index[0]} has the largest housing-unit total '
            f'within this selection; {t.index[0]} has the most SIRTA records. '
            'Important: SIRTA covers selected serious crashes rather than every crash, and an HPD project '
            'start does not mean a home was completed in that year. Different definitions, population sizes, '
            'reporting coverage, and location/time confounders mean these are patterns, NOT evidence that '
            'housing causes crashes. NYC planners could use the comparisons to prioritize further localized '
            'study, not to conclude causation.')


ERROR = None
try:
    H, T=fetch_local_or_download()
except Exception as e:
    ERROR=f'Data could not be downloaded or loaded: {type(e).__name__}: {e}. Run python pipeline.py with internet access.'
    H, T=None,None

app=Dash(__name__,title='NYC Housing × Road Safety')
server=app.server

def dropdown(title,id,options,value):
    return html.Div([html.Label(title),dcc.Dropdown(options=[{'label':str(v),'value':v} for v in options],
                    id=id,value=value,clearable=False,style={'color':'#14233A'})],className='field')

all_years=sorted(set(H['year'].dropna().astype(int))&set(T['year'].dropna().astype(int))) if ERROR is None else [2022,2023,2024,2025]
construction_types=sorted(str(x) for x in H['construction_type'].dropna().unique()) if ERROR is None else ['New Construction','Preservation']
severity_types=sorted(str(x) for x in T['severity_band'].dropna().unique()) if ERROR is None else ['Fatality recorded','Severe injury recorded']
app.layout=html.Div(className='container',children=[
    html.Div(className='top',children=[html.Span('GIU · ICS503 · MILESTONE 1',className='badge'),
         html.H1('NYC Housing × Road Safety'),
         html.P('Exploring whether boroughs with more affordable housing project starts also show more serious traffic injury reporting · Official NYC Open Data · 2022–2025',className='muted')]),
    html.Div(className='panel',children=[html.H2('Generate an interactive report'),
         html.Div(className='inputs',children=[
             dropdown('Borough','borough',['All']+BOROUGHS,'All'),
             dropdown('Year','year',['All']+all_years,'All'),
             dropdown('Housing construction type','construction',['All']+construction_types,'All'),
             dropdown('SIRTA severity category','severity',['All']+severity_types,'All'),
             html.Div(className='field',children=[html.Label('Search mode (borough, year, type, severity)'),
               dcc.Input(id='search',type='text',placeholder='Brooklyn 2023 preservation fatal',debounce=True)])
         ]),html.Br(),html.Button('GENERATE REPORT',id='generate',className='btn',n_clicks=0),
         html.P('Filters take effect when you click Generate Report. You can also type a plain-language search.',className='muted'),
         html.Div(ERROR or '',id='error',style={'color':'#ff9b9b'})]),
    html.Div(className='kpis',children=[html.Div(className='kpi',children=[html.Small(label),html.Strong(id=idx)]) for label,idx in [
        ('Affordable units in started projects','kpi-units'),('SIRTA records','kpi-events'),
        ('Severe injuries','kpi-injuries'),('Matched borough-year groups','kpi-groups')]]),
    html.Div(className='panel',style={'marginTop':'20px'},children=[html.H2('The story'),html.P(id='story',className='story')]),
    html.H2('12 research questions · 12 interactive visualizations'),
    html.Div(className='charts',children=[html.Div(className='chart',children=[dcc.Graph(id=f'chart-{i}',config={'displaylogo':False,'scrollZoom':True})]) for i in range(12)]),
    html.Div(className='panel',style={'marginTop':'22px'},children=[html.H2('What the data cannot prove'),
      html.P('Comparing annual borough totals does not control for population, traffic volumes, built environment, or variation in event reporting. Project start dates are not completion dates. SIRTA data does not cover every road collision. This tool detects co-occurrence, not a causal effect or a per-person safety risk.',className='story')]),
    html.Div(className='footer',children='Sources: HPD Affordable Housing Production by Building (hg8x-zxpr) · DOT SIRTA (xeqp-qz8h) · Aggregated borough × year. Project for GIU Data Engineering and Visualization.')
])

@app.callback([Output(f'chart-{i}','figure') for i in range(12)]+[
  Output('kpi-units','children'),Output('kpi-events','children'),Output('kpi-injuries','children'),
  Output('kpi-groups','children'),Output('story','children'),
  Output('borough','value'),Output('year','value'),Output('construction','value'),Output('severity','value')],
  Input('generate','n_clicks'),State('borough','value'),State('year','value'),
  State('construction','value'),State('severity','value'),State('search','value'))
def regenerate(_n,borough,year,construction,severity,query):
    if ERROR is not None:
        return [unavailable(q) for q in CHART_QUESTIONS]+['—']*4+[ERROR,borough,year,construction,severity]
    borough,year,construction,severity=query_parser(query,borough,year,construction,severity)
    m,hh,tt=selection_data(H,T,borough,year,construction,severity)
    return figures(m)+[f'{m.housing_units.sum():,.0f}',f'{m.sirta_records.sum():,.0f}',
         f'{m.severe_injuries.sum():,.0f}',str(len(m)),story_text(m),borough,year,construction,severity]

if __name__=='__main__':
    app.run(debug=True,host='0.0.0.0',port=8050)
