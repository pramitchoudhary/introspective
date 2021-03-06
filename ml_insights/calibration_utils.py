"""Calibration of predicted probabilities."""
from __future__ import division

import numpy as np
import sklearn
import random

try:
    from sklearn.model_selection import StratifiedKFold
except:
    from sklearn.cross_validation import StratifiedKFold


def _natural_cubic_spline_basis_expansion(xpts,knots):
    num_knots = len(knots)
    num_pts = len(xpts)
    outmat = np.zeros((num_pts,num_knots))
    outmat[:,0]= np.ones(num_pts)
    outmat[:,1] = xpts
    def make_func_H(k):
        def make_func_d(k):
            def func_d(x):
                denom = knots[-1] - knots[k-1]
                numer = np.maximum(x-knots[k-1],np.zeros(len(x)))**3 - np.maximum(x-knots[-1],np.zeros(len(x)))**3
                return numer/denom
            return func_d
        def func_H(x):
            d_fun_k = make_func_d(k)
            d_fun_Km1 = make_func_d(num_knots-1)
            return d_fun_k(x) -  d_fun_Km1(x)
        return func_H
    for i in range(1,num_knots-1):
        curr_H_fun = make_func_H(i)
        outmat[:,i+1] = curr_H_fun(xpts)
    return outmat


def prob_calibration_function(truthvec, scorevec, reg_param_vec='default',
                                knots = 'sample', method='logistic', force_prob = True, eps=1e-15, max_knots=200, random_state=942):
    """This function takes an uncalibrated set of scores and the true 0/1 values and returns a calibration function.

    This calibration function can then be applied to other scores from the same model and will return an accurate probability
    based on the data it has seen.  For best results, the calibration should be done on a separate validation set (not used
    to train the model).
    """
    from sklearn import linear_model
    from sklearn.metrics import log_loss, make_scorer

    knot_vec = np.unique(scorevec)
    if (knots == 'sample'):
        num_unique = len(knot_vec)
        if (num_unique>max_knots):
            smallest_knot, biggest_knot = knot_vec[0],knot_vec[-1]
            inter_knot_vec = knot_vec[1:-1]
            random.seed(random_state)
            random.shuffle(inter_knot_vec)
            reduced_knot_vec = inter_knot_vec[:(max_knots-2)]
            reduced_knot_vec = np.insert(reduced_knot_vec,[0,0],[smallest_knot,biggest_knot])
            knot_vec = np.sort(reduced_knot_vec)
        print("Originally there were {} knots.  Reducing to {} while preserving first and last knot.".format(num_unique, len(knot_vec)))
    X_mat = _natural_cubic_spline_basis_expansion(scorevec, knot_vec)


    if (method=='logistic'):
        if ((type(reg_param_vec)==str) and (reg_param_vec=='default')):
            reg_param_vec = 10**np.linspace(-4,10,43)
        print("Trying {} values of C between {} and {}".format(len(reg_param_vec),np.min(reg_param_vec),np.max(reg_param_vec)))
        reg = linear_model.LogisticRegressionCV(Cs=reg_param_vec, cv=5, scoring=make_scorer(log_loss,needs_proba=True, greater_is_better=False))
        reg.fit(X_mat, truthvec)
        print("Best value found C = {}".format(reg.C_))
    
    if (method=='ridge'):
        if ((type(reg_param_vec)==str) and (reg_param_vec=='default')):
            reg_param_vec = 10**np.linspace(-7,7,43)
        print("Trying {} values of alpha between {} and {}".format(len(reg_param_vec),np.min(reg_param_vec),np.max(reg_param_vec)))
        reg = linear_model.RidgeCV(alphas=reg_param_vec, cv=5, scoring=make_scorer(mean_squared_error_trunc,needs_proba=False, greater_is_better=False))
        reg.fit(X_mat, truthvec)
        print("Best value found alpha = {}".format(reg.alpha_))

    def calibrate_scores(new_scores):
        #if (not extrapolate):
        #    new_scores = np.maximum(new_scores,knot_vec[0]*np.ones(len(new_scores)))
        #    new_scores = np.minimum(new_scores,knot_vec[-1]*np.ones(len(new_scores)))
        basis_exp = _natural_cubic_spline_basis_expansion(new_scores,knot_vec)
        if (method=='logistic'):
            outvec = reg.predict_proba(basis_exp)[:,1]
        if (method=='ridge'):
            outvec = reg.predict(basis_exp)
            if force_prob:
                outvec = np.where(outvec<eps,eps,outvec)
                outvec = np.where(outvec>1-eps,1-eps,outvec)
        return outvec
    return calibrate_scores

def train_and_calibrate_cv(model, X_tr, y_tr, cv=5):
    y_pred_xval = np.zeros(len(y_tr))
    skf = cross_validation.StratifiedKFold(y_tr, n_folds=cv,shuffle=True)
    i = 0;
    for train, test in skf:
        i = i+1
        print("training fold {} of {}".format(i, cv))
        X_train_xval = np.array(X_tr)[train,:]
        X_test_xval = np.array(X_tr)[test,:]
        y_train_xval = np.array(y_tr)[train]
        # We could also copy the model first and then fit it
        model_copy = clone(model)
        model_copy.fit(X_train_xval,y_train_xval)
        y_pred_xval[test]=model.predict_proba(X_test_xval)[:,1]
    print("training full model")
    model_copy = clone(model)
    model_copy.fit(X_tr,y_tr)
    print("calibrating function")
    calib_func = prob_calibration_function(y_tr, y_pred_xval)
    return model_copy, calib_func

def mean_squared_error_trunc(y_true, y_pred,eps=1e-15): 
    y_pred = np.where(y_pred<eps,eps,y_pred)
    y_pred = np.where(y_pred>1-eps,1-eps,y_pred)
    return np.average((y_true-y_pred)**2)
