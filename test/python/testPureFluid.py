from __future__ import division

import utilities
import numpy as np
import Cantera as ct
import Cantera.liquidvapor as lv

# To minimize data when transcribing tabulated data, the input units here are:
# T: K, P: MPa, rho: kg/m3, v: m3/kg, (u,h): kJ/kg, s: kJ/kg-K
# Which are then converted to SI
class StateData(object):
    def __init__(self, phase, T, p, rho=None, v=None, u=None, h=None, s=None, relax=False):
        self.phase = phase
        self.T = T
        self.p = p * 1e6
        self.rho = rho if rho else 1.0/v
        self.u = 1e3 * u if u is not None else 1e3 * h - self.p/self.rho
        self.s = 1e3 * s
        self.tolMod = 10.0 if relax else 1.0


class Tolerances(object):
    def __init__(self, p=None, u=None, s=None,
                 dUdS=None, dAdV=None, dPdT=None, hTs=None):
        self.p = p or 2e-5
        self.u = u or 2e-6
        self.s = s or 2e-6
        self.dUdS = dUdS or 2e-6
        self.dAdV = dAdV or 2e-6
        self.dPdT = dPdT or 2e-4
        self.hTs = hTs or 2e-4


class PureFluidTestCases(object):
    fluids = {}

    def __init__(self, name, refState, tolerances=Tolerances()):
        if name not in self.fluids:
            self.fluids[name] = lv.PureFluid('liquidvapor.cti', name)

        self.fluid = self.fluids[name]

        self.fluid.set(T=refState.T, Rho=refState.rho)
        self.refState = refState
        self.u0 = self.fluid.intEnergy_mass()
        self.s0 = self.fluid.entropy_mass()
        self.tol = tolerances

    def a(self, T, rho):
        """ Helmholtz free energy """
        self.fluid.set(T=T, Rho=rho)
        return self.fluid.intEnergy_mass() - T * self.fluid.entropy_mass()

    def test_ConsistencyTemperature(self):
        for state in self.states:
            dT = 2e-5 * state.T
            self.fluid.set(T=state.T-dT, Rho=state.rho)
            s1 = self.fluid.entropy_mass()
            u1 = self.fluid.intEnergy_mass()
            self.fluid.set(T=state.T+dT, Rho=state.rho)
            s2 = self.fluid.entropy_mass()
            u2 = self.fluid.intEnergy_mass()

            # At constant volume, dU = T dS
            msg = 'At state: T=%s, rho=%s' % (state.T, state.rho)
            self.assertNear((u2-u1)/(s2-s1), state.T, self.tol.dUdS, msg=msg)

    def test_ConsistencyVolume(self):
        for state in self.states:
            self.fluid.set(T=state.T, Rho=state.rho)
            p = self.fluid.pressure()
            V = 1 / state.rho
            dV = 5e-6 * V

            a1 = self.a(state.T, 1/(V-0.5*dV))
            a2 = self.a(state.T, 1/(V+0.5*dV))

            # dP/drho is high for liquids, so relax tolerances
            tol = 100 *self.tol.dAdV if state.phase == 'liquid' else self.tol.dAdV

            # At constant temperature, dA = - p dV
            msg = 'At state: T=%s, rho=%s' % (state.T, state.rho)
            self.assertNear(-(a2-a1)/dV, p, tol, msg=msg)

    def test_saturation(self):
        for state in self.states:
            if state.phase == 'super':
                continue

            dT = 1e-6 * state.T
            self.fluid.set(T=state.T, Vapor=0)
            p1 = self.fluid.pressure()
            vf = 1.0 / self.fluid.density()
            hf = self.fluid.enthalpy_mass()
            sf = self.fluid.entropy_mass()

            self.fluid.set(T=state.T + dT, Vapor=0)
            p2 = self.fluid.pressure()

            self.fluid.set(T=state.T, Vapor=1)
            vg = 1.0 / self.fluid.density()
            hg = self.fluid.enthalpy_mass()
            sg = self.fluid.entropy_mass()

            # Clausius-Clapeyron Relation
            msg = 'At state: T=%s, rho=%s' % (state.T, state.rho)
            self.assertNear((p2-p1)/dT, (hg-hf)/(state.T * (vg-vf)),
                            self.tol.dPdT, msg=msg)

            # True for a change in state at constant pressure and temperature
            self.assertNear(hg-hf, state.T * (sg-sf), self.tol.hTs, msg=msg)

    def test_pressure(self):
        for state in self.states:
            self.fluid.set(T=state.T, Rho=state.rho)
            # dP/drho is high for liquids, so relax tolerances
            tol = 50 *self.tol.p if state.phase == 'liquid' else self.tol.p
            tol *= state.tolMod
            msg = 'At state: T=%s, rho=%s' % (state.T, state.rho)
            self.assertNear(self.fluid.pressure(), state.p, tol, msg=msg)

    def test_internalEnergy(self):
        for state in self.states:
            self.fluid.set(T=state.T, Rho=state.rho)
            msg = 'At state: T=%s, rho=%s' % (state.T, state.rho)
            self.assertNear(self.fluid.intEnergy_mass()-self.u0,
                            state.u - self.refState.u,
                            self.tol.u * state.tolMod, msg=msg)

    def test_entropy(self):
        for state in self.states:
            self.fluid.set(T=state.T, Rho=state.rho)
            msg = 'At state: T=%s, rho=%s' % (state.T, state.rho)
            self.assertNear(self.fluid.entropy_mass()-self.s0,
                            state.s - self.refState.s,
                            self.tol.s * state.tolMod, msg=msg)

