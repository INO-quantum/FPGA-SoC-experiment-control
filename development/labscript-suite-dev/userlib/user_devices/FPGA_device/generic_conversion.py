#!/usr/bin/python
#-*- coding: latin-1 -*-

# only additional dependency is on numerical python
import numpy as np

# this file must be in labscriptlib/<experiment> or user_devices/ or pythonlib folder (default)
from labscript import LabscriptError
from labscript_utils.unitconversions import UnitConversion
# TODO: it would be nice to remove this dependency
from user_devices.FPGA_device.labscript_device import default_ao_props

class generic_conversion(UnitConversion):
    """
    generic unit conversion class
    give calibration_parameters a dictionary with required keys:
    'unit' is displayed by labscript as the unit of user input.
    'equation' must be a function of 'user_param', given in units 'unit', and converts it to a voltage (i.e. is equivalent to unit_to_base function)
    optional calibration_parameters keys:
    'user_param' is the variable representing the user input, default 'x'.
    'min' minimum value in units 'unit'. default default_ao_props['min'].
    'max' maximum value in units 'unit'. default default_ao_props['max']
    'step' step when clicking in gui on up/down arrow. default default_ao_props['step']
    'decimals' number of decimals to be displayed in gui. default default_ao_props['decimals']
    notes:
    - does the unit conversion and dynamically creates functions unit_to_base and unit_from_base needed for UnitConversion class.
    - input 'user_param' values are automatically clipped to 'min' <= 'user_param' <= 'max' before unit conversion.
    - after unit conversion the resulting voltage is automatically clipped to default_ao_props defined in FPGA_device.
    """

    # This must be defined outside of init, and must match the default hardware unit specified within the BLACS tab
    # TODO: would like to define this in BLACS tab but cannot import here!? (see above)
    base_unit   = default_ao_props['base_unit']

    # number of decimals in base unit
    V_decimals = default_ao_props['decimals']

    # if True (default) round values to number of decimals.
    # notes:
    # - round=True can generate a Labscript warning 'Failed to convert number of significant figures to new unit...'
    #   in output_classes.py class AO, function change_unit. this happens when changing voltage by least significant digit
    #   while derived unit does not change due to rounding. this warning is not nice but can be ignored.
    # - round=False will display nonzero digits beyond significant digits.
    # - Labscript always displays more digits than needed. the number of digits can sometimes even change.
    round = True

    # number of values used to calculate starting values in from_base()
    num_start = 10

    def __init__(self, calibration_parameters = None):
        #print('generic_conversion::__init__ params=',calibration_parameters)
        if calibration_parameters is None:
            calibration_parameters = {}
            self.derived_units = []
        else:
            # get unit and equation. both are mandatory.
            try:
                self.unit = calibration_parameters['unit']
                self.equation = calibration_parameters['equation']
            except KeyError:
                # TODO: this will raise a NameError since I could not import LabscriptError when copied into labsript source?
                raise LabscriptError("generic_conversion error: please give 'unit' and 'equation' as calibration_parameters!")

            # define derived_units which is required for UnitConversionClass
            if self.unit == '%': self.unit = 'percent'
            self.derived_units = [self.unit]

            # get optional 'user_param' and replace with 'x' in equation.
            # this is easier than defining a variable with name 'user_param'.
            try:
                self.user_param = calibration_parameters['user_param']
                self.equation = self.equation.replace(self.user_param, 'x')
            except KeyError:
                self.user_param = 'x'

            # compile equation as function of 'x'
            self.compiled = compile(self.equation, 'conv', 'eval')

            # get optional number of decimals from which tolerance for newton method is calculated
            try:
                self.decimals = calibration_parameters['decimals']
            except KeyError:
                self.decimals = default_ao_props['decimals']
            self.x_tol = 10**(-self.decimals-2)

            # set default voltages. might be overwritten by min/max values below.
            self.V_min = default_ao_props['min']
            self.V_max = default_ao_props['max']

            # get min/max in user-defined unit:
            # if 'min' or 'max' given: calculate V_min and V_max in volts.
            # otherwise calculate with newton() 'min' or 'max' from default 'V_min' or 'V_max' voltage.
            # note: if 'min' or 'max' is not given we assume that full voltage range is valid, which might produces problems.
            #       therefore, give always 'min' and 'max' for equations which are valid only in a limited range.
            try:
                x = self.min = calibration_parameters['min']
                self.V_min = eval(self.compiled)
            except KeyError:
                y = self.V_min
                max = calibration_parameters['max'] if 'max' in calibration_parameters else None
                x, err, ok, iter = newton((lambda x: eval(compiled)-y), x0 = 0.0, dx = 1.0, tol = self.x_tol, x_min=None, x_max=max, warn=False)
                #x, err, ok = secant((lambda x: eval(self.compiled) - y), self.V_min, self.V_max, tol=self.x_tol, maxiter=50, print_warning=False)
                if not ok:
                    txt = "generic_conversion error: could not calculate min value for equation:\n%s\nwith %f%s!\ngive 'min' in connection table." % (self.equation, y, self.base_unit)
                    print(txt)
                    raise LabscriptError(txt)
                else: self.min = x
            try:
                x = self.max = calibration_parameters['max']
                self.V_max = eval(self.compiled)
            except KeyError:
                y = self.V_max
                x, err, ok, iter = newton((lambda x: eval(compiled)-y), x0 = 0.0, dx = 1.0, tol = self.x_tol, x_min=self.min, x_max=None, warn=False)
                #x, err, ok = secant((lambda x: eval(self.compiled) - y), self.V_min, self.V_max, tol=self.x_tol, maxiter=50, print_warning=False)
                if not ok:
                    txt = "generic_conversion error: could not calculate max value for equation '%s' with %f%s!\ngive 'max' in connection table." % (self.equation, y, self.base_unit)
                    print(txt)
                    raise LabscriptError(txt)
                else: self.max = x

            # get mapping y(x) for calculation of starting values
            self.x_rng = np.linspace(self.min, self.max, num=self.num_start, endpoint=True)
            self.y_rng = np.array([eval(self.compiled) for x in self.x_rng])
            # sort by increasing y-values
            index = np.argsort(self.y_rng)
            self.x_rng = self.x_rng[index]
            self.y_rng = self.y_rng[index]

        setattr(self, self.unit+'_to_base', self.to_base)
        setattr(self, self.unit+'_from_base', self.from_base)
        self.parameters = calibration_parameters
        UnitConversion.__init__(self, self.parameters)

    @staticmethod
    def get_limits(calibration_parameters):
        "static function which returns [V_min, V_max, min, max] for given calibration parameters"
        # temporarily create a generic_conversion class object and return limits
        gc = generic_conversion(calibration_parameters)
        return [gc.V_min, gc.V_max, gc.min, gc.max]

    def to_base(self, x):
        "convert unit to Volts. x can be a numpy array"
        x = np.clip(x, self.min, self.max)
        if self.round : y = np.round(eval(self.compiled),self.V_decimals)
        else:           y = eval(self.compiled)
        y = np.clip(y, self.V_min, self.V_max)
        #print('%%s %%.%if -> %%s %%.%if' % (self.decimals, self.V_decimals) % (self.user_param, x, self.base_unit, y))
        return y

    def from_base(self, y):
        "convert Volts to unit using newton method"
        #TODO: can this be made more efficient for ndarrays?
        if isinstance(y, np.ndarray):
            return np.array([self.from_base(yi) for yi in y])
        if   y < self.V_min: y = self.V_min
        elif y > self.V_max: y = self.V_max
        # find staring values x0 and x1 left and right of solution y(x) = y
        x0 = self.x_rng[self.y_rng < y]
        x1 = self.x_rng[self.y_rng > y]
        x0 = x0[-1] if (len(x0) > 0) else self.min
        x1 = x1[0]  if (len(x1) > 0) else self.max
        # instead of scipy.optimize.newton method we use newton method below to avoid additional dependencies
        # x = np.round(newton((lambda x: eval(self.compiled)-y), (self.V_min + self.V_max)/2, tol=tol, maxiter = 50), self.decimals)
        #x, err, ok = secant((lambda x: eval(self.compiled)-y), x0, x1, tol=self.x_tol, maxiter=50, print_warning=False)
        x, err, ok, iter = newton((lambda x: eval(self.compiled)-y), x0, dx=x1-x0, tol=self.x_tol, x_min=self.min, x_max=self.max, warn=False)
        # we ignore 'err' and 'ok' but check that y(x) == y within self.V_decimals
        if self.round:
            x = np.round(x, self.decimals)
            yx = np.round(eval(self.compiled), self.V_decimals)
        else:
            yx = eval(self.compiled)
        if abs(y - yx) > 10**(-self.V_decimals):
            #print({'equation':self.equation, 'x0':x0, 'dx':x1-x0, 'tol':self.x_tol, 'x_min':self.min, 'x_max':self.max, 'x':x, 'err':err, 'ok':ok, 'iter':iter})
            #print(np.transpose([self.x_rng, self.y_rng]))
            try:
                txt = "%s_from_base error y(x) != y: %%.%if != %%.%if (ok=%s)" % (self.unit, self.V_decimals, self.V_decimals, str(ok)) % (yx, y)
                print(txt)
            except BrokenPipeError: # this happens sometimes randomly. have no idea why?
                pass
            #raise LabscriptError(txt)
        if   x < self.min: x = self.min
        elif x > self.max: x = self.max
        #print('%%s %%.%if -> %%s %%.%if' % (self.V_decimals, self.decimals) % (self.base_unit, y, self.user_param, x))
        return x

