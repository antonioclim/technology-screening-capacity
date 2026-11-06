import math
import unittest

import numpy as np
import pandas as pd

from pilot_primitives import (expected_contact_probabilities,fit_logistic_risk,
                              group_contact_rates,group_contact_shares,score_contacts,training_category_risks)


class PilotPrimitiveTests(unittest.TestCase):
    def test_marginal_tie_uniform_and_quota_exact(self):
        scores=[2,1,1,0];weights=[1,1,3,5]
        p=expected_contact_probabilities(scores,weights,.3)
        np.testing.assert_allclose(p,[1,.5,.5,0])
        self.assertAlmostEqual(math.fsum(np.asarray(weights)*p),3)

    def test_lottery_preserves_prevalence(self):
        w=np.array([1,2,3]);y=np.array([1,0,1])
        p=expected_contact_probabilities([0,0,0],w,.5)
        np.testing.assert_allclose(p,[.5,.5,.5])
        m=score_contacts(y,w,p)
        self.assertAlmostEqual(m['cases_per_100_expected_contacts'],100*4/6)

    def test_boundaries_and_bad_values(self):
        np.testing.assert_array_equal(expected_contact_probabilities([2,1],[1,2],0),[0,0])
        np.testing.assert_array_equal(expected_contact_probabilities([2,1],[1,2],1),[1,1])
        for s,w,q in [([1],[0],.5),([np.nan],[1],.5),([1],[1],1.01)]:
            with self.assertRaises(ValueError):expected_contact_probabilities(s,w,q)

    def test_group_distribution(self):
        shares=group_contact_shares(['A','A','B'],[1,1,6],[1,.5,.25])
        self.assertAlmostEqual(shares['A'],50)
        self.assertAlmostEqual(shares['B'],50)
        rates=group_contact_rates(['A','A','B'],[1,1,6],[1,.5,.25])
        self.assertAlmostEqual(rates['A'],75)
        self.assertAlmostEqual(rates['B'],25)

    def test_category_risk_is_fitted_on_given_training_only(self):
        risks,base=training_category_risks(['1','1','2'],[1,0,1],[1,3,2])
        self.assertAlmostEqual(risks['1'],.25)
        self.assertEqual(risks['2'],1)
        self.assertAlmostEqual(base,.5)

    def test_logistic_encoder_and_imputer_do_not_fit_target(self):
        train=pd.DataFrame({'sector':['A','B','A','B'],'year':[2000.,np.nan,2010.,2020.]})
        target=pd.DataFrame({'sector':['UNSEEN'],'year':[2050.]})
        fit=fit_logistic_risk(train,[0,1,0,1],[1,1,1,1],['sector'],['year'])
        got=fit.predict(target)
        self.assertEqual(got.shape,(1,))
        self.assertTrue(0<=got[0]<=1)
        encoder=fit.pipeline.named_steps['features'].named_transformers_['categorical'].named_steps['encode']
        self.assertEqual(encoder.categories_[0].tolist(),['A','B'])
        imputer=fit.pipeline.named_steps['features'].named_transformers_['numeric']
        self.assertEqual(imputer.statistics_.tolist(),[2010.])
        self.assertEqual(imputer.transform(target[['year']]).shape,(1,2))

    def test_one_class_training_is_constant(self):
        fit=fit_logistic_risk(pd.DataFrame({'a':['x','y']}),[1,1],[1,1],['a'],[])
        np.testing.assert_array_equal(fit.predict(pd.DataFrame({'a':['z']})),[1.])

    def test_numeric_missing_indicator_exists_without_training_missing(self):
        train=pd.DataFrame({'sector':['A','B','A','B'],'year':[1990.,2000.,2010.,2020.]})
        target=pd.DataFrame({'sector':['A'],'year':[np.nan]})
        fit=fit_logistic_risk(train,[0,1,0,1],[1,1,1,1],['sector'],['year'])
        numeric=fit.pipeline.named_steps['features'].named_transformers_['numeric']
        matrix=numeric.transform(target[['year']])
        self.assertEqual(matrix.shape,(1,2))
        self.assertEqual(matrix[0,1],1.)

    def test_prediction_arithmetic_is_invariant_to_batch_order(self):
        train=pd.DataFrame({'sector':['A','B']*20,'year':np.arange(40)+1980.})
        test=pd.DataFrame({'sector':['A','B','A']*11,'year':[1995.,2005.,2010.]*11})
        fit=fit_logistic_risk(train,[0,1]*20,np.ones(40),['sector'],['year'])
        before=fit.pipeline.named_steps['risk'].coef_.copy()
        scores=fit.predict(test)
        np.testing.assert_array_equal(scores,fit.predict(test.iloc[::-1])[::-1])
        np.testing.assert_array_equal(before,fit.pipeline.named_steps['risk'].coef_)
        np.testing.assert_allclose(scores,fit.pipeline.predict_proba(test[list(fit.fit_columns)])[:,1],rtol=0,atol=1e-15)


if __name__=='__main__':unittest.main(verbosity=2)