# Reference values for HFC134a taken from NIST Chemistry WebBook, which
# implements the same EOS from Tillner-Roth and Baehr as Cantera, so close
# agreement is expected.

class HFC134a(PureFluidTestCases, utilities.CanteraTest):
    states = [
        StateData('liquid', 175.0, 0.1, rho=1577.6239, u=77.534586, s=0.44788182),
        StateData('liquid', 210.0, 0.1, rho=1483.2128, u=119.48566, s=0.66633877),
        StateData('vapor', 250.0, 0.1, rho=5.1144317, u=365.59424, s=1.7577491),
        StateData('vapor', 370.0, 0.1, rho=3.3472612, u=459.82664, s=2.0970769),
        StateData('liquid', 290.0, 10, rho=1278.4700, u=216.99119, s=1.0613409),
        StateData('super', 410.0, 10, rho=736.54666, u=399.02258, s=1.5972395),
        StateData('super', 450.0, 40, rho=999.34087, u=411.92422, s=1.6108568)]

    def __init__(self, *args, **kwargs):
        refState = StateData('critical', 374.21, 4.05928,
                             rho=511.900, u=381.70937, s=1.5620991)
        PureFluidTestCases.__init__(self, 'hfc134a', refState)
        utilities.CanteraTest.__init__(self, *args, **kwargs)

# Reference values for the following substances are taken from the tables in
# W.C. Reynolds, "Thermodynamic Properties in SI", which is the source of
# Cantera's equations of state for these substances. Agreement is limited by
# the precision of the results printed in the book (typically 4 significant
# figures).

# Property comparisons for saturated states are further limited by the use of
# different methods for satisfying the phase equilibrium condition g_l = g_v.
# Cantera uses the actual equation of state, while the tabulated values given
# by Reynolds are based on the given P_sat(T_sat) relations.

class CarbonDioxide(PureFluidTestCases, utilities.CanteraTest):
    states = [
        StateData('liquid', 230.0, 2.0, rho=1132.4, h=28.25, s=0.1208),
        StateData('liquid', 270.0, 10.0, rho=989.97, h=110.59, s=0.4208),
        StateData('vapor', 250.0, 1.788, v=0.02140, h=358.59, s=1.4500, relax=True), #sat
        StateData('vapor', 300.0, 2.0, v=0.02535, h=409.41, s=1.6174),
        StateData('super', 500.0, 1.0, v=0.09376, h=613.22, s=2.2649),
        StateData('super', 600.0, 20.0, v=0.00554, h=681.94, s=1.8366)]

    def __init__(self, *args, **kwargs):
        refState = StateData('critical', 304.21, 7.3834,
                             rho=464.0, h=257.31, s=0.9312)
        tols = Tolerances(2e-3, 2e-3, 2e-3)
        PureFluidTestCases.__init__(self, 'carbondioxide', refState, tols)
        utilities.CanteraTest.__init__(self, *args, **kwargs)