def secant(func, x0, x1, tol=1e-12, maxiter=50, print_warning=True, return_iter=False):
    """
    secant method to find root of a function func(x) within starting values x=x0 and x=x1.
    optional parameter tol = aborts when error of x < tol.
    optional parameter maxiter gives maximum number of iterations. simple functions need < 25 iterations. more complicated < 50.
    optional parameter print_warning if True prints warnings, otherwise not. errors are always printed.
    optional parameter return_iter = returns number of iterations if True, otherwise not (default)
    returns [x, error, ok, optional iterations]
    x = estimated zero crossing.
    error = estimated error of x.
    ok = True if solution found, False if not found.
    iterations = returned number of iterations if return_iter = True.
    notes:
    if starting values are not crossing 0 returns x = error = 0.0 and ok = False.
    if maxiter reached returns last x and error but ok = False.
    if tolerance is too small might stop due to numerical errors and returns last x and error and ok = False.
    """
    #input = [func, x0, x1, tol, maxiter, return_iter]
    y_tol = 5e-16 # this defines how close to 0 we have to be for y.
    if x0 > x1: x0, x1 = x1, x0 # ensure x0 < x1
    y0 = func(x0)
    y1 = func(x1)
    x = error = 0.0
    i = 0
    ok = False
    goal_reached = False
    if tol < y_tol:
        print("secant error: tolerance %e smaller than %e! increase 'tol'." % (tol, y_tol))
    elif (y0 * y1 > 0) and (abs(y0) > y_tol) and (abs(y1) > y_tol): # bad initial values. when y0 or y1 is zero we continue.
        #print('%e %e %e' % (y0, y1, y0*y1))
        print('secant error: initial values x = [%f,%f] give y = [%f,%f] which do not cross zero!' % (x0, x1, y0, y1))
    else:
        xold = x1 - y0*(x1-x0)/(y1-y0)
        for i in range(maxiter):
            # calculte intersection point
            x = x0 - y0*(x1-x0)/(y1-y0)
            eold = error
            error = abs(x - xold)
            xold = x
            y = func(x)
            #print([i, [x0, x, x1], [y0, y, y1], np.sign(y0*y), np.sign(y*y1), x1 - x0, error])
            if error < tol: # tolerance reached.
                #print('error %e < tol %e' % (error, tol))
                if error == 0.0: # numerical limit reached or y == 0
                    if goal_reached or (abs(y) < y_tol): # solution found: take last error
                        if print_warning: print("secant warning: zero error obtained. returning last error %e instead." % (eold))
                        ok = True
                    else:
                        #print(input)
                        #print([i, [x0, x, x1], [y0, y, y1], np.sign(y0 * y), np.sign(y * y1), x1 - x0, error])
                        print("secant error: could not reach tolerance %e (returning last error %e)! increase 'tol'." % (tol, eold))
                    error = eold # we return last error
                    break
                if goal_reached: # stop after another security loop
                    ok = True
                    break
                else:
                    goal_reached = True
            if y0*y < 0: # root < x
                x1 = x
                y1 = y
            elif y*y1 < 0: # root > x
                x0 = x
                y0 = y
            elif y == 0: # root == x. this happens for linear equations.
                error = 0
                ok = True
                break
            else: # rounding error
                print('secant error: values x = [%f,%f,%f] give y = [%f,%f,%f] which do not cross zero!' % (x0, x, x1, y0, y, y1))
                break
        i += 1
        if not ok and (i >= maxiter):
            print('secant error: reached %i iterations!' % (maxiter))
    #print([x, error, ok, i])
    if return_iter: return [x, error, ok, i]
    else: return [x, error, ok]

