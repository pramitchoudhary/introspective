"""Calibration of predicted probabilities."""
import numpy as np
import sklearn
from sklearn.base import BaseEstimator, ClassifierMixin, clone

try:
    from sklearn.model_selection import StratifiedKFold
except:
    from sklearn.cross_validation import StratifiedKFold

from .calibration_utils import prob_calibration_function


class SplineCalibratedClassifierCV(BaseEstimator, ClassifierMixin):
    """Probability calibration using cubic splines.

    With this class, the base_estimator is fit on each of the cross-validation
    training set folds in order to generate scores on the (cross-validated)
    test set folds.  The test set scores are accumulated into a final vector
    (the size of the full set) which is used to calibrate the answers.
    The model is then fit on the full data set.  The predict, and predict_proba
    methods are then updated to use the combination of the predictions from the 
    full model and the calibration function computed as above.

    Parameters
    ----------
    base_estimator : instance BaseEstimator
        The classifier whose output decision function needs to be calibrated
        to offer more accurate predict_proba outputs. If cv=prefit, the
        classifier must have been fit already on data.

    method : 'logistic' or 'ridge'
        The default is 'logistic', which is best if you plan to use log-loss as your
        performance metric.  This method is relatively robust and will typically do
        well on brier score as well.  The 'ridge' method calibrates using an L2 loss,
        and therefore should do better for brier score, but may do considerably worse
        on log-loss.

    cv : integer, cross-validation generator, iterable or "prefit", optional
        Determines the cross-validation splitting strategy.
        Possible inputs for cv are:

        - None, to use the default 5-fold cross-validation,
        - integer, to specify the number of folds.
        - 'prefit', if you wish to use the data only for calibration

        For integer/None inputs, if ``y`` is binary or multiclass,
        :class:`sklearn.model_selection.StratifiedKFold` is used. If ``y`` is
        neither binary nor multiclass, :class:`sklearn.model_selection.KFold`
        is used.

        Refer :ref:`User Guide <cross_validation>` for the various
        cross-validation strategies that can be used here.

        If "prefit" is passed, it is assumed that base_estimator has been
        fitted already and all data is used for calibration.

    Attributes
    ----------
    classes_ : array, shape (n_classes)
        The class labels.

    calibrated_classifiers_: list (len() equal to cv or 1 if cv == "prefit")
        The list of calibrated classifiers, one for each crossvalidation fold,
        which has been fitted on all but the validation fold and calibrated
        on the validation fold.

    References
    ----------
   """
    def __init__(self, base_estimator=None, method='logistic', cv=5, **calib_kwargs):
        self.base_estimator = base_estimator
        self.uncalibrated_classifier = None
        self.calib_func = None
        self.method = method
        self.cv = cv
        self.calib_kwargs = calib_kwargs

    def fit(self, X, y):
        """Fit the calibrated model

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            Training data.

        y : array-like, shape (n_samples,)
            Target values.

        Returns
        -------
        self : object
            Returns an instance of self.
        """
        if ((type(self.cv)==str) and (self.cv=='prefit')):
            self.uncalibrated_classifier = self.base_estimator
            y_pred = self.uncalibrated_classifier.predict_proba(X)[:,1]

        else:
            y_pred = np.zeros(len(y))
            if sklearn.__version__ < '0.18':
                skf = StratifiedKFold(y, n_folds=self.cv,shuffle=True)
            else:
                skf = StratifiedKFold(n_splits=self.cv, shuffle=True).split(X, y)
            for idx, (train_idx, test_idx) in enumerate(skf):
                print("training fold {} of {}".format(idx+1, self.cv))
                X_train = np.array(X)[train_idx,:]
                X_test = np.array(X)[test_idx,:]
                y_train = np.array(y)[train_idx]
                # We could also copy the model first and then fit it
                this_estimator = clone(self.base_estimator)
                this_estimator.fit(X_train,y_train)
                y_pred[test_idx] = this_estimator.predict_proba(X_test)[:,1]
            
            print("Training Full Model")
            self.uncalibrated_classifier = clone(self.base_estimator)
            self.uncalibrated_classifier.fit(X, y)

        # calibrating function
        print("Determining Calibration Function")
        if self.method=='logistic':
            self.calib_func = prob_calibration_function(y, y_pred, **self.calib_kwargs)
        if self.method=='ridge':
            self.calib_func = prob_calibration_function(y, y_pred, method='ridge', **self.calib_kwargs)
        # training full model

        return self

    def predict_proba(self, X):
        """Posterior probabilities of classification

        This function returns posterior probabilities of classification
        according to each class on an array of test vectors X.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The samples.

        Returns
        -------
        C : array, shape (n_samples, n_classes)
            The predicted probas.
        """
        # check_is_fitted(self, ["classes_", "calibrated_classifier"])
        col_1 = self.calib_func(self.uncalibrated_classifier.predict_proba(X)[:,1])
        col_0 = 1-col_1
        return np.vstack((col_0,col_1)).T


    def predict(self, X):
        """Predict the target of new samples. Can be different from the
        prediction of the uncalibrated classifier.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The samples.

        Returns
        -------
        C : array, shape (n_samples,)
            The predicted class.
        """
        # check_is_fitted(self, ["classes_", "calibrated_classifier"])
        return self.uncalibrated_classifier.classes_[np.argmax(self.predict_proba(X), axis=1)]

    def classes_(self):
        return self.uncalibrated_classifier.classes_
