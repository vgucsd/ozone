from __future__ import division
import numpy as np
import unittest
import scipy.integrate
from six import iteritems, itervalues

from openmdao.api import Problem, ScipyOptimizer, IndepVarComp

from openode.api import ODEIntegrator
from openode.tests.ode_functions.simple_ode import SimpleODEFunction
from openode.utils.suppress_printing import suppress_stdout_stderr


class Test(unittest.TestCase):

    def setUp(self):
        pass

    def run_ode(self, integrator_name, scheme_name):
        times = np.linspace(0., 1., 20)
        y0 = 1.

        ode_function = SimpleODEFunction()

        integrator = ODEIntegrator(ode_function, integrator_name, scheme_name,
            times=times, initial_conditions={'y': y0},)

        prob = Problem(integrator)

        if integrator_name == 'SAND':
            prob.driver = ScipyOptimizer()
            prob.driver.options['optimizer'] = 'SLSQP'
            prob.driver.options['tol'] = 1e-9
            prob.driver.options['disp'] = True

            integrator.add_subsystem('dummy_comp', IndepVarComp('dummy_var', val=1.0))
            integrator.add_objective('dummy_comp.dummy_var')

        with suppress_stdout_stderr():
            prob.setup(check=False)
            prob.run_driver()

        return prob

    def compute_diff(self, integrator_name, scheme_name, y_ref):
        y = self.run_ode(integrator_name, scheme_name)['output_comp.y']

        return np.linalg.norm(y - y_ref) / np.linalg.norm(y_ref)

    def test_tm(self):
        scheme_names = [
            'ForwardEuler', 'BackwardEuler', 'RK4', 'ExplicitMidpoint', 'ImplicitMidpoint']

        for scheme_name in scheme_names:
            y_ref = self.run_ode('TM', scheme_name)['output_comp.y']

            for integrator_name in ['TM', 'MDF', 'SAND']:
                diff = self.compute_diff(integrator_name, scheme_name, y_ref)
                print('%20s %5s %16.9e' % (scheme_name, integrator_name, diff))
                self.assertTrue(diff < 1e-10, 'Error when integrating with %s %s' % (
                    integrator_name, scheme_name))

        for integrator_name in ['TM', 'MDF', 'SAND']:
            prob = self.run_ode(integrator_name, 'ForwardEuler')
            with suppress_stdout_stderr():
                jac = prob.check_partials(compact_print=True)
            for comp_name, jac_comp in iteritems(jac):
                for partial_name, jac_partial in iteritems(jac_comp):
                    mag_fd = jac_partial['magnitude'].fd
                    mag_fwd = jac_partial['magnitude'].forward
                    mag_rev = jac_partial['magnitude'].reverse

                    abs_fwd = jac_partial['abs error'].forward
                    abs_rev = jac_partial['abs error'].reverse

                    rel_fwd = jac_partial['rel error'].forward
                    rel_rev = jac_partial['rel error'].reverse

                    non_zero = np.max([mag_fd, mag_fwd, mag_rev]) > 1e-12
                    if non_zero:
                        print('%16.9e %16.9e %5s %s %s' % (
                            jac_partial['rel error'].forward,
                            jac_partial['rel error'].reverse,
                            integrator_name, comp_name, partial_name,
                        ))
                        self.assertTrue(rel_fwd < 1e-3 or abs_fwd < 1e-3)
                        self.assertTrue(rel_rev < 1e-3 or abs_rev < 1e-3)



if __name__ == '__main__':
    unittest.main()
