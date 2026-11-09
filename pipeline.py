"""Official NYC Open Data ETL for affordable housing starts & SIRTA road safety.
Run: python pipeline.py
No fabricated or synthetic input data is used.
"""
from pathlib import Path
import json
import pandas as pd
import numpy as np
import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
HOUSING_ID = 'hg8x-zxpr'
TRANSPORT_ID = 'xeqp-qz8h'
START_YEAR, END_YEAR = 2022, 2025
BOROUGHS = ['Bronx', 'Brooklyn', 'Manhattan', 'Queens', 'Staten Island']
BOROUGH_MAP = {x.upper(): x for x in BOROUGHS}


def download_dataset(dataset_id, target, limit=50000, force=False):
    """Download full dataset within API limit (verified sizes in Nov 2026: ~9.6k/~13.8k).
    Fail closed instead of making up substitute observations.
    """
    if target.exists() and not force:
        return pd.read_csv(target, low_memory=False)
    url = f'https://data.cityofnewyork.us/resource/{dataset_id}.csv'
    response = requests.get(url, params={'$limit': limit}, timeout=95,
                            headers={'User-Agent': 'GIU-ICS503-Educational-Project/1.0'})
    response.raise_for_status()
    if not response.content:
        raise RuntimeError(f'No rows returned for {dataset_id}')
    target.write_bytes(response.content)
    frame = pd.read_csv(target, low_memory=False)
    if frame.empty:
        raise RuntimeError(f'Empty dataset {dataset_id}')
    if len(frame) >= limit:
        raise RuntimeError(f'{dataset_id} reached {limit} rows: increase API limit or paginate before analysis.')
    return frame


def overview(df, label):
    return {
        'dataset': label, 'rows': int(len(df)), 'columns': int(len(df.columns)),
        'duplicate_full_rows': int(df.duplicated().sum()),
        'null_percentage_top_10': (df.isna().mean().sort_values(ascending=False).head(10) * 100).round(2).to_dict()
    }


def normalize_borough(series):
    return series.astype('string').str.strip().str.upper().map(BOROUGH_MAP)


def clean_housing(raw):
    """Start date is loan/marketing milestone, not completed homes (explicit limitation)."""
    mandatory = {'project_start_date', 'borough', 'all_counted_units', 'building_id', 'project_id'}
    if not mandatory.issubset(raw.columns):
        raise ValueError(f'Missing housing columns: {mandatory - set(raw.columns)}')
    df = raw.copy().drop_duplicates()
    report = {'input': int(len(raw)), 'exact_duplicates_removed': int(len(raw) - len(df))}
    df['borough'] = normalize_borough(df['borough'])
    df['project_start_date'] = pd.to_datetime(df['project_start_date'], errors='coerce')
    df['year'] = df['project_start_date'].dt.year
    df['all_counted_units'] = pd.to_numeric(df['all_counted_units'], errors='coerce')
    # Preserve valid large buildings: IQR is reviewed/flagged, never used for blind trimming.
    units = df['all_counted_units'].dropna()
    if len(units):
        q1, q3 = units.quantile([.25, .75]); upper = q3 + 1.5 * (q3 - q1)
        report['iqr_flagged_units_not_deleted'] = int((df['all_counted_units'] > upper).sum())
    if 'reporting_construction_type' not in df:
        df['reporting_construction_type'] = 'Not recorded'
    df['construction_type'] = df['reporting_construction_type'].astype('string').str.strip().str.title().fillna('Not recorded')
    if 'project_completion_date' in df.columns:
        df['project_completion_date'] = pd.to_datetime(df['project_completion_date'], errors='coerce')
    df = df.loc[df['borough'].notna() & df['year'].between(START_YEAR, END_YEAR)
                & df['all_counted_units'].notna() & (df['all_counted_units'] >= 0)].copy()
    df['year'] = df['year'].astype(int)
    report['invalid_or_out_of_scope_removed'] = int(raw.shape[0] - report['exact_duplicates_removed'] - len(df))
    report['output'] = int(len(df))
    report['granularity'] = 'building-project record (repeated buildings across separate projects remain valid)'
    return df, report


