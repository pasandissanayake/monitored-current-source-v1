import threading
import time
import numpy as np
import serial
import pylive
import colorama
from colorama import Fore, Back, Style
import keyboard
from datetime import datetime, timedelta
import warnings
import os
import re
import serial.tools.list_ports

#Global variables for the system
SENSE_VOLT_PROBE = 'A0'
LOAD_VOLT_PROBE = 'A1'
OUTPUT_PROBE = '5'
LOAD_VOLT_FACTOR = 2
LV_CONST = 0.2
P = 0.3
I = 0.0
D = 0.0

MAX_VOLT_ERROR = 0.1             # Maximum error of voltage measurement in Volts
DELAY = 0.01                     # Delay between two regulatory cycles in seconds

COM_PORT = "COM23"               # Serial port

# Global variables defining the job
calibrationArray = [1023, 0]    # Digital values shown for 5.0V and 0.0V
senseResVal = 22.0              # Sense resistor value in Ohms
outputFilePath = 'out.csv'      # Output file path
maxVoltage = 0.0                # Maximum allowable voltage in Volts
chargeCurrent = 0.0             # Charging current in mA

# Global variables set by threads
lastReadValues = [0.0, 0.0, 0.0, 0.0, 0.0]   # Set by Com thread after each read-cycle [senseVoltage, loadVoltage, pidValue, outputValue, stepValue]
jobEnd = False                               # Set to True by Com thread when job is done. Unset by main thread when a new job begins.
plotRequest = 'none'

