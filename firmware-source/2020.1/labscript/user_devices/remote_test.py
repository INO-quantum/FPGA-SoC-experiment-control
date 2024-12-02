# demonstation how to update a global value in Runmanager and compile and submit a new shot to blacs
# we wait until h5 file is created and check that global is written correctly
# and we check that there is valid data in file, otherwise there was a compilation error.

# Note: Runmanger engage function does not return information if shot compilaton gave an error or not!
#       h5 file is always created but contains only these groups: calibrations, devices, globals
#       globals attributes are already set to the new value.
#       so we check that h5 file contains all other groups (see check_groups) to contain valid data.
#       even this sometimes fails since file is only partially written. so we retry.
#       after WAIT_LOOPS and total WAIT_TIME seconds we stop if still fails.

# this file is supposed to be placed into user_devices folder

from runmanager.remote import Client
from h5py import File
from zprocess.utils import TimeoutError

from datetime import datetime
from os.path import isfile, join, exists, sep
from time import sleep

# if True show all file datasets and attributes
# requires h5_file_parser in same folder
show_file_content = False
if show_file_content:
    from user_devices.h5_file_parser import read_file

# name of variable to update in runmanager
# create a group and add this variable. this is an integer.
# we increment it for each execution of this script.
var_name = 'shot_number'

# server IP address
SERVER_IP = 'localhost'

# True = submit to blacs, False = do not submit to blacs
run_shots = True

# restart and engage every number of shots. None = never, 1 = each, 2 = every second, etc.
restart_engage_num = None

# we check that each of these groups exist in h5 file and have at least 1 dataset
check_groups = [#'calibrations', # this is always there but with 0 entries
                'globals', # this is always there and is not empty since we add var_name
                #'devices', # this is always there but might be empty
                'connection table', 'labscriptlib', 'script' # these are only there if compilation is ok
                ]

# set waiting times in seconds before or after engage. set None if not used
wait_before_engage = None
wait_after_engage  = None

# maximum waiting time in seconds until h5 file is written or error
WAIT_TIME = 100.0