class Heptane(PureFluidTestCases, utilities.CanteraTest):
    states = [
        StateData('liquid', 300.0, 0.006637, v=0.001476, h=0.0, s=0.0, relax=True), #sat
        StateData('liquid', 400.0, 0.2175, v=0.001712, h=248.01, s=0.709, relax=True), #sat
        StateData('vapor', 490.0, 1.282, v=0.02222, h=715.64, s=1.7137, relax=True), #sat
        StateData('vapor', 480.0, 0.70, v=0.04820, h=713.04, s=1.7477),
        StateData('super', 600.0, 2.0, v=0.01992, h=1014.87, s=2.2356),
        StateData('super', 680.0, 0.2, v=0.2790, h=1289.29, s=2.8450)]

    def __init__(self, *args, **kwargs):
        refState = StateData('critical', 537.68, 2.6199,
                             rho=197.60, h=747.84, s=1.7456)
        tols = Tolerances(2e-3, 2e-3, 2e-3)
        PureFluidTestCases.__init__(self, 'heptane', refState, tols)
        utilities.CanteraTest.__init__(self, *args, **kwargs)


# para-hydrogen
class Hydrogen(PureFluidTestCases, utilities.CanteraTest):
    states = [
        StateData('liquid', 18.0, 0.04807, v=0.013660, h=30.1, s=1.856, relax=True), #sat
        StateData('liquid', 26.0, 0.4029, v=0.015911, h=121.2, s=5.740, relax=True), #sat
        StateData('vapor', 30.0, 0.8214, v=0.09207, h=487.4, s=17.859, relax=True), #sat
        StateData('super', 100.0, 0.20, v=2.061, h=1398.3, s=39.869),
        StateData('super', 200.0, 20.0, v=0.04795, h=3015.9, s=31.274),
        StateData('super', 300.0, 0.50, v=2.482, h=4511.6, s=53.143),
        StateData('super', 600.0, 1.00, v=2.483, h=8888.4, s=60.398),
        StateData('super', 800.0, 4.0, v=0.8329, h=11840.0, s=58.890)]

    def __init__(self, *args, **kwargs):
        refState = StateData('critical', 32.938, 1.2838,
                             rho=31.36, h=346.5, s=12.536)
        tols = Tolerances(2e-3, 2e-3, 2e-3, 2e-4)
        PureFluidTestCases.__init__(self, 'hydrogen', refState, tols)
        utilities.CanteraTest.__init__(self, *args, **kwargs)


class Methane(PureFluidTestCases, utilities.CanteraTest):
    states = [
        StateData('liquid', 100.0, 0.50, rho=439.39, h=31.65, s=0.3206),
        StateData('liquid', 140.0, 2.0, rho=379.51, h=175.48, s=1.4963),
        StateData('vapor', 150.0, 0.20, v=0.3772, h=660.72, s=5.5435),
        StateData('vapor', 160.0, 1.594, v=0.03932, h=627.96, s=4.3648, relax=True), #sat
        StateData('vapor', 175.0, 1.0, v=0.08157, h=692.55, s=4.9558),
        StateData('super', 200.0, 0.2, v=0.5117, h=767.37, s=6.1574),
        StateData('super', 300.0, 0.5, v=0.3083, h=980.87, s=6.5513)]

    def __init__(self, *args, **kwargs):
        refState = StateData('critical', 190.555, 4.5988,
                             rho=160.43, h=490.61, s=3.2853)
        tols = Tolerances(2e-3, 2e-3, 2e-3)
        PureFluidTestCases.__init__(self, 'methane', refState, tols)
        utilities.CanteraTest.__init__(self, *args, **kwargs)