# Com thread handles communicating and regulating functions
class Com (threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'Com'
        self.exitRequest = threading.Event()
        self.fixRequest = threading.Event()

        try:
            self.ser = serial.Serial(COM_PORT)
            self.ser.read()
        except Exception as e:
            log(self.name + ' service: Serial communication error: ' + str(e))

        log(self.name + ' service: Service initiated.')

    def run(self):
        log(self.name + ' service: Service started.')
        senseVoltList = [0.0 , 0.0, 0.0, 0.0, 0.0]
        emitVoltList = [0.0 , 0.0, 0.0, 0.0, 0.0]

        self.set_output(OUTPUT_PROBE, 0)
        outputVolt = 0

        while not self.exitRequest.is_set():
            targetSenseVolt = chargeCurrent * senseResVal / 1000
            prevOutputVolt = outputVolt

            senseVolt = self.get_input(SENSE_VOLT_PROBE)
            emitVolt = self.get_input(LOAD_VOLT_PROBE) * LOAD_VOLT_FACTOR

            senseVoltList.append(senseVolt)
            emitVoltList.append(emitVolt)
            senseVoltList = senseVoltList[1:]
            emitVoltList = emitVoltList[1:]
            loadVoltList = [emitVoltList[i] - senseVoltList[i]  for i in range(len(senseVoltList))]

            senseVoltErrList = np.array([i - targetSenseVolt for i in senseVoltList])
            loadVoltErrList = np.array([i - maxVoltage for i in loadVoltList])

            p = P
            i = I
            d = D

            step = senseVoltErrList[-1] * p + sum(senseVoltErrList) * i + (senseVoltErrList[-1]-senseVoltErrList[-2]) * d

            if not self.fixRequest.is_set(): outputVolt = prevOutputVolt - step
            if outputVolt > 5.0 : outputVolt = 5.0

            step = abs(step)

            # informing job end
            global jobEnd
            if not (all(i > 0 for i in loadVoltErrList) or all(i < 0 for i in loadVoltErrList) or any(abs(i) > MAX_VOLT_ERROR for i in loadVoltErrList)):
                jobEnd = True
                log(self.name + ' service: Job ended.')

            # voltage protection
            if (emitVolt-senseVolt)>maxVoltage:
                outputVolt = prevOutputVolt - step

            # updating lastReadValues[senseVolt, loadVoltage, pidValue, outputValue, stepValue]
            global lastReadValues
            lastReadValues = [senseVolt, emitVolt, ana_to_dig(outputVolt), outputVolt, step]

            self.set_output(OUTPUT_PROBE,outputVolt)

            time.sleep(0.01)

        self.set_output(OUTPUT_PROBE,0)
        self.ser.close()
        log(self.name + 'service: Service stopped.')

    def request_stop(self):
        log(self.name + 'service: Stop requested.')
        self.exitRequest.set()

    def get_input(self, probe):
        if probe==SENSE_VOLT_PROBE:
            self.ser.write(b'get 0c')
        else:
            self.ser.write(b'get 1c')

        char = self.ser.readline()
        value = int(char.decode('ascii').strip())
        return dig_to_ana(value)

    def set_output(self, probe, value):
        value = ana_to_dig(value)
        cmd = "set " + str(value) + "c"
        self.ser.write(cmd.encode('ascii'))

        char = self.ser.readline()
        char = int(char.decode().strip())
        if char != 0 :
            log(self.name + 'service: Setting output value failed.')



# Rec thread handles plotting and keeping records in files
class Rec (threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'Rec'
        self.exitRequest = threading.Event()
        log(self.name + ' service: Service initiated.')

    def run(self):
        log(self.name + 'service: Service started.')

        file = open(outputFilePath, 'w')
        file.write("timestamp(ms), load(Ohm), load voltage(V), load current(mA)\n")
        file.close()

        size = 1000
        x_vec = np.linspace(-1, 0, size + 1)[0:-1]
        lc_vec = np.zeros(len(x_vec))
        lv_vec = np.zeros(len(x_vec))
        lr_vec = np.zeros(len(x_vec))

        lc_plt = pylive.plot(x_vec,lc_vec,'time','current (mA)','load current')
        lv_plt = pylive.plot(x_vec,lc_vec,'time','voltage (V)','load voltage')
        lr_plt = pylive.plot(x_vec,lc_vec,'time','resistance (Ohm)','load resistance')

        oldPTime = datetime.now()
        oldWTime = oldPTime

        notificationCount = 0

        while not self.exitRequest.is_set():
            newWTime = datetime.now()
            lc = 1000 * lastReadValues[0] / senseResVal
            lv = lastReadValues[1] - lastReadValues[0] + LV_CONST;
            if lc != 0: lr = 1000 * lv / lc
            else: lr = -1
            writeDif = (newWTime - oldWTime) // timedelta(milliseconds=1000)
            if writeDif>0:
                file = open(outputFilePath, 'a')
                file.write(str(datetime.now()) + ', ' + str(lr) + ', ' + str(lv) + ', ' + str(lc) + '\n')
                file.close()

                if jobEnd:
                    if notificationCount>10:
                        print(Fore.LIGHTGREEN_EX, 'Job complete', Style.RESET_ALL)
                        notificationCount = 0
                    else:
                        notificationCount += 1
                else:
                    notificationCount = 0

                oldWTime = newWTime

            newPTime = datetime.now()
            plotDif = (newPTime - oldPTime) // timedelta(milliseconds=1)
            if plotDif>0:
                lc_vec[-1] = lc
                lv_vec[-1] = lv
                lr_vec[-1] = lr

                global plotRequest
                if lc_plt.is_existing(): lc_plt.live_plot(x_vec,lc_vec)
                elif plotRequest == 'lc':
                    lc_plt.restart(x_vec, lc_vec)
                    plotRequest = 'none'
                if lv_plt.is_existing(): lv_plt.live_plot(x_vec,lv_vec)
                elif plotRequest == 'lv':
                    lv_plt.restart(x_vec, lv_vec)
                    plotRequest = 'none'
                if lr_plt.is_existing(): lr_plt.live_plot(x_vec,lr_vec)
                elif plotRequest == 'lr':
                    lr_plt.restart(x_vec, lr_vec)
                    plotRequest = 'none'


                lc_vec = np.append(lc_vec[1:], 0.0)
                lv_vec = np.append(lv_vec[1:], 0.0)
                lr_vec = np.append(lr_vec[1:], 0.0)

                oldPTime = newPTime

        lc_plt.terminate()
        lv_plt.terminate()
        lr_plt.terminate()
        log(self.name + 'service: Service stopped.')

    def request_stop(self):
        log(self.name + 'service: Stop requested.')
        self.exitRequest.set()








# Global functions

def log(string):
    file = open('log.txt', 'a')
    file.write(str(time.time()) + ' : ' + string + '\n')
    file.close()
    return


def ana_to_dig(analogVal):
    if analogVal>5.0 :
        log('ana_to_dig error: value out of range. ' + str(analogVal))
        return 255
    elif analogVal<0.0 :
        log('ana_to_dig error: value out of range. ' + str(analogVal))
        return 0
    else:
        return np.round(analogVal*255/5.0)


def dig_to_ana(digitalVal):
    if calibrationArray[0] == calibrationArray[1]:
        log('dig_to_ana error: Calibration array elements are equal.')
        return 10000000
    else:
        return (digitalVal - calibrationArray[1]) * 5.0 / (calibrationArray[0] - calibrationArray[1])


def read_user(prompt, intype ='s'):
    print(prompt, end='')
    try:
        val = input()
        if intype == 'y':
            yes = ['y', 'Y', 'yes', 'Yes', 'YES']
            no = ['n', 'N', 'no', 'No', 'NO']
            val = val.strip()
            if val in yes:
                return True
            elif val in no:
                return False
            else:
                print(Fore.LIGHTRED_EX + "Please specify yes or no." + Style.RESET_ALL)
                return read_user(prompt, intype)
        elif intype == 'f':
            val = val.strip()
            try:
                return float(val)
            except ValueError:
                print(Fore.LIGHTRED_EX + "Please insert a number." + Style.RESET_ALL)
                return read_user(prompt, intype)
        else:
            return val
    except KeyboardInterrupt as e:
        print('Keyboard interrupt. Quitting ungracefully!!')
        os._exit(1)


def start_job():
    global outputFilePath, senseResVal, maxVoltage, chargeCurrent, COM_PORT
    file = read_user(Fore.LIGHTYELLOW_EX + "Output file name:" + Style.RESET_ALL, 's')
    if file != '':
        y = re.findall(".*\.csv$", file, re.I)
        if len(y):
            outputFilePath = file
        else:
            outputFilePath = file + '.csv'
    else: print(Fore.LIGHTGREEN_EX + 'Using default file name out.csv' + Style.RESET_ALL)

    port = ''
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        print(p)
        if "VID:PID=2341:0043" in p[0] or "VID:PID=2341:0043" in p[1] or "VID:PID=2341:0043" in p[2]:
            port = p[0]
    if port == '':
        port = read_user(Fore.LIGHTYELLOW_EX + "Port on which Arduino is connected (Eg: COM23):" + Style.RESET_ALL, 's')
        log('COM port manually selected: ' + port + '\n')
    else:
        log('COM port automatically detected: ' + port + '\n')
        print('COM port automatically detected: ' + port + '\n')
    COM_PORT = port
	
    senseResVal = 22
    print(Fore.LIGHTYELLOW_EX + "Sense resistor value (in Ohms):" + Style.RESET_ALL + ' 22');
    maxVoltage = read_user(Fore.LIGHTYELLOW_EX + "Maximum load voltage (in Volts): " + Style.RESET_ALL, 'f')
    chargeCurrent = read_user(Fore.LIGHTYELLOW_EX + "Charging current (in mili Amperes): " + Style.RESET_ALL, 'f')
    calibrate()
    com = Com()
    rec = Rec()
    if read_user(Fore.LIGHTYELLOW_EX + "Start job? (y/n): " + Style.RESET_ALL, 'y'):
        com.start()
        rec.start()

    return com,rec


def end_job(com, rec):
    com.exitRequest.set()
    rec.exitRequest.set()
    global jobEnd
    jobEnd = True
    print(Fore.LIGHTGREEN_EX + 'job ended' + Style.RESET_ALL)


def calibrate():
    a1 = 4.7
    print(Fore.LIGHTYELLOW_EX + '5V output measured as (in V):' + Style.RESET_ALL + ' 4.7')
    a2 = 0.0
    print(Fore.LIGHTYELLOW_EX + 'GND output measured as (in V):' + Style.RESET_ALL + ' 0.0')
    if a1 != a2:
        calibrationArray[0] = 1023 * (5.0 - a2) / (a1 - a2)
        calibrationArray[1] = -1023 * a2 / (a1 - a2)
        return
    else:
        print(Fore.LIGHTRED_EX + 'Invalid measurements. Please try again' + Style.RESET_ALL)
        calibrate()
        return






# main thread
# lastReadValues[senseVoltage, loadVoltage, pidValue, outputValue, stepValue]

warnings.simplefilter('ignore')
warnings.filterwarnings('ignore')
colorama.init()

while True:
    if read_user(Fore.LIGHTYELLOW_EX + "Start new job? (y/n): " + Style.RESET_ALL, 'y'):
        jobEnd = False
        file = open('log.txt', 'w')
        file.write(str(time.time()) + ': job started\n')
        file.close()
        com, rec = start_job()
        while True:
            if jobEnd:
                comm = read_user(Fore.LIGHTYELLOW_EX + "job_completed >" + Style.RESET_ALL)
            else:
                comm = read_user(Fore.LIGHTYELLOW_EX + ">" + Style.RESET_ALL)
            comm = comm.strip()
            if comm == 'watch':
                k = 0
                while not keyboard.is_pressed('q'):
                    if k > 100:
                        loadCurrent = 1000 * lastReadValues[0] / senseResVal
                        loadVoltage = lastReadValues[1] - lastReadValues[0] + LV_CONST
                        if loadCurrent != 0: load = loadVoltage / loadCurrent
                        else: load = 'Inf'
                        print('Load:' + str(load) + ' Ohm', ' Current:' + str(loadCurrent) + ' mA', ' Voltage:' + str(loadVoltage) + ' V\n',
                              'pid:' + str(lastReadValues[2]), 'output:' + str(lastReadValues[3]), 'step:' + str(lastReadValues[4]))
                        #print( 'pid:' + str(lastReadValues[2]), 'output:' + str(lastReadValues[3]), 'step:' + str(lastReadValues[4]))
                        k = 0
                    k += 1
                    time.sleep(0.005)
            elif comm == 'seti':
                chargeCurrent = read_user(Fore.LIGHTYELLOW_EX + 'Target current in mA:' + Style.RESET_ALL, 'f')
                print('Charge current set to', chargeCurrent, 'mA')
            elif comm == 'setv':
                maxVoltage = read_user(Fore.LIGHTYELLOW_EX + 'Maximum voltage in V:' + Style.RESET_ALL, 'f')
                jobEnd = False
                print('Maximum voltage set to', maxVoltage, 'V')
            elif comm == 'setr':
                # senseResVal = read_user(Fore.LIGHTYELLOW_EX + 'Sense resistor value in Ohm:' + Style.RESET_ALL, 'f')
                print('Sense resistor value set to', senseResVal, 'Ohm')
            elif comm == 'calib':
                calibrate()
                print('Calibration done')
            elif comm == 'plti':
                plotRequest = 'lc'
            elif comm == 'pltv':
                plotRequest = 'lv'
            elif comm == 'pltr':
                plotRequest = 'lr'
            elif comm == 'fixi':
                com.fixRequest.set()
            elif comm == 'reli':
                com.fixRequest.clear()
            elif comm == 'show':
                print('Output file:', outputFilePath, '\nSense resistor:', senseResVal, 'Ohm\nMaximum load voltage:',maxVoltage,
                      'V\nCharging current',chargeCurrent,'mA')
            elif comm == 'end':
                val = read_user(Fore.LIGHTRED_EX + 'Are you sure? (y/n):' + Style.RESET_ALL, 'y')
                if val:
                    end_job(com, rec)
                    break
            elif comm == 'help':
                print('Usage:\n')
                print('watch - print current values periodically')
                print('seti - set charging current')
                print('setv - set maximum voltage')
                print('setr - set sense resistor value (disabled in this version)')
                print('calib - initiate a calibration dialog (disabled in this version)')
                print('plti - view load current vs time plot')
                print('pltv - view load voltage vs time plot')
                print('pltr - view load resistance vs time plot')
                print('fixi - fix charging current without further changes')
                print('reli - release fixed state of charging current to allow variations')
                print('show - show current job parameters')
                print('end - end current job')
                print('help - display this message')
                print('\nEnjoy!!')
            elif comm != '':
                print('No such command - ' + str(comm) + '. List of commands:\nwatch, seti, setv, setr, calib, plti, pltv, pltr, fixi, reli, show, end, help')
                print('For more details try help.')
    else:
        print('Have a nice day!!')
        exit(0)