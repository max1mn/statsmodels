# -*- coding: utf-8 -*-
"""
Conditional logit

Sources: sandbox-statsmodels:runmnl.py

General References
--------------------

Greene, W. `Econometric Analysis`. Prentice Hall, 5th. edition. 2003.
Train, K. `Discrete Choice Methods with Simulation`.
    Cambridge University Press. 2003
--------------------
"""

import numpy as np
import pandas as pd
from statsmodels.base.model import (LikelihoodModel,
                                    LikelihoodModelResults, ResultMixin)
import statsmodels.api as sm
import time
from collections import OrderedDict
from scipy import stats
from statsmodels.tools.decorators import (resettable_cache,
        cache_readonly)


# TODO: public/private method
class CLogit(LikelihoodModel):
    __doc__ = """
    Conditional Logit

    Parameters
    ----------
    endog_data : array
        dummy encoding of realized choices.
    exog_data : array (nobs, k*)
        array with explanatory variables.Variables for the model are select
        by V, so, k* can be >= than k. An intercept is not included by
        default and should be added by the user.
    V: dict
        a dictionary with the names of the explanatory variables for the
        utility function for each alternative.
        Alternative specific variables (common coefficients) have to be first.
        For specific variables (various coefficients), choose an alternative and
        drop all specific variables on it.
    ncommon : int
        number of explanatory variables with common coefficients.
    ref_level : str
        Name of the key for the alternative of reference.
    name_intercept : str
        name of the column with the intercept. 'None' if an intercept is not
        included.

    Attributes
    ----------
    endog : array (nobs*J, )
        the endogenous response variable
    endog_bychoices: array (nobs,J)
        the endogenous response variable by choices
    exog_matrix: array   (nobs*J,K)
        the enxogenous response variables
    exog_bychoices: list of arrays J * (nobs,K)
        the enxogenous response variables by choices. one array of exog
        for each choice.
    nobs : float
        number of observations.
    J  : float
        The number of choices for the endogenous variable. Note that this
        is zero-indexed.
    K : float
        The actual number of parameters for the exogenous design.  Includes
        the constant if the design has one and excludes the constant of one
        choice which should be dropped for identification.
    loglikeobs
    params
    score
    jac
    hessian
    information
    predict
    residuals
    resid_misclassified
    pred_table
    summary : Summary instance
        summarize the results inside CLogitResults class.

    Notes
    -----

    Utility for choice j is given by

        $V_j = X_j * beta + Z * gamma_j$

    where X_j contains generic variables (terminology Hess) that have the same
    coefficient across choices, and Z are variables, like individual-specific
    variables that have different coefficients across variables.

    If there are choice specific constants, then they should be contained in Z.
    For identification, the constant of one choice should be dropped.
    """

    def __init__(self, endog_data, exog_data, V, ncommon, ref_level,
                         name_intercept = None, **kwds):

        self.endog_data = endog_data
        self.exog_data = exog_data

        self.V = V
        self.ncommon = ncommon

        self.ref_level = ref_level

        if name_intercept == None:
            self.exog_data['Intercept'] = 1
            self.name_intercept = 'Intercept'
        else:
            self.name_intercept = name_intercept

        self._initialize()
        super(CLogit, self).__init__(endog = endog_data,
                exog = self.exog_matrix, **kwds)

    def _initialize(self):
        """
        Preprocesses the data for Clogit
        """

        self.J = len(self.V)
        self.nobs = self.endog_data.shape[0] / self.J

        # Endog_bychoices
        self.endog_bychoices = self.endog_data.values.reshape(-1, self.J)

        # Exog_bychoices
        exog_bychoices = []
        exog_bychoices_names = []
        choice_index = np.array(self.V.keys() * self.nobs)

        for key in iter(self.V):
            (exog_bychoices.append(self.exog_data[self.V[key]]
                                    [choice_index == key]
                                    .values.reshape(self.nobs, -1)))

        for key in self.V:
            exog_bychoices_names.append(self.V[key])

        self.exog_bychoices = exog_bychoices

        # Betas
        beta_not_common = ([len(exog_bychoices_names[ii]) - self.ncommon
                            for ii in range(self.J)])
        exog_names_prueba = []

        for ii, key in enumerate(self.V):
            exog_names_prueba.append(key * beta_not_common[ii])

        zi = np.r_[[self.ncommon], self.ncommon + np.array(beta_not_common)\
                    .cumsum()]
        z = np.arange(max(zi))
        beta_ind = [np.r_[np.arange(self.ncommon), z[zi[ii]:zi[ii + 1]]]
                               for ii in range(len(zi) - 1)]  # index of betas
        self.beta_ind = beta_ind

        beta_ind_str = ([map(str, beta_ind[ii]) for ii in range(self.J)])
        beta_ind_J = ([map(str, beta_ind[ii]) for ii in range(self.J)])

        for ii in range(self.J):
            for jj, item in enumerate(beta_ind[ii]):
                if item in np.arange(self.ncommon):
                    beta_ind_J[ii][jj] = ''
                else:
                    beta_ind_J[ii][jj] = ' (' + self.V.keys()[ii] + ')'

        self.betas = OrderedDict()

        for sublist in range(self.J):
            aa = []
            for ii in range(len(exog_bychoices_names[sublist])):
                aa.append(
                beta_ind_str[sublist][ii] + ' ' +
                exog_bychoices_names[sublist][ii]
                + beta_ind_J[sublist][ii])
            self.betas[sublist] = aa

        # Exog
        pieces = []
        for ii in range(self.J):
            pieces.append(pd.DataFrame(exog_bychoices[ii], columns=self.betas[ii]))

        self.exog_matrix_all = (pd.concat(pieces, axis = 0, keys = self.V.keys(),
                                     names = ['choice', 'nobs'])
                           .fillna(value = 0).sortlevel(1).reset_index())

        self.exog_matrix = self.exog_matrix_all.iloc[:, 2:]

        self.K = len(self.exog_matrix.columns)

        self.df_model = self.K
        self.df_resid = int(self.nobs - self.K)

    def xbetas(self, params):
        '''the Utilities V_i

        '''
        res = np.empty((self.nobs, self.J))
        for ii in range(self.J):
            res[:, ii] = np.dot(self.exog_bychoices[ii],
                                      params[self.beta_ind[ii]])
        return res

    def cdf(self, item):
        """
        Conditional Logit cumulative distribution function.

        Parameters
        ----------
        X : array (nobs,K)
            the linear predictor of the model.

        Returns
        --------
        cdf : ndarray
            the cdf evaluated at `X`.

        Notes
        -----
        .. math:: \\frac{\\exp\\left(\\beta_{j}^{\\prime}x_{i}\\right){\\sum_{k=0}^{J}\\exp\\left(\\beta_{k}^{\\prime}x_{i}\\right)}
        """
        eXB = np.exp(item)
        return  eXB / eXB.sum(1)[:, None]

    def pdf(self, item):
        """
        Conditional Logit probability density function.

        """
        raise NotImplementedError


    def loglike(self, params):

        """
        Log-likelihood of the conditional logit model.

        Parameters
        ----------
        params : array
            the parameters of the conditional logit model.

        Returns
        -------
        loglike : float
            the log-likelihood function of the model evaluated at `params`.

        Notes
        ------
        .. math:: \\ln L=\\sum_{i=1}^{n}\\sum_{j=0}^{J}d_{ij}\\ln\\left(\\frac{\\exp\\left(\\beta_{j}^{\\prime}x_{i}\\right)}{\\sum_{k=0}^{J}\\exp\\left(\\beta_{k}^{\\prime}x_{i}\\right)}\\right)

        where :math:`d_{ij}=1` if individual `i` chose alternative `j` and 0
        if not.

        """

        xb = self.xbetas(params)
        loglike = (self.endog_bychoices * np.log(self.cdf(xb))).sum(1)
        return loglike.sum()

    def loglikeobs(self, params):
        """
        Log-likelihood for each observation.

        Parameters
        ----------
        params : array-like
            The parameters of the model.

        Returns
        -------
        loglike : ndarray (nobs,K)
            The log likelihood for each observation of the model evaluated
            at `params`. See Notes

        Notes
        ------
        .. math:: \\ln L_{i}=\\sum_{j=0}^{J}d_{ij}\\ln\\left(\\frac{\\exp\\left(\\beta_{j}^{\\prime}x_{i}\\right)}{\\sum_{k=0}^{J}\\exp\\left(\\beta_{k}^{\\prime}x_{i}\\right)}\\right)

        for observations :math:`i=1,...,n`

        where :math:`d_{ij}=1` if individual `i` chose alternative `j` and 0
        if not.
        """

        xb = self.xbetas(params)
        return  (self.endog_bychoices * np.log(self.cdf(xb))).sum(1)

    def score(self, params):
        """
        Score/gradient matrix for conditional logit model log-likelihood

        Parameters
        ----------
        params : array
            the parameters of the conditional logit model.

        Returns
        --------
        score : ndarray 1d (K)
            the score vector of the model evaluated at `params`.

        Notes
        -----
        It is the first derivative of the loglikelihood function of the
        conditional logit model evaluated at `params`.

        .. math:: \\frac{\\partial\\ln L}{\\partial\\beta_{j}}=\\sum_{i}\\left(d_{ij}-\\frac{\\exp\\left(\\beta_{j}^{\\prime}x_{i}\\right)}{\\sum_{k=0}^{J}\\exp\\left(\\beta_{k}^{\\prime}x_{i}\\right)}\\right)x_{i}

        for :math:`j=1,...,J`
        """

        firstterm = (self.endog_bychoices - self.cdf(self.xbetas(params)))\
                    .reshape(-1, 1)
        return np.dot(firstterm.T, self.exog).flatten()


    def jac(self, params):
        """
        Jacobian matrix for conditional logit model log-likelihood.

        Parameters
        ----------
        params : array
            the parameters of the conditional logit model.

        Returns
        --------
        jac : ndarray, (nobs, K)
            the jacobian for each observation.

        Notes
        -----
        It is the first derivative of the loglikelihood function of the
        conditional logit model for each observation evaluated at `params`.

        .. math:: \\frac{\\partial\\ln L_{i}}{\\partial\\beta_{j}}=\\left(d_{ij}-\\frac{\\exp\\left(\\beta_{j}^{\\prime}x_{i}\\right)}{\\sum_{k=0}^{J}\\exp\\left(\\beta_{k}^{\\prime}x_{i}\\right)}\\right)x_{i}

        for :math:`j=1,...,J`, for observations :math:`i=1,...,n`

        """

        firsterm = (self.endog_bychoices - self.cdf(self.xbetas(params)))\
                    .reshape(-1, 1)
        return (firsterm * self.exog)

    def hessian(self, params):
        """
        Conditional logit Hessian matrix of the log-likelihood

        Parameters
        -----------
        params : array-like
            The parameters of the model

        Returns
        -------
        hess : ndarray, (K, K)
            The Hessian
        Notes
        -----
        It is the second derivative with respect to the flattened parameters
        of the loglikelihood function of the conditional logit model
        evaluated at `params`.

        .. math:: \\frac{\\partial^{2}\\ln L}{\\partial\\beta_{j}\\partial\\beta_{l}}=-\\sum_{i=1}^{n}\\frac{\\exp\\left(\\beta_{j}^{\\prime}x_{i}\\right)}{\\sum_{k=0}^{J}\\exp\\left(\\beta_{k}^{\\prime}x_{i}\\right)}\\left[\\boldsymbol{1}\\left(j=l\\right)-\\frac{\\exp\\left(\\beta_{l}^{\\prime}x_{i}\\right)}{\\sum_{k=0}^{J}\\exp\\left(\\beta_{k}^{\\prime}x_{i}\\right)}\\right]x_{i}x_{l}^{\\prime}

        where
        :math:`\\boldsymbol{1}\\left(j=l\\right)` equals 1 if `j` = `l` and 0
        otherwise.
        """

        # TODO: analytical derivatives
        from statsmodels.tools.numdiff import approx_hess
        # need options for hess (epsilon)
        return approx_hess(params, self.loglike)

    def information(self, params):
        """
        Fisher information matrix of model

        Returns -Hessian of loglike evaluated at params.
        """
        raise NotImplementedError

    def fit(self, start_params=None, maxiter=10000, maxfun=5000,
            method="newton", full_output=1, disp=None, callback=None, **kwds):
        """
        Fits CLogit() model using maximum likelihood.
        In a model linear the log-likelihood function of the sample, is
        global concave for β parameters, which facilitates its numerical
        maximization (McFadden, 1973).
        Fixed Method = Newton, because it'll find the maximum in a few
        iterations. Newton method require a likelihood function, a gradient,
        and a Hessian. Since analytical solutions are known, we give it.
        Initial parameters estimates from the standard logit
        Returns
        -------
        Fit object for likelihood based models
        See: GenericLikelihoodModelResults

        """

        if start_params is None:

            Logit_res = sm.Logit(self.endog, self.exog_matrix).fit(disp=0)
            start_params = Logit_res.params.values

        else:
            start_params = np.asarray(start_params)

        start_time = time.time()
        model_fit = super(CLogit, self).fit(disp = disp,
                                            start_params = start_params,
                                            method=method, maxiter=maxiter,
                                            maxfun=maxfun, **kwds)

        self.params = model_fit.params
        end_time = time.time()
        self.elapsed_time = end_time - start_time

        return model_fit

    def predict(self, params, linear=False):
        """
        Predict response variable of a model given exogenous variables.

        Parameters
        ----------
        params : array-like
            Fitted parameters of the model.
        linear : bool, optional
            If True, returns the linear predictor dot(exog_bychoices,params).
            Else, returns the value of the cdf at the linear predictor.

        Returns
        -------
        array (nobs,K)
            Fitted values at exog.
        """
        if not linear:
            return self.cdf(self.xbetas(params))
        else:
            return self.xbetas(params)

    def summary(self):
        # TODO add __doc__ = CLogitResults.__doc__
        return CLogitResults(self).summary()

    @cache_readonly
    def residuals(self):
        """
        Residuals

        Returns
        -------
        array
            Residuals.

        Notes
        -----
        The residuals for the Conditional Logit model are defined as

        .. math:: y_i - p_i

        where : math:`y_i` is the endogenous variable and math:`p_i`
        predicted probabilities for each category value.
        """

        return self.endog_bychoices - self.predict(self.params)

    @cache_readonly
    def resid_misclassified(self):
        """
        Residuals indicating which observations are misclassified.

        Returns
        -------
        array (nobs,K)
            Residuals.

        Notes
        -----
        The residuals for the Conditional Logit model are defined

        .. math:: argmax(y_i) \\neq argmax(p_i)

        where :math:`argmax(y_i)` is the index of the category for the
        endogenous variable and :math:`argmax(p_i)` is the index of the
        predicted probabilities for each category. That is, the residual
        is a binary indicator that is 0 if the category with the highest
        predicted probability is the same as that of the observed variable
        and 1 otherwise.
        """
        # it's 0 or 1 - 0 for correct prediction and 1 for a missed one

        return (self.endog_bychoices.argmax(1) !=
                self.predict(self.params).argmax(1)).astype(float)

    def pred_table(self, params = None):
        """
        Returns the J x J prediction table.

        Parameters
        ----------
        params : array-like, optional
            If None, the parameters of the fitted model are used.

        Notes
        -----
        pred_table[i,j] refers to the number of times "i" was observed and
        the model predicted "j". Correct predictions are along the diagonal.
        """
        # TODO. doesn't match the results of green.
        # greene = np.array([[ 32.,   8.,   5.,  13.],
        #                   [  7.,  37.,   5.,  14.],
        #                   [  3.,   5.,  15.,   6.],
        #                   [ 16.,  13.,   6.,  25.]])
        # clogit_mod.endog_bychoices.sum(0) #OK: 58.,  63.,  30.,  59.
        # clogit_mod.predict(clogit_res.params).sum(0) #OK: 58.,  63.,  30.,  59.
        # clogit_mod.pred_table().sum(0) # 56.,  64.,  23.,  67.
        # clogit_mod.pred_table().sum(1) # OK: 58.,  63.,  30.,  59.

        if params == None:
            params = self.params

        # these are the real choices
        idx = self.endog_bychoices.argmax(1)
        # these are the predicted choices
        idy = self.predict(params).argmax(1)

        return np.histogram2d(idx, idy, bins = self.J)[0]