def newton(func, x0, dx=1.0, tol=1e-12, maxiter=50, x_min=None, x_max=None, warn=True, escale=3.0):
    """
    finds x where func(x) == 0 within tolerance tol.
    func = function of x
    x0 = starting x-value
    dx = starting offset to calculate slope
    tol = goal error of found x-value.
    x_min = if not None minimum allowed x value
    x_max = if not None maximum allowed x value
    warn = if True print warnings, othersise not
    escale = error multiplication factor of abs(dx). adapted to remove errors and minimize warnings in tests.
    returns [x, error, ok]
    error = estimated error of x
    ok = True when solution found, False on error
    """
    if abs(dx) <= tol:
        print('newton error: dx=0!');
        return [x0, 0, False, 0]
    with np.errstate(all='raise'): # catches numpy RuntimeWarnings
        try:
            if (x_min is None): x_min = -np.inf
            if (x_max is None): x_max =  np.inf
            i = 0
            error = tol + 1.0
            while(error >= tol):
                if i >= maxiter: return [x0, error, False, i]
                error = escale*abs(dx) # we calculate error one iteration later to ensure one additional iteration after tolerance reached.
                x1 = x0 + dx
                if x0 < x_min: x0 = x_min; x1 = x_min + dx
                if x0 > x_max: x0 = x_max; x1 = x_max - dx
                if x1 < x_min: x1 = x_min; dx = x1 - x0
                if x1 > x_max: x1 = x_max; dx = x1 - x0
                y0 = func(x0)
                y1 = func(x1)
                if np.isnan(y0): return [x0, error, False, i]
                if np.isnan(y1): return [x0, error, False, i]
                if (y0 == 0): # exact goal reached. cannot continue.
                    #dx = x1 - y1*dx/(y1 - y0) - x0 # for calcuation of error use y1 which should be nonzero. result = 0.
                    if i == 1:
                        if warn: print('newton warning: unreliable error! return error = 0.')
                        dx = 0;
                    break
                elif (y0 == y1): # happens when y0 is close to zero due to numerical errors when tol is too small.
                    if (error < tol): # we cannot do another iteration but we are done
                        if warn: print("newton warning: numerical limit reached. returned value unreliable.")
                        break
                    else: # we cannot continue.
                        print("newton error: numerical limit reached. increase 'tol'.")
                        return [x0, error, False, i]
                dx = y0 * dx/(y1 - y0)
                x0 = x0 - dx
                i = i+1
            if x0 < x_min: x0 = x_min
            if x0 > x_max: x0 = x_max
            error = escale*abs(dx)
            return [x0, error, True, i]
        except Exception as e:
            print("newton exception '%s'" % (e))
            return [np.nan, np.nan, False, 0]

