"""
Test Results for discrete models
Replicate Greene (2003: Page 729) results.
Results are from R mlogit package (Cross check with Biogeme).

"""

import numpy as np
import os

cur_dir = os.path.abspath(os.path.dirname(__file__))

class Travelmodechoice():

    """
    R code

    library("mlogit", "TravelMode")
    data("TravelMode", package="AER") #load data
    names(TravelMode)<- c("individual", "mode", "choice", "ttme", "invc",
                          "invt", "gc", "hinc", "psize")
    TravelMode$hinc_air <- with(TravelMode, hinc * (mode == "air"))
    res <- mlogit(choice ~ gc + ttme + hinc_air, data = TravelMode,
                  shape = "long", alt.var = "mode", reflevel = "car")
    res_summary <- summary(res)
    str( res_summary)
    order_in_smCLogit <- c(4,5,1,6,2,3)
    params <- res_summary$CoefTable[order_in_smCLogit, 1] # model$coefficients
    bse <- res_summary$CoefTable[order_in_smCLogit, 2]
    score <- res$gradient[order_in_smCLogit]
    predict <- fitted.values(res, outcome=FALSE)
    write.table(predict[,c(2,3,4,1)], file = "clogit_predict.csv",
                        row.names = FALSE, col.names = FALSE,sep = ";")

    """
    def __init__(self):
        self.nobs = 210

    def clogit_greene(self):

        """
        R results
        """

        self.params = [-0.0155015067043374, -0.0961246217793847, 5.20743292761953,
                       0.0132870137736127, 3.86903570401292, 3.16319033000995]

        self.bse = [0.00440799307835216, 0.0104398465313473, 0.779055142508082,
                0.0102624069997369, 0.443126852001293, 0.450265930527341]

        self.hessian = np.array([
                    [-7.54742053e+04,  -1.68416889e+04,   1.92371522e+02,
                    7.78063150e+03,  -7.76604449e+02,  -2.17068300e+01],
                    [ -1.68416889e+04,  -9.14469710e+04,  -1.10997845e+03,
                    -4.34480365e+04,  -3.13751079e+02,  -1.59840260e+02],
                    [ 1.92371520e+02,  -1.10997840e+03,  -2.56136270e+01,
                    -9.93264100e+02,   7.71506200e+00,   3.88369600e+00],
                    [  7.78063148e+03,  -4.34480365e+04,  -9.93264146e+02,
                    -4.80541196e+04,   2.84426623e+02,   1.44526736e+02],
                    [ -7.76604450e+02,  -3.13751100e+02,   7.71506200e+00,
                    2.84426600e+02,  -2.87075270e+01,   6.76657400e+00],
                    [ -2.17068300e+01,  -1.59840300e+02,   3.88369600e+00,
                    1.44526700e+02,   6.76657400e+00,  -1.79784270e+01]])

        self.llf = -199.1284

        self.llnull = -283.7588

        self.aic = 410.2567

        self.llrt = 169.2608

        self.score = [-1.6002843494789e-09, -2.46809062076636e-09,
                      4.05102973735638e-11, 1.7963349419059e-09,
                      3.78327581936067e-11, -9.05671633608801e-11]

        self.predict = np.loadtxt(os.path.join(cur_dir, 'clogit_predict.csv'),
            delimiter=";")