### Results Class ###
class CLogitResults(LikelihoodModelResults, ResultMixin):
    __doc__ = """
    Parameters
    ----------
    model : A Discrete Choice Model instance.

    Returns
    -------
    aic : float
        Akaike information criterion.  -2*(`llf` - p) where p is the number
        of regressors including the intercept.
    bic : float
        Bayesian information criterion. -2*`llf` + ln(`nobs`)*p where p is the
        number of regressors including the intercept.
    bse : array
        The standard errors of the coefficients.
    df_resid : float
        Residual degrees-of-freedom of model.
    df_model : float
        Params.
    llf : float
        Value of the loglikelihood
    llnull : float
        Value of the constant-only loglikelihood
    llr : float
        Likelihood ratio chi-squared statistic; -2*(`llnull` - `llf`)
    llrt: float
        Likelihood ratio test
    llr_pvalue : float
        The chi-squared probability of getting a log-likelihood ratio
        statistic greater than llr.  llr has a chi-squared distribution
        with degrees of freedom `df_model`.
    prsquared : float
        McFadden's pseudo-R-squared. 1 - (`llf`/`llnull`)

    """

    def __init__(self, model):

        self.model = model
        self.mlefit = model.fit()
        self.nobs_bychoice = model.nobs
        self.nobs = model.endog.shape[0]
        self.alt = model.V.keys()
        self.freq_alt = model.endog_bychoices[:, ].sum(0).tolist()
        self.perc_alt = (model.endog_bychoices[:, ].sum(0) / model.nobs)\
                        .tolist()
        self.__dict__.update(self.mlefit.__dict__)
        self._cache = resettable_cache()

    def __getstate__(self):
        try:
            #remove unpicklable callback
            self.mle_settings['callback'] = None
        except (AttributeError, KeyError):
            pass
        return self.__dict__

    @cache_readonly
    def llnull(self):
        # loglike model without predictors
        model = self.model
        V = model.V

        V_null = OrderedDict()

        for ii in range(len(V.keys())):
            if V.keys()[ii] == model.ref_level:
                V_null[V.keys()[ii]] = []
            else:
                V_null[V.keys()[ii]] = [model.name_intercept]

        clogit_null_mod = model.__class__(model.endog_data, model.exog_data,
                                          V_null, ncommon = 0,
                                          ref_level = model.ref_level,
                                          name_intercep = model.name_intercept)
        clogit_null_res = clogit_null_mod.fit(start_params = np.zeros(\
                                                len(V.keys()) - 1), disp = 0)

        return clogit_null_res.llf

    @cache_readonly
    def llr(self):
        return -2 * (self.llnull - self.llf)

    @cache_readonly
    def llrt(self):
        return 2 * (self.llf - self.llnull)

    @cache_readonly
    def llr_pvalue(self):
        return stats.chisqprob(self.llr, self.model.df_model)

    @cache_readonly
    def prsquared(self):
        """
        McFadden's Pseudo R-Squared: comparing two models on the same data, would
        be higher for the model with the greater likelihood.
        """
        return (1 - self.llf / self.llnull)

    def summary(self, title = None, alpha = .05):
        """Summarize the Clogit Results

        Parameters
        -----------
        title : string, optional
            Title for the top table. If not None, then this replaces the
            default title
        alpha : float
            significance level for the confidence intervals

        Returns
        -------
        smry : Summary instance
            this holds the summary tables and text, which can be printed or
            converted to various output formats.

        See Also
        --------
        statsmodels.iolib.summary.Summary : class to hold summary
            results

        """

        top_left = [('Dep. Variable:', None),
                    ('Model:', [self.model.__class__.__name__]),
                    ('Method:', [self.mle_settings['optimizer']]),
                    ('Date:', None),
                    ('Time:', None),
                    ('Converged:', ["%s" % self.mle_retvals['converged']]),
                    ('Iterations:', ["%s" % self.mle_retvals['iterations']]),
                    ('Elapsed time (seg.):',
                                    ["%10.4f" % self.model.elapsed_time]),
                    ('Num. alternatives:', [self.model.J])
                      ]

        top_right = [
                     ('No. Cases:', [self.nobs]),
                     ('No. Observations:', [self.nobs_bychoice]),
                     ('Df Residuals:', [self.model.df_resid]),
                     ('Df Model:', [self.model.df_model]),
                     ('Log-Likelihood:', None),
                     ('LL-Null:', ["%#8.5g" % self.llnull]),
                     ('Pseudo R-squ.:', ["%#6.4g" % self.prsquared]),
                     ('LLR p-value:', ["%#6.4g" % self.llr_pvalue]),
                     ('Likelihood ratio test:', ["%#8.5g" %self.llrt]),
                     ('AIC:', ["%#8.5g" %self.aic])

                                     ]
        if title is None:
            title = self.model.__class__.__name__ + ' ' + \
            "results"

        #boiler plate
        from statsmodels.iolib.summary import Summary, SimpleTable

        smry = Summary()
        # for top of table
        smry.add_table_2cols(self, gleft=top_left, gright=top_right,
                             title=title)

        # Frequencies of alternatives
        mydata = [self.freq_alt, self.perc_alt]
        myheaders = self.alt
        mytitle = ("")
        mystubs = ["Frequencies of alternatives: ", "Percentage:"]
        tbl = SimpleTable(mydata, myheaders, mystubs, title = mytitle,
                          data_fmts = ["%5.2f"])
        smry.tables.append(tbl)

        # for parameters
        smry.add_table_params(self, alpha=alpha, use_t=False)

        return smry


