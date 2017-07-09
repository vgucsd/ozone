import numpy as np
from six import iteritems
import scipy.sparse
import scipy.sparse.linalg

from openmdao.api import ImplicitComponent

from openode.utils.var_names import get_F_name, get_y_old_name, get_y_new_name
from openode.utils.units import get_rate_units


class VectorizedStepComp(ImplicitComponent):

    def initialize(self):
        self.metadata.declare('states', type_=dict, required=True)
        self.metadata.declare('time_units', values=(None,), type_=str, required=True)
        self.metadata.declare('num_time_steps', type_=int, required=True)
        self.metadata.declare('num_stages', type_=int, required=True)
        self.metadata.declare('num_step_vars', type_=int, required=True)
        self.metadata.declare('glm_B', type_=np.ndarray, required=True)
        self.metadata.declare('glm_V', type_=np.ndarray, required=True)

    def setup(self):
        time_units = self.metadata['time_units']
        num_time_steps = self.metadata['num_time_steps']
        num_stages = self.metadata['num_stages']
        num_step_vars = self.metadata['num_step_vars']
        glm_B = self.metadata['glm_B']
        glm_V = self.metadata['glm_V']

        self.dy_dy = dy_dy = {}
        self.dy_dy_inv = dy_dy_inv = {}

        h_arange = np.arange(num_time_steps - 1)

        self.add_input('h_vec', shape=(num_time_steps - 1), units=time_units)

        for state_name, state in iteritems(self.metadata['states']):
            size = np.prod(state['shape'])
            shape = state['shape']

            F_name = 'F:%s' % state_name
            y0_name = 'y0:%s' % state_name
            y_name = 'y:%s' % state_name

            y0_arange = np.arange(num_step_vars * size).reshape((num_step_vars,) + shape)

            y_arange = np.arange(num_time_steps * num_step_vars * size).reshape(
                (num_time_steps, num_step_vars,) + shape)

            F_arange = np.arange((num_time_steps - 1) * num_stages * size).reshape(
                (num_time_steps - 1, num_stages,) + shape)

            self.add_input(F_name,
                shape=(num_time_steps - 1, num_stages,) + shape,
                units=get_rate_units(state['units'], time_units))

            self.add_input(y0_name,
                shape=(num_step_vars,) + shape,
                units=state['units'])

            self.add_output(y_name,
                shape=(num_time_steps, num_step_vars,) + shape,
                units=state['units'])

            # -----------------

            # (num_time_steps, num_step_vars,) + shape
            data1 = np.ones(num_time_steps * num_step_vars * size)
            rows1 = np.arange(num_time_steps * num_step_vars * size)
            cols1 = np.arange(num_time_steps * num_step_vars * size)

            # (num_time_steps - 1, num_step_vars, num_step_vars,) + shape
            data2 = np.einsum('i...,jk->ijk...',
                np.ones((num_time_steps - 1,) + shape), -glm_V).flatten()
            rows2 = np.einsum('ij...,k->ijk...',
                y_arange[1:, :, :], np.ones(num_step_vars)).flatten()
            cols2 = np.einsum('ik...,j->ijk...',
                y_arange[:-1, :, :], np.ones(num_step_vars)).flatten()

            data = np.concatenate([data1, data2])
            rows = np.concatenate([rows1, rows2])
            cols = np.concatenate([cols1, cols2])

            dy_dy[state_name] = scipy.sparse.csc_matrix(
                (data, (rows, cols)),
                shape=(
                    num_time_steps * num_step_vars * size,
                    num_time_steps * num_step_vars * size))

            dy_dy_inv[state_name] = scipy.sparse.linalg.splu(dy_dy[state_name])

            self.declare_partials(y_name, y_name, val=data, rows=rows, cols=cols)

            # -----------------

            # (num_step_vars,) + shape
            data = -np.ones((num_step_vars,) + shape).flatten()
            rows = y_arange[0, :, :].flatten()
            cols = y0_arange.flatten()

            self.declare_partials(y_name, y0_name, val=data, rows=rows, cols=cols)

            # -----------------

            # (num_time_steps - 1, num_step_vars, num_stages,) + shape
            rows = np.einsum('ij...,k->ijk...', y_arange[1:, :, :], np.ones(num_stages)).flatten()

            cols = np.einsum('jk...,i->ijk...',
                np.ones((num_step_vars, num_stages,) + shape), h_arange).flatten()
            self.declare_partials(y_name, 'h_vec', rows=rows, cols=cols)

            cols = np.einsum('ik...,j->ijk...', F_arange, np.ones(num_step_vars)).flatten()
            self.declare_partials(y_name, F_name, rows=rows, cols=cols)

    def apply_nonlinear(self, inputs, outputs, residuals):
        num_time_steps = self.metadata['num_time_steps']
        num_step_vars = self.metadata['num_step_vars']
        glm_B = self.metadata['glm_B']

        dy_dy = self.dy_dy

        for state_name, state in iteritems(self.metadata['states']):
            size = np.prod(state['shape'])
            shape = state['shape']

            F_name = 'F:%s' % state_name
            y0_name = 'y0:%s' % state_name
            y_name = 'y:%s' % state_name

            # dy_dy term
            in_vec = outputs[y_name].reshape((num_time_steps * num_step_vars * size))
            out_vec = dy_dy[state_name].dot(in_vec).reshape(
                (num_time_steps, num_step_vars,) + shape)

            residuals[y_name] = out_vec # y term
            residuals[y_name][0, :, :] -= inputs[y0_name] # y0 term
            residuals[y_name][1:, :, :] -= np.einsum('jl,i,il...->ij...',
                glm_B, inputs['h_vec'], inputs[F_name]) # hF term

    def solve_nonlinear(self, inputs, outputs):
        num_time_steps = self.metadata['num_time_steps']
        num_step_vars = self.metadata['num_step_vars']
        glm_B = self.metadata['glm_B']

        dy_dy_inv = self.dy_dy_inv

        for state_name, state in iteritems(self.metadata['states']):
            size = np.prod(state['shape'])
            shape = state['shape']

            F_name = 'F:%s' % state_name
            y0_name = 'y0:%s' % state_name
            y_name = 'y:%s' % state_name

            vec = np.zeros((num_time_steps, num_step_vars,) + shape)
            vec[0, :, :] += inputs[y0_name] # y0 term
            vec[1:, :, :] += np.einsum('jl,i,il...->ij...',
                glm_B, inputs['h_vec'], inputs[F_name]) # hF term

            outputs[y_name] = dy_dy_inv[state_name].solve(vec.flatten(), 'N').reshape(
                (num_time_steps, num_step_vars,) + shape)

    def linearize(self, inputs, outputs, partials):
        glm_B = self.metadata['glm_B']

        for state_name, state in iteritems(self.metadata['states']):
            size = np.prod(state['shape'])
            shape = state['shape']

            F_name = 'F:%s' % state_name
            y0_name = 'y0:%s' % state_name
            y_name = 'y:%s' % state_name

            # (num_time_steps - 1, num_step_vars, num_stages,) + shape

            partials[y_name, F_name] = -np.einsum(
                '...,jk,i->ijk...', np.ones(shape), glm_B, inputs['h_vec']).flatten()

            partials[y_name, 'h_vec'] = -np.einsum(
                'jk,ik...->ijk...', glm_B, inputs[F_name]).flatten()

    def solve_linear(self, d_outputs, d_residuals, mode):
        num_time_steps = self.metadata['num_time_steps']
        num_step_vars = self.metadata['num_step_vars']

        dy_dy_inv = self.dy_dy_inv

        for state_name, state in iteritems(self.metadata['states']):
            size = np.prod(state['shape'])
            shape = state['shape']

            y_name = 'y:%s' % state_name

            if mode == 'fwd':
                rhs_vec = d_residuals[y_name].flatten()
                solve_mode = 'N'
            elif mode == 'rev':
                rhs_vec = d_outputs[y_name].flatten()
                solve_mode = 'T'

            sol_vec = dy_dy_inv[state_name].solve(rhs_vec, solve_mode)

            if mode == 'fwd':
                d_outputs[y_name] = sol_vec.reshape((num_time_steps, num_step_vars,) + shape)
            elif mode == 'rev':
                d_residuals[y_name] = sol_vec.reshape((num_time_steps, num_step_vars,) + shape)