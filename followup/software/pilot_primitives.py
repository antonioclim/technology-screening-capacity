"""Small H4 computational primitives, with no new mathematical results.

This module does not load empirical data or choose a policy. The separately
locked protocol must define cohorts, features, fitting weights and comparisons.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


class FixedNumericEncoder(TransformerMixin,BaseEstimator):
    """Train medians/scaling, plus an unscaled missing flag for every variable."""
    def fit(self,X,y=None):
        values=np.asarray(X,dtype=float)
        missing=~np.isfinite(values)
        self.statistics_=np.array([float(np.median(values[~missing[:,i],i])) if (~missing[:,i]).any() else 0.
                                   for i in range(values.shape[1])])
        imputed=np.where(missing,self.statistics_,values)
        self.scaler_=StandardScaler().fit(imputed)
        self.n_features_in_=values.shape[1]
        return self

    def transform(self,X):
        values=np.asarray(X,dtype=float)
        missing=~np.isfinite(values)
        imputed=np.where(missing,self.statistics_,values)
        return np.column_stack([self.scaler_.transform(imputed),missing.astype(float)])

    def get_feature_names_out(self,input_features=None):
        names=list(input_features) if input_features is not None else [f'x{i}' for i in range(self.n_features_in_)]
        return np.asarray([*names,*[x+'_missing' for x in names]],dtype=object)


def expected_contact_probabilities(scores, weights, quota):
    """Highest scores first; one common chance throughout a marginal tie."""
    scores=np.asarray(scores,dtype=float)
    weights=np.asarray(weights,dtype=float)
    if scores.ndim!=1 or weights.shape!=scores.shape or not len(scores):
        raise ValueError('Scores and weights require nonempty matching vectors')
    if not np.isfinite(scores).all() or not np.isfinite(weights).all() or np.any(weights<=0):
        raise ValueError('Finite scores and strictly positive finite weights required')
    if not math.isfinite(quota) or not 0<=quota<=1:
        raise ValueError('Quota must be in [0,1]')
    order=np.argsort(-scores,kind='stable')
    ordered=scores[order]
    starts=np.r_[0,np.flatnonzero(ordered[1:]!=ordered[:-1])+1]
    stops=np.r_[starts[1:],len(scores)]
    result=np.zeros(len(scores),dtype=float)
    remaining=quota*math.fsum(weights)
    for start,stop in zip(starts,stops):
        indices=order[start:stop]
        mass=math.fsum(weights[indices])
        probability=min(1.,max(0.,remaining/mass))
        result[indices]=probability
        remaining-=probability*mass
    observed=math.fsum(weights*result)
    target=quota*math.fsum(weights)
    if abs(observed-target)>1e-8:
        raise ArithmeticError('Expected quota accounting failed')
    return result


def score_contacts(events, weights, probabilities):
    events=np.asarray(events,dtype=bool)
    weights=np.asarray(weights,dtype=float)
    probabilities=np.asarray(probabilities,dtype=float)
    contacts=math.fsum(weights*probabilities)
    cases=math.fsum(weights*probabilities*events)
    event_mass=math.fsum(weights*events)
    return {'expected_weighted_contacts':contacts,'expected_weighted_cases':cases,
            'eligible_weighted_mass':math.fsum(weights),
            'event_prevalence_percent':100*event_mass/math.fsum(weights),
            'cases_per_100_expected_contacts':100*cases/contacts if contacts else None,
            'event_recall_percent':100*cases/event_mass if event_mass else None}


def group_contact_shares(groups, weights, probabilities):
    groups=np.asarray(groups,dtype=str)
    weighted=np.asarray(weights,dtype=float)*np.asarray(probabilities,dtype=float)
    total=math.fsum(weighted)
    return {g:100*math.fsum(weighted[groups==g])/total for g in sorted(set(groups))}


def group_contact_rates(groups, weights, probabilities):
    """Expected weighted contacts as a percentage of each group's own mass."""
    groups=np.asarray(groups,dtype=str)
    weights=np.asarray(weights,dtype=float)
    weighted=weights*np.asarray(probabilities,dtype=float)
    return {g:100*math.fsum(weighted[groups==g])/math.fsum(weights[groups==g])
            for g in sorted(set(groups))}


