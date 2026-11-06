"""Synthetic contracts for H5. These do not establish empirical validity."""
import math
import unittest
import numpy as np
import pandas as pd
from pilot_primitives import expected_contact_probabilities,FixedNumericEncoder
from run_h5_followup import fit,balanced_fit_weights
from pilot_data import onehot_state,adopted_max_state

def fixture(n=240):
    i=np.arange(n)
    return pd.DataFrame({'firmid':i+1,'country':np.where(i<n//2,'A','B'),'reporting_country':np.where(i<n//2,'A','B'),
       'base_wt':1+(i%3)/3,'event':i%5==0,'a5a':1+i%2,'s4':i%2,'a3b':np.where(i%3==0,20.,0.),
       'a6':np.where(i%7==0,np.nan,1990+i%20),'s7':1+i%100,'plan_MOST':1+i%5,'admin_MOST':1+(i//2)%5})

class H5Tests(unittest.TestCase):
    def test_fractional_tie_and_permutation(self):
        s=np.array([0.,0.,1.]);w=np.array([1.,3.,2.]);p=expected_contact_probabilities(s,w,.5)
        np.testing.assert_array_equal(p,[.25,.25,1.]);np.testing.assert_array_equal(p,expected_contact_probabilities(s[::-1],w[::-1],.5)[::-1])
    def test_zero_full_quotas(self):
        for q in [0.,1.]:np.testing.assert_array_equal(expected_contact_probabilities([1,1],[2,3],q),[q,q])
    def test_numeric_train_only_and_missing_indicator(self):
        e=FixedNumericEncoder().fit([[1.],[3.],[np.nan]])
        self.assertEqual(e.statistics_[0],2.);np.testing.assert_array_equal(e.transform([[np.nan]])[:,1],[1.])
        e.transform([[1e99]]);self.assertEqual(e.statistics_[0],2.)
        e2=FixedNumericEncoder().fit([[1.],[3.]])
        self.assertEqual(e2.transform([[2.]]).shape,(1,2))
    def test_onehot_and_adoption_validation(self):
        d=pd.DataFrame({'m1':[1,0,1,0],'m2':[0,0,1,1],'a1':[1,0,1,0],'a2':[1,0,0,1]})
        s,v=onehot_state(d,'m',2);np.testing.assert_array_equal(v,[True,False,False,True])
        m,v=adopted_max_state(d,'a',2);np.testing.assert_array_equal(v,[True,False,True,True]);self.assertEqual(m.iloc[0],2.)
    def test_country_and_source_balance(self):
        d=fixture();d.loc[:59,'country']='A1';d.loc[60:119,'country']='A2'
        w,m=balanced_fit_weights(d)
        self.assertAlmostEqual(math.fsum(w),len(d));self.assertAlmostEqual(m['A'],m['B'])
        self.assertAlmostEqual(w[:60].sum(),w[60:120].sum())
    def test_model_target_perturbation_and_batch_invariance(self):
        train=fixture();test=fixture(120)
        for model in ['logistic','tree']:
            for spec in ['B','B_plan_MOST5','B_admin_MOST5','B_both_MOST5']:
                s,p=fit(train,test,model+'_'+spec)
                t=test.copy();t['event']=~t.event
                s2,p2=fit(train,t,model+'_'+spec)
                np.testing.assert_array_equal(s,s2);self.assertEqual(p,p2)
                extended=pd.concat([test,test.iloc[:10].assign(a6=1e6)],ignore_index=True)
                s3,p3=fit(train,extended,model+'_'+spec)
                np.testing.assert_array_equal(s,s3[:len(test)]);self.assertEqual(p,p3)
    def test_one_class_no_target_class_inference(self):
        train=fixture().assign(event=False);test=fixture(120)
        for model in ['logistic','tree']:
            s,p=fit(train,test,model+'_B_plan_MOST5');np.testing.assert_array_equal(s,np.zeros(len(test)));self.assertEqual(p['one_class_constant'],0.)

if __name__=='__main__':unittest.main(verbosity=2)
