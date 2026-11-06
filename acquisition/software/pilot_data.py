"""Authenticated input and coding helpers; no empirical evaluation at import."""
from __future__ import annotations

from hashlib import sha256
import importlib.util
import io
from pathlib import Path
import sys
from zipfile import ZipFile

import numpy as np
import pandas as pd

RAW_SHA='6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e'
MEMBER_SHA='f61a2c6e09f4763818ae1d4db8b330e97bffd8bb0824c2d833b79d728152bd17'
FROZEN_SHA='0ac2f1d60dbafcdc5edd763e682759732f326cceb66639cdf50647d34987a402'
H1_SHA='f3d6536f0de1ccd09cb18f3e73a4a7071eeada16a3423cbfca0572285ae6fa72'
PRIMARY_FP='59d49ff980b98de612b32d721ed35dc80a92fb3175be2e1ddfcf8d36168c6f76'


def digest(path):return sha256(Path(path).read_bytes()).hexdigest()


def load_frozen(path):
    if digest(path)!=FROZEN_SHA:raise ValueError('Frozen E4 software hash differs')
    spec=importlib.util.spec_from_file_location('papere_h4_frozen_e4',path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module


def load_raw(path):
    blob=Path(path).read_bytes()
    if sha256(blob).hexdigest()!=RAW_SHA:raise ValueError('Original FAT ZIP differs')
    with ZipFile(io.BytesIO(blob)) as z:
        if z.testzip() is not None:raise ValueError('FAT ZIP CRC failed')
        member=z.read('fat0_raw_data_qje.csv')
    if sha256(member).hexdigest()!=MEMBER_SHA:raise ValueError('Pooled member differs')
    frame=pd.read_csv(io.BytesIO(member),low_memory=False)
    if frame.shape!=(21055,723) or frame.firmid.duplicated().any():
        raise ValueError('Unexpected raw shape or duplicate establishment identifiers')
    return frame


def onehot_state(frame,prefix,levels=5):
    fields=[prefix+str(i) for i in range(1,levels+1)]
    values=frame[fields]
    valid=values.isin([0,1]).all(axis=1)&values.sum(axis=1).eq(1)
    state=pd.Series(np.nan,index=frame.index,dtype=float)
    state.loc[valid]=np.argmax(values.loc[valid].to_numpy(),axis=1)+1
    return state,valid


def adopted_max_state(frame,prefix,levels=5):
    fields=[prefix+str(i) for i in range(1,levels+1)]
    values=frame[fields]
    valid=values.isin([0,1]).all(axis=1)&values.sum(axis=1).ge(1)
    state=pd.Series(np.nan,index=frame.index,dtype=float)
    state.loc[valid]=np.max(values.loc[valid].to_numpy()*np.arange(1,levels+1),axis=1)
    return state,valid


def add_event_labels(frame,frozen,quantile=.2):
    """Apply the frozen inclusive source-relative event to this supplied base."""
    out=frame.sort_values(['country','firmid'],kind='stable').reset_index(drop=True).copy()
    out['event']=False
    out['eval_weight']=out.base_wt.astype(float)/out.groupby('country').base_wt.transform('mean')
    outcome=np.log(out.e6a.astype(float)/out.s7.astype(float))
    for source,indices in out.groupby('country',sort=True).groups.items():
        threshold=frozen.weighted_quantile_threshold(outcome.loc[indices].to_numpy(),
                                                     out.loc[indices,'eval_weight'].to_numpy(),quantile)
        out.loc[indices,'event']=outcome.loc[indices].le(threshold)
    return out


def encode_routine(frame):
    out=pd.DataFrame(index=frame.index)
    sector=pd.to_numeric(frame.a5a,errors='coerce')
    allowed={1,2,3,4,5,6,7,8,9,10,11,101,102}
    out['sector']=sector.map(lambda x:str(int(x)) if pd.notna(x) and x in allowed else 'UNKNOWN')
    multi=pd.to_numeric(frame.s4,errors='coerce')
    out['multi_establishment']=multi.map(lambda x:str(int(x)) if pd.notna(x) and x in {0,1} else 'UNKNOWN')
    owner=pd.to_numeric(frame.a3b,errors='coerce')
    out['foreign_owner']=np.select([owner.eq(0),owner.gt(0)&owner.le(100)],['DOMESTIC','ANY_FOREIGN'],default='UNKNOWN')
    year=pd.to_numeric(frame.a6,errors='coerce')
    out['start_year']=year.where(year.between(1800,2023))
    employees=pd.to_numeric(frame.s7,errors='coerce')
    out['log_employment']=np.log(employees.where(employees.gt(0)))
    return out


def employment_groups(frame,edges=(20,100,250)):
    values=pd.to_numeric(frame.s7,errors='coerce').to_numpy()
    out=np.full(len(values),'UNKNOWN',dtype=object)
    valid=np.isfinite(values)&(values>0)
    labels=[f'LT{edges[0]}',*[f'{a}_{b-1}' for a,b in zip(edges[:-1],edges[1:])],f'GE{edges[-1]}']
    bins=np.searchsorted(edges,values[valid],side='right')
    out[valid]=np.asarray(labels,dtype=object)[bins]
    return out