def training_category_risks(categories, events, weights, *, smoothing_mass=0.):
    """Training-only empirical risks, optionally shrunk to its overall event rate."""
    categories=np.asarray(categories,dtype=str)
    events=np.asarray(events,dtype=float)
    weights=np.asarray(weights,dtype=float)
    baseline=math.fsum(weights*events)/math.fsum(weights)
    result={}
    for group in sorted(set(categories)):
        selected=categories==group
        mass=math.fsum(weights[selected])
        cases=math.fsum(weights[selected]*events[selected])
        result[group]=(cases+smoothing_mass*baseline)/(mass+smoothing_mass)
    return result,baseline


@dataclass
class FittedBinaryRisk:
    pipeline: Pipeline | None
    constant: float | None
    train_n: int
    fit_columns: tuple[str,...]
    convergence_warnings: tuple[str,...]

    def predict(self,frame):
        if self.pipeline is None:
            return np.full(len(frame),self.constant,dtype=float)
        # Fixed per-row arithmetic prevents batch-dependent BLAS ULP differences
        # from splitting a mathematically identical score tie after row reordering.
        matrix=self.pipeline.named_steps['features'].transform(frame[list(self.fit_columns)])
        fitted=self.pipeline.named_steps['risk']
        coefficients=fitted.coef_[0]
        intercept=float(fitted.intercept_[0])
        logits=[math.fsum(row*coefficients)+intercept for row in matrix]
        def sigmoid(value):
            if value>=0:return 1./(1.+math.exp(-value))
            exp_value=math.exp(value)
            return exp_value/(1.+exp_value)
        return np.fromiter((sigmoid(value) for value in logits),dtype=float,count=len(logits))


def fit_logistic_risk(frame,events,weights,categorical,numeric,*,C=1.,max_iter=2000,tol=1e-8,categorical_domains=None):
    """Fit all imputation, coding and scaling on the provided training rows only."""
    categorical=list(categorical);numeric=list(numeric)
    columns=tuple([*categorical,*numeric])
    y=np.asarray(events,dtype=int);w=np.asarray(weights,dtype=float)
    if len(frame)!=len(y) or len(y)!=len(w) or not len(y):
        raise ValueError('Training inputs have incompatible lengths')
    if not set(y).issubset({0,1}) or not np.isfinite(w).all() or np.any(w<=0):
        raise ValueError('Binary events and positive finite fit weights required')
    if len(np.unique(y))==1:
        return FittedBinaryRisk(None,float(y[0]),len(y),columns,())
    blocks=[]
    if categorical:
        categories=[categorical_domains[x] for x in categorical] if categorical_domains else 'auto'
        cat=Pipeline([('impute',SimpleImputer(strategy='constant',fill_value='UNKNOWN',keep_empty_features=True)),
                      ('encode',OneHotEncoder(categories=categories,handle_unknown='ignore',sparse_output=False,dtype=float))])
        blocks.append(('categorical',cat,categorical))
    if numeric:
        num=FixedNumericEncoder()
        blocks.append(('numeric',num,numeric))
    if not blocks:raise ValueError('At least one feature required')
    pipeline=Pipeline([('features',ColumnTransformer(blocks,remainder='drop')),
                       ('risk',LogisticRegression(penalty='l2',C=C,solver='lbfgs',max_iter=max_iter,tol=tol))])
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always',ConvergenceWarning)
        pipeline.fit(frame[list(columns)],y,risk__sample_weight=w)
    problems=tuple(str(x.message) for x in captured if issubclass(x.category,ConvergenceWarning))
    if problems:raise RuntimeError('Prespecified logistic model did not converge: '+'; '.join(problems))
    return FittedBinaryRisk(pipeline,None,len(y),columns,problems)