class Nitrogen(PureFluidTestCases, utilities.CanteraTest):
    states = [
        StateData('liquid', 80.0, 0.1370, v=0.001256, h=33.50, s=0.4668, relax=True), #sat
        StateData('vapor', 110.0, 1.467, v=0.01602, h=236.28, s=2.3896, relax=True), #sat
        StateData('super', 200.0, 0.5, v=0.1174, h=355.05, s=3.5019),
        StateData('super', 300.0, 10.0, v=0.00895, h=441.78, s=2.9797),
        StateData('super', 500.0, 5.0, v=0.03031, h=668.48, s=3.7722),
        StateData('super', 600.0, 100.0, v=0.00276, h=827.54, s=3.0208)]

    def __init__(self, *args, **kwargs):
        refState = StateData('critical', 126.200, 3.400,
                             rho=314.03, h=180.78, s=1.7903)
        tols = Tolerances(2e-3, 2e-3, 2e-3)
        PureFluidTestCases.__init__(self, 'nitrogen', refState, tols)
        utilities.CanteraTest.__init__(self, *args, **kwargs)


class Oxygen(PureFluidTestCases, utilities.CanteraTest):
    states = [
        StateData('liquid', 80.0, 0.03009, v=0.000840, h=42.56, s=0.6405, relax=True), #sat
        StateData('liquid', 125.0, 1.351, v=0.001064, h=123.24, s=1.4236, relax=True), #sat
        StateData('vapor', 145.0, 3.448, v=0.006458, h=276.45, s=2.4852, relax=True), #sat
        StateData('super', 200.0, 0.050, v=1.038, h=374.65, s=4.1275),
        StateData('super', 300.0, 1.0, v=0.07749, h=463.76, s=3.7135),
        StateData('super', 600.0, 0.20, v=0.7798, h=753.38, s=4.7982),
        StateData('super', 800.0, 5.0, v=0.04204, h=961.00, s=4.2571)
        ]

    def __init__(self, *args, **kwargs):
        refState = StateData('critical', 154.581, 5.0429,
                             rho=436.15, h=226.53, s=2.1080)
        tols = Tolerances(2e-3, 2e-3, 2e-3)
        PureFluidTestCases.__init__(self, 'oxygen', refState, tols)
        utilities.CanteraTest.__init__(self, *args, **kwargs)


class Water(PureFluidTestCases, utilities.CanteraTest):
    states = [
        StateData('liquid', 295.0, 0.002620, v=0.0010025, h=90.7, s=0.3193, relax=True),
        StateData('vapor', 315.0, 0.008143, v=17.80, h=2577.1, s=8.2216, relax=True),
        StateData('liquid', 440.0, 0.7332, v=0.001110, h=705.0, s=2.0096, relax=True),
        StateData('vapor', 510.0, 3.163, v=0.06323, h=2803.6, s=6.1652, relax=True),
        StateData('vapor', 400.0, 0.004, v=46.13, h=2738.8, s=9.0035),
        StateData('vapor', 500.0, 1.0, v=0.2206, h=2890.2, s=6.8223),
        StateData('super', 800.0, 0.01, v=36.92, h=3546.0, s=9.9699),
        StateData('super', 900.0, 0.70, v=0.5917, h=3759.4, s=8.2621),
        StateData('super', 1000.0, 30.0, v=0.01421, h=3821.6, s=6.6373),
        StateData('liquid', 500.0, 3.0, rho=832.04, h=975.68, s=2.58049)
        ]

    def __init__(self, *args, **kwargs):
        refState = StateData('critical', 647.286, 22.089,
                             rho=317.0, h=2098.8, s=4.4289)
        tols = Tolerances(2e-3, 2e-3, 2e-3)
        PureFluidTestCases.__init__(self, 'water', refState, tols)
        utilities.CanteraTest.__init__(self, *args, **kwargs)