def test_newton():
    "test cases for newton function"
    # list of [1d equations of 'x', x0, x1, tol, maxiter, true solution, expected ok=False/True]
    tests = [
        # quadratic equation with exact solution found with few iterations when tolerance is not too tight.
        ['2-x^2', 0, 1, 3e-16, 25, None, None, np.sqrt(2), True], # get numerical problems y0==y1 depending on starting values and tolerance.
        ['2-x^2', 0, 2, 3e-16, 25, None, None, np.sqrt(2), True], # get numerical problems y0==y1 depending on starting values and tolerance.
        ['2-x^2', 0, 1, 5e-16, 25, None, None, np.sqrt(2), True], # tolerance ok
        ['2-x^2', 0, -1, 3e-16, 25, None, None, -np.sqrt(2), True], # get numerical problems y0==y1 depending on starting values and tolerance.
        ['2-x^2', 0, -1, 5e-16, 25, None, None, -np.sqrt(2), True],  # tolerance ok
        ['2-x^2', np.sqrt(2), 1, 1e-12, 25, None, None, np.sqrt(2), True], # x0 = solution. happens when limits reached. indicated error < true error.
        ['2-x^2', np.sqrt(2), -1, 1e-12, 25, None, None, np.sqrt(2), True], # x0 = solution, dx<0. happens when limits reached.
        ['2-x^2', np.sqrt(2), 1, 1e-4, 25, None, None, np.sqrt(2), True],  # x0 = solution. happens when limits reached. larger tolerance. indicated error < true error.
        ['2-x^2', np.sqrt(2), -1, 1e-4, 25, None, None, np.sqrt(2), True], # x0 = solution, dx<0.. happens when limits reached. larger tolerance.
        ['5-(x-3)^2', 0, 1, 1e-12, 25, None, None, 3 - np.sqrt(5), True],
        ['5-(x-3)^2', 3, 1, 1e-12, 25, None, None, 3 + np.sqrt(5), True], # get numerical problems y0==y1. but is ok.
        # 3rd order equation with solution at x=0 touches zero with horizontal tangent. x0 and dx must be close. requires many iterations.
        ['x^2-x^3', -1, 0.5, 1e-12, 25, None, None, 0, False], # fails because maxiter reached
        ['x^2-x^3', -1, 0.5, 1e-12, 60, None, None, 0, True], # ok after 60 iterations! approaching from left side solution <0
        ['x^2-x^3', 0.25, 0.25, 1e-12, 60, None, None, 0, True], # ok after 56 iterations! approaching from right side soltution >0
        ['x^2-x^3', -0.5, -0.25, 2e-5, 25, None, None, 0, True], # ok after 25 iterations & reduced accuracy. from left side solution <0. starting dx<0.
        ['x^2-x^3', 0.5, -0.25, 1e-5, 25, None, None, 0, True], # ok after 23 iterations & reduced accuracy. from left side solution >0. starting dx<0.
        # 3rd order equation with solution at x=1 crosses zero. solution is found easily as long as starting values are properly chosen.
        ['x^2-x^3', 1.5, 0.4, 1e-12, 25, None, None, 1, True], # TODO: indicated error > 5x expected error. ok for dx=0.4
        ['x^2-x^3', 0.7, 0.1, 1e-12, 60, None, None, 1, True], # indicated error < true error
        ['x^2-x^3', 0.8, -0.1, 1e-12, 60, None, None, 1, True],
        # 3rd order equation with offset has single numeric solution which is easy to find.
        ['1+x^2-x^3', 1, 1, 1e-10, 25, None, None, 1.4655712318767682, True], # indicated error < true error
        # testing more complicated functions with numeric solutions
        ['np.exp(-x)-3*x', 0, 1.0, 1e-12, 25, None, None, 0.2576276530497367, True],
        ['np.exp(x)-3*x', 0, 1.0, 1e-12, 25, None, None, 0.619061286735945, True],
        ['np.exp(x)-3*x', 2.5, 0.5, 1e-12, 25, None, None, 1.5121345516578426, True], # TODO: x0 = 2 indicated error > 5x expected error. ok with x0=2.5
        ['np.exp(-x)-x^2', 0, 1.0, 1e-12, 25, None, None, 0.7034674224983917, True],
        ['np.exp(x)-x^2', -1, -1.0, 1e-12, 25, None, None, -0.7034674224983924, True], # indicated error < true error
        ['np.cos(x)-np.exp(x)', -2, 1.5, 1e-12, 25, None, None, -1.2926957193733983, True], # numerical limit reached but ok.
        ['x/10-0.4002', 0, 5, 1e-12, 25, None, None, 4.002, True], # linear equation solved within 1 iteration. TODO: gives warning and sets error = 0.
        ['x/10-0.4002', 0, 1, 1e-12, 25, None, None, 4.002, True],  # linear equation solved within 2 iterations. indicated error is ok.
        # AOM calibration functions. need limits and good starting values
        ['(-0.02063+3.62077*np.tan(0.01724-0.19288*np.sqrt(x/100)+1.39915*x/100))-10', 80, 1.0, 1e-12, 25, 0, None, 100.04240713799629, True],
        ['np.sign(x-7.0)*(1.04532+np.sqrt(abs(-0.04508+(0.04255*x-0.07844)^2)))-10', 20, 1.0, 1e-12, 25, 0, None, 212.3533905020858, True], # discontinuity at 7
        ['np.sign(x-7.0)*(1.04532+np.sqrt(abs(-0.04508+(0.04255*x-0.07844)^2)))-1.5', 10, 5.0, 1e-12, 25, 0, None, 13.636912433386218, True],  # discontinuity at 7. # TODO: dx=1 indicated error > 5x expected error. ok for dx=5
        ['np.sign(x-7.0)*(1.04532+np.sqrt(abs(-0.04508+(0.04255*x-0.07844)^2)))-1.2', 10, 1.0, 1e-12, 25, 0, None, 8.017150305932008, True],  # discontinuity at 7
        # other tests
        ['np.log(x/50)', 40, 20, 1e-12, 25, 0, None, 50.0, True],# TODO: with tol=1e-12 indicated error > 5x expected error. ok with 1e-12
        ['np.log(x/50)', -1, 1, 1e-12, 25, 0.0, None, 50.0, False], # x0 outside valid range will clip to x0=0 but Log[0] raises exception.
        ['np.log(x/50)', -1, 1, 1e-12, 25, 0.1, None, 50.0, True], # works with proper boundaries
        ['x*32767/10+1', -10, 1, 1e-12, 25, None, None, -10/32767, True], # linear equation 'wrongly' scaled, solution close to 0. # TODO: with dx=1: indicated error > 5x expected error. ok with dx=5 or tol=1e-12 instead 1e-16.
        ['(x-80.237)/15.224+10', -50, -1, 1e-12, 25, None, None, -72.003, True], # TODO: with dx=1: indicated error > 5x expected error. with dx=5: true error > 3x expected error. ok with tol=1e-12 instead of 1e-16.
    ]
    warn = 0
    for i,test in enumerate(tests):
        equ, x0, dx, tol, maxiter, x_min, x_max, x, ok = test
        #result = secant((lambda x: eval(compile(equ.replace('^','**'), 'conv', 'eval'))), x0, x1, tol=tol, maxiter=maxiter, print_warning=True, return_iter=True)
        result = newton((lambda x: eval(compile(equ.replace('^', '**'), 'conv', 'eval'))), x0=x0, dx=dx, tol=tol, maxiter=maxiter, x_min=x_min, x_max=x_max)
        error = abs(result[0] - x)
        if result[2] != ok:            print("test %i result '%s' not expected! returns [%e,%e,%s,%i]" % (i, result[2], result[0], result[1], result[2],result[3])); exit()
        if ok and (error >= 3*tol):    print('test %i true error %e > 3x expected error %e' % (i, error, tol)); exit()
        elif ok and (error >= tol):    print('test %i warning: true error %e > expected error %e' % (i, error, tol)); warn += 1
        if ok and (result[1] > 5*tol): print('test %i: indicated error %e > 5x expected error %e' % (i, result[1], tol)); exit()
        elif ok and (result[1] > tol): print('test %i warning: indicated error %e > 3x expected error %e' % (i, result[1], tol)); warn += 1
        if ok and (result[1] < error): print('test %i warning: indicated error %e < true error %e' % (i, result[1], error)); warn += 1
        if ok: print('test %i ok: %s == 0 @ x = %e, error = %e, iterations = %i' % (i, equ, result[0], result[1], result[3]))
        else:  print('test %i ok: %s == 0 fails as expected. iterations = %i' % (i, equ, result[3]))
    if warn > 0: print('%i tests done with success, %i warnings' % (i+1, warn))
    else:        print('%i tests done with success!' % (i+1))

if __name__ == '__main__':
    # TODO: running of this test when this file is within labscript source code does not work since importing gives strange errors?
    #       however, for test we do not need UnitConversion class and this dependency can be commented temporarily.
    test_newton()

