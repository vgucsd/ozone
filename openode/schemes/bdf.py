from __future__ import division

import numpy as np
from openode.schemes.scheme import GLMScheme


class BDF2(GLMScheme):
    def __init__(self):
        A = np.array([
            [2./3.],
        ])
        U = np.array([
            [4./3., -1./3.],
        ])
        B = np.array([
            [2./3.],
            [0.],
        ])
        V = np.array([
            [4./3., -1./3.],
            [1., 0.],
        ])
        starting_scheme_name = 'RK4'
        starting_coeffs = np.array([
            [1., 0.],
            [0., 1.],
        ]).reshape((2, 2, 1))
        starting_time_steps = 1

        super(BDF2, self).__init__(A=A, B=B, U=U, V=V, abscissa=np.ones(1),
            starting_method=(starting_scheme_name, starting_coeffs, starting_time_steps))


class BDF4(GLMScheme):
    def __init__(self):
        A = np.array([
            [12./25.],
        ])
        U = np.array([
            [48./25., -36./25., 16./25., -3./25.],
        ])
        B = np.array([
            [12./25.],
            [0.],
            [0.],
            [0.],
        ])
        V = np.array([
            [48./25., -36./25., 16./25., -3./25.],
            [1., 0., 0., 0.],
            [0., 1., 0., 0.],
            [0., 0., 1., 0.],
        ])
        starting_scheme_name = 'RK4'
        starting_coeffs = np.array([
            [1., 0., 0., 0.],
            [0., 1., 0., 0.],
            [0., 0., 1., 0.],
            [0., 0., 0., 1.],
        ]).reshape((4, 4, 1))
        starting_time_steps = 3

        super(BDF4, self).__init__(A=A, B=B, U=U, V=V, abscissa=np.ones(1),
            starting_method=(starting_scheme_name, starting_coeffs, starting_time_steps))