# number of loops to wait. this gives the resolution in time.
# each loop we check if h5 file exists
WAIT_LOOPS = int(WAIT_TIME//1.0)

def check_file(path, var_name, value):
    # returns True when h5 file has data and contains global of given value
    print("check file '%s'" % path)
    with File(path, 'r') as f:
        # check if groups exist and are not empty
        for group in check_groups:
            try:
                data = f[group]
            except KeyError:
                print("group '%s' does not exist!" % (group))
                return False
            attrs = data.attrs
            try:
                data = data[()]
                try:
                    bytes = data.nbytes
                    l = len(data)
                except AttributeError: # bytes object
                    bytes = len(data)
                    l = 0
                type = 'dataset'
            except TypeError:
                bytes = 0
                l = len(data)
                type = 'group'
            if l == 0 and len(attrs) == 0 and bytes == 0:
                print("%s '%s' has no data!" % (type, group))
                return False
            else:
                #print("%s '%s' with %i entries, %i attributes, %i bytes (ok)" % (type, group, l, len(attrs), bytes))
                pass

        # check if globals have been updated
        try:
            g = f['globals']
            file_value = g.attrs[var_name]
        except KeyError:
            print("error: '%s' not in globals!" % (var_name))
            return False
        if file_value != value:
            print("error: '%s' = %i != %i as expected!" % (var_name, file_value, value))
            return False
        else:
            print("globals:", {k:v for k,v in g.attrs.items()}, 'ok')

    return True

if __name__ == '__main__':
    t = datetime.now()
    #print(t)
    tstr = '%4i/%02i/%02i %02i:%02i:%09.6f' % (t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond/1e6)
    print(tstr)

    # setup default client with runmanager with 1s timeout
    try:
        rm = Client(host=SERVER_IP, timeout=1.0)
    except Exception as e:
        print('exception', e)
        exit()

    print('connection established')

    try:
        rsp = rm.say_hello()
        print('hello responds:', rsp)
    except Exception as e:
        print('exception happened:', e)
        exit()

    try:
        print("hello responds:", rm.say_hello())
        print("Runmanager version:", rm.get_version())
        current = rm.get_globals()
        print("get globals:", current)
        try:
            value = current[var_name]
        except:
            print("please add '%s' to Runmanager globals!" % var_name)
            exit()
        try:
            rm.set_globals({var_name: value + 1})
        except ValueError:
            print("cannot set '%s' in Runmanager!" % var_name)
            exit()
        current = rm.get_globals()
        print("get globals:", current)
        try:
            new_value = current[var_name]
        except:
            print("cannot get '%s' from Runmanager!" % var_name)
            exit()
        if new_value != value + 1:
            print("updated '%s' = %i but should be %i " % (var_name, new_value, value+1))
            exit()
        print("sucessfully updated '%s' to %i" % (var_name, value + 1))
        script = rm.get_labscript_file()
        print("current labscript file:", script)
        folder = rm.get_shot_output_folder()
        print("current shot output folder:", folder)
        num_shots = rm.n_shots()
        print("number shots:", num_shots)
        is_error = rm.error_in_globals()
        if is_error:
            print("error in globals!")
            exit()
        else:
            print("no error.")
        submit = rm.get_run_shots()
        if submit != run_shots:
            print("\nwarning: setting 'Run shot(s)' = %s in Runviewer!" % run_shots)
            rm.set_run_shots(run_shots)
            submit = rm.get_run_shots()
            if submit != run_shots:
                print("error: could not set 'Run shot(s)' = %s in Runviewer!\n" % run_shots)
                exit()
            else:
                print("Run shot(s) = %s successfully set\n" % run_shots)
        else:
            print("Run shot(s) = %s" % run_shots)

        if wait_before_engage is not None:
            print('waiting %.3fs ...' % wait_before_engage)
            sleep(wait_before_engage)

        index = int(folder.split(sep)[-1])
        if restart_engage_num is None or (index % restart_engage_num) != (restart_engage_num-1):
            print(index, 'engage ...')
            result = rm.engage()
        else:
            print(index, 'restart ...')
            result = rm.restart()
            sleep(2.0)
            print(index, 'engage ...')
            result = rm.engage()

        # this returns None regardless of ok or error
        print('engage done, result:', result)

        if wait_after_engage is not None:
            print('waiting %.3fs ...' % wait_after_engage)
            sleep(wait_after_engage)

        # next folder is also immediately updated although files not finised writing!
        new_folder = rm.get_shot_output_folder()
        print("next shot output folder:", new_folder)

        # generate h5 file names
        name = script.split(sep)[-1].split('.')[0]
        date = folder.split(sep)
        index = '_' + date[-1] + '_'
        date = '-'.join(date[-4:-1])
        ext = '.h5'
        name = folder + sep + date + index + name
        files = [name + ('_%i'%i) + ext for i in range(num_shots)]
        #print(files)

        for f in files[-1::-1]:
            found = False
            ok = False
            print('shot file:', f)
            for i in range(WAIT_LOOPS):
                if exists(f):
                    found = True
                    if check_file(f, var_name, new_value):
                        if show_file_content:
                            read_file(f)
                        ok = True
                        break
                    else:
                        print('not ok (retry)')
                sleep(WAIT_TIME / WAIT_LOOPS)
                print('waiting %.1fs' % ((i+1) * WAIT_TIME / WAIT_LOOPS))
            if not found:
                print("cannot find h5 file!")
                print(f)
                exit()
            elif not ok:
                print("incomplete data in h5 file!")
                exit()
    except TimeoutError:
        print("error timeout: coult not connect to Runmanager!")
        exit()

print("%i h5 file%s ok" % (num_shots, '' if num_shots == 1 else 's'))