# Marginal Effects
class ClogitMargeff(CLogit):

    __doc__ = """
    Conditional Logit Marginal effects
        Derivatives of the probabilitis with respect to the explanatory variables.

    Notes
    -----
    * for alternative specific coefficients are:

        P[j] * (params_asc[j] - sum_k P[k]*params_asc[k])

        where params_asc are params for the individual-specific variables

        See _derivative_exog in class MultinomialModel

    * for generic coefficient are:

        params_gen[j] * P[j] (1 - P[j])

        where params_gen are params for the alternative-specific variables.

    """

    def __init__(self, model):

        self.model = model
        params = model.params
        self.ncommon = model.ncommon
        K = model.K
        self.J = model.J
        exog = model.exog_matrix

        self.K_asc = self.ncommon
        self.K_gen = K - self.ncommon

        self.exog_asc = exog[np.arange(self.ncommon)]
        self.exog_gen = exog[np.arange(self.ncommon, K)]

        self.params_asc = params[np.arange(self.ncommon)]
        self.params_gen = params[np.arange(self.ncommon, K)]

    def _derivative_exog_asc(self):
        return NotImplementedError

    def _derivative_exog_gen(self):
        return NotImplementedError

    def get_margeff(self):
        return NotImplementedError

if __name__ == "__main__":

    print 'Example:'

    # Load data
    from patsy import dmatrices

    url = "http://vincentarelbundock.github.io/Rdatasets/csv/Ecdat/ModeChoice.csv"
    file_ = "ModeChoice.csv"
    import os
    if not os.path.exists(file_):
        import urllib
        urllib.urlretrieve(url, "ModeChoice.csv")
    df = pd.read_csv(file_)
    df.describe()

    f = 'mode  ~ ttme+invc+invt+gc+hinc+psize'
    y, X = dmatrices(f, df, return_type='dataframe')

    # Set up model

    # Names of the variables for the utility function for each alternative
    # variables with common coefficients have to be first in each array
    V = OrderedDict((
        ('air',   ['gc', 'ttme', 'Intercept', 'hinc']),
        ('train', ['gc', 'ttme', 'Intercept']),
        ('bus',   ['gc', 'ttme', 'Intercept']),
        ('car',   ['gc', 'ttme']))
        )
    # Number of common coefficients
    ncommon = 2

    # Describe model
    clogit_mod = CLogit(y, X,  V, ncommon,
                        ref_level = 'car', name_intercept = 'Intercept')
    # Fit model
    clogit_res = clogit_mod.fit(disp=1)

    # Summarize model
    print clogit_mod.summary()

    # Marginal Effects
    # clogit_margeff = ClogitMargeff(clogit_mod)
    # print clogit_margeff._derivative_exog_asc()