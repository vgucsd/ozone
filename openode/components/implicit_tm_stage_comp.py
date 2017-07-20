import numpy as np
from six import iteritems
import scipy.sparse

from openmdao.api import ExplicitComponent

from openode.utils.var_names import get_name
from openode.utils.units import get_rate_units


class ImplicitTMStageComp(ExplicitComponent):

    def initialize(self):
        self.metadata.declare('states', type_=dict, required=True)
        self.metadata.declare('time_units', values=(None,), type_=str, required=True)
        self.metadata.declare('num_stages', type_=int, required=True)
        self.metadata.declare('num_step_vars', type_=int, required=True)
        self.metadata.declare('glm_A', type_=np.ndarray, required=True)
        self.metadata.declare('glm_U', type_=np.ndarray, required=True)
        self.metadata.declare('i_step', type_=int, required=True)

    def setup(self):
        time_units = self.metadata['time_units']
        num_stages = self.metadata['num_stages']
        num_step_vars = self.metadata['num_step_vars']
        i_step = self.metadata['i_step']
        glm_A = self.metadata['glm_A']
        glm_U = self.metadata['glm_U']

        self.add_input('h', units=time_units)

        for state_name, state in iteritems(self.metadata['states']):
            size = np.prod(state['shape'])
            shape = state['shape']

            F_name = get_name('F', state_name, i_step=i_step)
            y_old_name = get_name('y_old', state_name, i_step=i_step)
            Y_name = get_name('Y', state_name, i_step=i_step)

            self.add_input(F_name, shape=(num_stages,) + shape,
                units=get_rate_units(state['units'], time_units))

            self.add_input(y_old_name, shape=(num_step_vars,) + shape,
                units=state['units'])

            self.add_output(Y_name, shape=(num_stages,) + shape,
                units=state['units'])

            Y_arange = np.arange(num_stages * size).reshape(
                (num_stages,) + shape)

            F_arange = np.arange(num_stages * size).reshape(
                (num_stages,) + shape)

            y_arange = np.arange(num_step_vars * size).reshape(
                (num_step_vars,) + shape)

            # -----------------

            # (num_stages, num_stages,) + shape
            rows = np.einsum('i...,j->ij...', Y_arange, np.ones(num_stages, int)).flatten()

            cols = np.zeros((num_stages, num_stages,) + shape, int).flatten()
            self.declare_partials(Y_name, 'h', rows=rows, cols=cols)

            cols = np.einsum('j...,i->ij...', F_arange, np.ones(num_stages, int)).flatten()
            self.declare_partials(Y_name, F_name, rows=rows, cols=cols)

            # -----------------

            # (num_stages, num_step_vars,) + shape
            data = np.einsum('ij,...->ij...',
                glm_U, np.ones(shape)).flatten()
            rows = np.einsum('i...,j->ij...', Y_arange, np.ones(num_step_vars)).flatten()
            cols = np.einsum('j...,i->ij...', y_arange, np.ones(num_stages)).flatten()

            self.declare_partials(Y_name, y_old_name, val=data, rows=rows, cols=cols)

    def compute(self, inputs, outputs):
        glm_A = self.metadata['glm_A']
        glm_U = self.metadata['glm_U']
        i_step = self.metadata['i_step']

        for state_name, state in iteritems(self.metadata['states']):
            size = np.prod(state['shape'])
            shape = state['shape']

            F_name = get_name('F', state_name, i_step=i_step)
            y_old_name = get_name('y_old', state_name, i_step=i_step)
            Y_name = get_name('Y', state_name, i_step=i_step)

            outputs[Y_name] = 0. \
                + np.einsum('ij,j...->i...', glm_A, inputs[F_name]) * inputs['h'] \
                + np.einsum('ij,j...->i...', glm_U, inputs[y_old_name])

    def compute_partials(self, inputs, outputs, partials):
        time_units = self.metadata['time_units']
        num_stages = self.metadata['num_stages']
        num_step_vars = self.metadata['num_step_vars']
        glm_A = self.metadata['glm_A']
        glm_U = self.metadata['glm_U']
        i_step = self.metadata['i_step']

        for state_name, state in iteritems(self.metadata['states']):
            size = np.prod(state['shape'])
            shape = state['shape']

            F_name = get_name('F', state_name, i_step=i_step)
            y_old_name = get_name('y_old', state_name, i_step=i_step)
            Y_name = get_name('Y', state_name, i_step=i_step)

            # (num_stages, num_stages,) + shape

            partials[Y_name, F_name] = np.einsum(
                '...,ij->ij...', np.ones(shape), glm_A).flatten() * inputs['h']

            partials[Y_name, 'h'] = np.einsum(
                'ij,j...->ij...', glm_A, inputs[F_name]).flatten()
