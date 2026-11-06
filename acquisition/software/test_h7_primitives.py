"""Meaningful synthetic checks of H7 allocation and inversion contracts."""
import math
import unittest
import numpy as np

from acquisition_primitives import (
    allocate, band_mask, capacity_equivalent, selective_allocate,
    sector_fixed_allocate,
)


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.b = np.array([.9, .8, .8, .5, .2])
        self.rich = np.array([.4, .8, .3, .9, .1])
        self.w = np.array([1., 2., 3., 2., 2.])

    def test_exact_tie_and_weighted_quota(self):
        p = allocate(self.b, self.w, .4)
        np.testing.assert_array_equal(p, [1., .6, .6, 0., 0.])
        self.assertEqual(math.fsum(self.w*p), 4.)

    def test_allocate_endpoints_and_invalid_inputs(self):
        np.testing.assert_array_equal(allocate(self.b,self.w,0.),np.zeros(5))
        np.testing.assert_array_equal(allocate(self.b,self.w,1.),np.ones(5))
        for q in [-.1,1.1,float('nan')]:
            with self.assertRaises(ValueError): allocate(self.b,self.w,q)
        with self.assertRaises(ValueError): allocate(self.b,[1,2,3,0,2],.5)

    def test_band_tie_expansion_and_strict_boundaries(self):
        np.testing.assert_array_equal(band_mask(self.b,self.w,.5,.1),[False,True,True,False,False])
        # At q=.1 and width .2 the upper endpoint=.28 enters the .8 tie.
        np.testing.assert_array_equal(band_mask(self.b,self.w,.1,.2),[True,True,True,False,False])
        # Boundary exactly .1 does not include the score block ending there.
        b=np.array([4.,3.,2.,1.]);w=np.array([1.,1.,1.,1.])
        np.testing.assert_array_equal(band_mask(b,w,.5,.5),[False,True,True,False])

    def test_band_zero_full_offcentre_and_nested(self):
        for q in [.2,.5,.75]:
            np.testing.assert_array_equal(band_mask(self.b,self.w,q,0.),np.zeros(5,dtype=bool))
            np.testing.assert_array_equal(band_mask(self.b,self.w,q,1.),np.ones(5,dtype=bool))
            previous=np.zeros(5,dtype=bool)
            for r in [.1,.25,.5,1.]:
                current=band_mask(self.b,self.w,q,r)
                self.assertTrue(np.all(current|~previous));previous=current

    def test_selective_zero_full_and_ignored_unqueried_rich(self):
        no=np.zeros(5,dtype=bool)
        np.testing.assert_array_equal(selective_allocate(self.b,np.full(5,np.nan),self.w,.5,no),allocate(self.b,self.w,.5))
        np.testing.assert_array_equal(selective_allocate(self.b,self.rich,self.w,.5,~no),allocate(self.rich,self.w,.5))
        mask=band_mask(self.b,self.w,.5,.1)
        rich=self.rich.copy();rich[~mask]=np.nan
        p=selective_allocate(self.b,rich,self.w,.5,mask)
        base=allocate(self.b,self.w,.5)
        np.testing.assert_array_equal(p[~mask],base[~mask])
        self.assertAlmostEqual(math.fsum(self.w*p),5.,places=13)

    def test_noncontiguous_query_pool_and_query_tie(self):
        mask=np.array([True,False,False,True,True])
        p=selective_allocate(self.b,self.rich,self.w,.5,mask)
        base=allocate(self.b,self.w,.5)
        self.assertAlmostEqual(math.fsum(self.w[mask]*p[mask]),math.fsum(self.w[mask]*base[mask]),places=13)
        rich=np.ones(5)
        tied=selective_allocate(self.b,rich,self.w,.5,mask)
        self.assertTrue(np.all(tied[mask]==tied[mask][0]))

    def test_permutation_invariance(self):
        order=np.array([4,2,0,3,1]);back=np.argsort(order)
        for q in [.2,.35,.5,.75]:
            np.testing.assert_array_equal(allocate(self.b,self.w,q),allocate(self.b[order],self.w[order],q)[back])
            mask=band_mask(self.b,self.w,q,.25)
            np.testing.assert_array_equal(mask,band_mask(self.b[order],self.w[order],q,.25)[back])
            np.testing.assert_array_equal(selective_allocate(self.b,self.rich,self.w,q,mask),selective_allocate(self.b[order],self.rich[order],self.w[order],q,mask[order])[back])

    def test_sector_contact_mass_preserved(self):
        sector=np.array(['A','B','A','B','A'])
        base=allocate(self.b,self.w,.5)
        p=sector_fixed_allocate(self.b,self.rich,self.w,.5,sector)
        for group in ['A','B']:
            mask=sector==group
            self.assertAlmostEqual(math.fsum(self.w[mask]*base[mask]),math.fsum(self.w[mask]*p[mask]),places=13)

    def test_capacity_interpolation_inside_tie(self):
        y=np.array([0,1,0,1,0])
        # First block weight1 has no case; tied block weight5/case2.
        self.assertAlmostEqual(capacity_equivalent(self.b,self.w,y,1.),.35)
        q=capacity_equivalent(self.b,self.w,y,3.)
        self.assertAlmostEqual(q,.7)
        self.assertAlmostEqual(math.fsum(self.w*y*allocate(self.b,self.w,q)),3.)

    def test_capacity_plateau_and_anchored_zero(self):
        b=np.array([4.,3.,2.,1.]);w=np.ones(4);y=np.array([1,0,0,1])
        self.assertEqual(capacity_equivalent(b,w,y,1.),.25)
        q=.5;cases=math.fsum(w*y*allocate(b,w,q))
        raw=capacity_equivalent(b,w,y,cases)-q
        anchored=capacity_equivalent(b,w,y,cases)-capacity_equivalent(b,w,y,cases)
        self.assertEqual(raw,-.25);self.assertEqual(anchored,0.)
        self.assertEqual(capacity_equivalent(b,w,np.zeros(4),0.),0.)

    def test_capacity_negative_contrast_retained(self):
        b=np.array([4.,3.,2.,1.]);w=np.ones(4);y=np.array([1,1,0,0])
        q=.5;rich_cases=1.
        contrast=capacity_equivalent(b,w,y,rich_cases)-capacity_equivalent(b,w,y,math.fsum(w*y*allocate(b,w,q)))
        self.assertEqual(contrast,-.25)

    def test_capacity_regrouping_plateau_10000_heterogeneous_weights(self):
        rng=np.random.default_rng(422)
        b=np.array([10,10,9,9,8,8,7,7,6,6,5,5],dtype=float)
        y=np.array([1,1,1,1,0,0,0,0,1,1,0,1],dtype=float)
        for _ in range(10000):
            w=10.**rng.uniform(-8,8,len(b))
            goal=math.fsum(w[:4])
            expected=goal/math.fsum(w)
            observed=capacity_equivalent(b,w,y,goal)
            # The fixed tolerance may identify an earlier boundary only when
            # its missing case mass is below the documented numerical margin.
            tolerance=64.*np.finfo(float).eps*max(1.,math.fsum(w*y))
            earlier_cases=math.fsum(w[:2])
            if goal-earlier_cases > tolerance:
                self.assertAlmostEqual(observed,expected,places=13)
            else:
                self.assertLessEqual(observed,expected+1e-13)
                observed_cases=math.fsum(w*y*allocate(b,w,observed))
                self.assertLessEqual(abs(observed_cases-goal),tolerance*1.01)

    def test_capacity_independent_plateau_regression(self):
        b=np.array([10,10,9,9,8,8,7,7,6,6,5,5],dtype=float)
        y=np.array([1,1,1,1,0,0,0,0,1,1,0,1],dtype=float)
        w=np.array([476.6260850778804,2.7172451436227147,.008819480272656104,
                    91658.99890677819,.010286745620223943,43985.58843666264,
                    .013308460060405666,21618.40518595098,.00793143862335484,
                    19.1052027208085,.0005319817371972565,2.958783251098768])
        goal=math.fsum(w[:4])
        self.assertAlmostEqual(capacity_equivalent(b,w,y,goal),.5840248324262814,places=15)

    def test_capacity_invalid_and_permutation(self):
        y=np.array([0,1,0,1,0]);order=np.array([4,2,0,3,1])
        for goal in [0.,1.,2.,3.,4.]:
            self.assertEqual(capacity_equivalent(self.b,self.w,y,goal),capacity_equivalent(self.b[order],self.w[order],y[order],goal))
        with self.assertRaises(ValueError): capacity_equivalent(self.b,self.w,y,5.)
        with self.assertRaises(ValueError): capacity_equivalent(self.b,self.w,[0,1,2,1,0],1.)


if __name__ == '__main__':
    unittest.main()
