"""Small separate oracle examples for H4 allocation and fitting contracts."""
import unittest
import numpy as np
import pandas as pd
from verify_h4_primary import contact_probabilities,fitting_weights,independent_fit_predict

class ContractExamples(unittest.TestCase):
    def test_quota_inside_an_exact_tie(self):
        weights=np.array([2.,3.,5.]);scores=np.array([.2,.2,.8])
        chances=contact_probabilities(scores,weights,.75)
        np.testing.assert_array_equal(chances,[.5,.5,1.])
        self.assertAlmostEqual(float(weights@chances),7.5)
        np.testing.assert_array_equal(contact_probabilities(scores[::-1],weights[::-1],.75)[::-1],chances)

    def test_country_and_india_source_balance_at_sum_N(self):
        frame=pd.DataFrame({'country':['India','India','India_Wave2_New','India_Wave2_New','Other'],
                            'reporting_country':['India','India','India','India','Other'],
                            'base_wt':[1.,3.,2.,2.,5.]})
        weights,totals=fitting_weights(frame)
        self.assertAlmostEqual(float(weights.sum()),5.)
        self.assertAlmostEqual(totals['India'],2.5);self.assertAlmostEqual(totals['Other'],2.5)
        self.assertAlmostEqual(float(weights[:2].sum()),1.25)
        self.assertAlmostEqual(float(weights[2:4].sum()),1.25)
        self.assertAlmostEqual(weights[1]/weights[0],3.)

    def test_target_outcome_and_target_median_never_enter_fit(self):
        train=pd.DataFrame({'country':['A','A','B','B'],'reporting_country':['A','A','B','B'],
                            'base_wt':[1.,1.,1.,1.],'event':[0,1,0,1],
                            'a5a':[1.,1.,2.,2.],'s4':[0.,1.,0.,1.],'a3b':[0.,0.,20.,20.],
                            'a6':[1900.,2000.,np.nan,np.nan],'MOST5':[1,2,1,3],'MAX5':[2,3,2,3]})
        target=pd.DataFrame({'country':['C','C'],'reporting_country':['C','C'],'base_wt':[1.,1.],
                             'event':[0,1],'a5a':[102.,3.],'s4':[1.,0.],'a3b':[0.,np.nan],
                             'a6':[2023.,2023.],'MOST5':[5,4],'MAX5':[5,5]})
        pred,receipt=independent_fit_predict(train,target,'B_MOST5')
        changed=target.copy();changed['event']=~changed.event.astype(bool)
        second,other=independent_fit_predict(train,changed,'B_MOST5')
        self.assertEqual(receipt['start_year_median'],1950.)
        self.assertEqual(receipt,other);np.testing.assert_array_equal(pred,second)
        self.assertTrue(np.isfinite(pred).all())

    def test_one_class_and_full_or_zero_quota(self):
        train=pd.DataFrame({'country':['A','B'],'reporting_country':['A','B'],'base_wt':[1.,2.],
                            'event':[0,0],'a5a':[1.,2.],'s4':[0.,1.],'a3b':[0.,10.],
                            'a6':[np.nan,np.nan],'MOST5':[1,2],'MAX5':[2,3]})
        pred,receipt=independent_fit_predict(train,train,'B')
        np.testing.assert_array_equal(pred,[0.,0.]);self.assertEqual(receipt['start_year_median'],0.)
        np.testing.assert_array_equal(contact_probabilities([1.,1.],[2.,3.],0.),[0.,0.])
        np.testing.assert_array_equal(contact_probabilities([1.,1.],[2.,3.],1.),[1.,1.])

if __name__=='__main__':unittest.main(verbosity=2)