def clean_transport(raw):
    required = {'crash_date', 'crash_borough', 'total_severe_injuries', 'total_fatalities'}
    if not required.issubset(raw.columns):
        raise ValueError(f'Missing transport columns: {required - set(raw.columns)}')
    df = raw.copy().drop_duplicates()
    report = {'input': int(len(raw)), 'exact_duplicates_removed': int(len(raw)-len(df))}
    df['borough'] = normalize_borough(df['crash_borough'])
    df['crash_date'] = pd.to_datetime(df['crash_date'], errors='coerce')
    df['year'] = df['crash_date'].dt.year
    for key in ['total_severe_injuries', 'total_fatalities', 'total_non_severe_injuries']:
        if key not in df: df[key] = np.nan
        df[key] = pd.to_numeric(df[key], errors='coerce')
    # Drop missing severity counts rather than silently convert unknown -> zero.
    df = df.loc[df['borough'].notna() & df['year'].between(START_YEAR, END_YEAR)
                & df['total_severe_injuries'].notna() & df['total_fatalities'].notna()
                & (df['total_severe_injuries'] >= 0) & (df['total_fatalities'] >= 0)].copy()
    df['total_non_severe_injuries'] = df['total_non_severe_injuries'].fillna(0).clip(lower=0)
    df['year'] = df['year'].astype(int)
    df['severity_band'] = np.select(
        [df['total_fatalities'] > 0, df['total_severe_injuries'] > 0],
        ['Fatality recorded', 'Severe injury recorded'], default='Other SIRTA record')
    for col in ['latitude', 'longitude']:
        if col in df: df[col] = pd.to_numeric(df[col], errors='coerce')
    report['invalid_or_out_of_scope_removed'] = int(len(raw) - report['exact_duplicates_removed']-len(df))
    report['output'] = int(len(df))
    report['granularity'] = 'SIRTA record; NOT all NYC crashes, and not population-adjusted risk'
    return df, report


def aggregate(housing, transport):
    keys = ['borough', 'year']
    h = (housing.groupby(keys, observed=True)
         .agg(housing_units=('all_counted_units', 'sum'), housing_records=('building_id', 'size'),
              housing_projects=('project_id', 'nunique')).reset_index())
    new = (housing.assign(new_units=np.where(housing['construction_type'].str.lower().eq('new construction'),
                                          housing['all_counted_units'], 0),
                          preservation_units=np.where(housing['construction_type'].str.lower().eq('preservation'),
                                                      housing['all_counted_units'], 0))
           .groupby(keys, observed=True)[['new_units', 'preservation_units']].sum().reset_index())
    h = h.merge(new, on=keys, validate='one_to_one')
    t = (transport.groupby(keys, observed=True)
         .agg(sirta_records=('crash_date','size'), severe_injuries=('total_severe_injuries','sum'),
              fatalities=('total_fatalities','sum'), nonsevere_injuries=('total_non_severe_injuries','sum'))
         .reset_index())
    joined = h.merge(t, on=keys, how='outer', indicator=True, validate='one_to_one')
    audit = {'housing_borough_year_groups': int(len(h)), 'transport_borough_year_groups': int(len(t)),
             'matched': int((joined['_merge']=='both').sum()),
             'housing_only': int((joined['_merge']=='left_only').sum()),
             'transport_only': int((joined['_merge']=='right_only').sum())}
    # Missing from either domain means no comparable observations: DO NOT infer zero.
    matched = joined.loc[joined['_merge'].eq('both')].drop(columns='_merge').copy()
    for metric in matched.columns.difference(keys):
        matched[metric] = pd.to_numeric(matched[metric], errors='coerce')
    matched = matched.dropna(subset=['housing_units','sirta_records','severe_injuries'])
    audit['integrated_rows_after_post_clean'] = int(len(matched))
    audit['key_duplicates_after_join'] = int(matched.duplicated(keys).sum())
    return matched, audit


def run(force=False):
    a = download_dataset(HOUSING_ID, DATA/'housing_raw.csv', force=force)
    b = download_dataset(TRANSPORT_ID, DATA/'transport_raw.csv', force=force)
    if a.shape[1] < 9 or b.shape[1] < 9:
        raise ValueError('At least nine source columns are required for EACH dataset.')
    housing, hc = clean_housing(a)
    transport, tc = clean_transport(b)
    combined, audit = aggregate(housing, transport)
    if combined.empty:
        raise RuntimeError('No overlapping borough-year data; investigate scope/data before reporting.')
    housing.to_csv(DATA/'housing_clean.csv', index=False)
    transport.to_csv(DATA/'transport_clean.csv', index=False)
    combined.to_csv(DATA/'integrated.csv', index=False)
    info = {'source_urls': {'housing': f'https://data.cityofnewyork.us/d/{HOUSING_ID}',
                             'transport': f'https://data.cityofnewyork.us/d/{TRANSPORT_ID}'},
            'period': f'{START_YEAR}–{END_YEAR}', 'housing_raw': overview(a, 'Affordable Housing Production by Building'),
            'transport_raw': overview(b, 'Serious Injury Response, Tracking & Analysis Program'),
            'housing_cleaning': hc, 'transport_cleaning': tc, 'join_audit': audit}
    (DATA/'quality_report.json').write_text(json.dumps(info, indent=2, default=str), encoding='utf-8')
    print('SUCCESS: downloaded official NYC data, cleaned, joined, and exported CSVs')
    print(json.dumps({'housing_rows': len(housing), 'transport_rows': len(transport), **audit}, indent=2))
    return housing, transport, combined, info

if __name__ == '__main__':
    run()
