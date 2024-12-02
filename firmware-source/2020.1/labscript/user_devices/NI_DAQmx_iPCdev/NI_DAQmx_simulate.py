# NI_DAQmx_simulate.h
# simulate NI-commands
# created 25/4/2024 by Andi
# last change 13/5/2024 by Andi
# this is only needed when you do not have a NI installation and still want to test the software without hardware.

from ctypes import c_uint as uInt32, c_void_p, byref, cast, POINTER, c_wchar

TaskHandle = c_void_p

DAQmx_Val_GroupByChannel    = 0         # Group by Channel
DAQmx_Val_GroupByScanNumber = 1         # Group by Scan Number
DAQmx_Val_ChanPerLine       = 0         # One Channel For Each Line
DAQmx_Val_ChanForAllLines   = 1         # One Channel For All Lines
DAQmx_Val_Volts             = 10348     # Volts
DAQmx_Val_Rising            = 10280     # Rising
DAQmx_Val_Falling           = 10171     # Falling
DAQmx_Val_FiniteSamps       = 10178     # Finite Samples
DAQmx_Val_Low               = 10214     # Low
DAQmx_Val_High              = 10192     # High

class Task:
    def __init__(self, name=""):
        self.taskHandle = TaskHandle(0)
        #DAQmxCreateTask(name, byref(self.taskHandle))

    def StartTask(self):
        return 0
    
    def WaitUntilTaskDone(self, timeToWait):
        return 0
    
    def StopTask(self):
        return 0
    
    def ClearTask(self):
        return 0
    
    def RegisterDoneEvent(self, task, options, callbackFunction, callbackData):
        return 0
    
    def CreateAOVoltageChan(self, physicalChannel, nameToAssignToChannel, minVal, maxVal, units, customScaleName):
        return 0
        
    def CreateDOChan(self, lines, nameToAssignToLines, lineGrouping):
        return 0
        
    def CreateCOPulseChanTicks(self, counter, nameToAssignToChannel, sourceTerminal, idleState, initialDelay, lowTicks, highTicks):
        return 0
        
    def SetRefClkSrc(self, data):
        return 0
        
    def SetRefClkRate(self, data):
        return 0
        
    def CfgDigEdgeStartTrig(self, triggerSource, triggerEdge):
        return 0
        
    def CfgImplicitTiming(self, sampleMode, sampsPerChan):
        return 0
        
    def CfgSampClkTiming(self, source, rate, activeEdge, sampleMode, sampsPerChan):
        return 0
        
    def WriteCtrTicks(self, numSampsPerChan, autoStart, timeout, dataLayout, highTicks, lowTicks, numSampsPerChanWritten, reserved):
        numSampsPerChanWritten.value = numSampsPerChan
        return 0
        
    def WriteAnalogF64(self, numSampsPerChan, autoStart, timeout, dataLayout, writeArray, sampsPerChanWritten, reserved) :
        sampsPerChanWritten.value = numSampsPerChan
        return 0
        
    def WriteDigitalU32(self, numSampsPerChan, autoStart, timeout, dataLayout, writeArray, sampsPerChanWritten, reserved):
        sampsPerChanWritten.value = numSampsPerChan
        return 0
        
    def GetCOPulseTerm(self, channel, data, bufferSize):
        return 0;
    
    def SetAODataXferMech(self, channel, data):
        return 0
        
    def SetAODataXferReqCond(self, channel, data):
        return 0
        
    def SetDODataXferMech(self, channel, data):
        return 0
        
    def SetDODataXferReqCond(self, channel, data):
        return 0
        
    def SetCODataXferMech(self, channel, data):
        return 0
        
    def SetCODataXferReqCond(self, channel, data):
        return 0
        
    def GetWriteCurrWritePos(self, data):
        return 0
        
    def GetWriteTotalSampPerChanGenerated(self, data):
        return 0
        
    def GetExtendedErrorInfo(self, errorString, bufferSize):
        return 0

    def GetCOPulseTerm(self, channel, data, bufferSize):
        # data should be a string and is converted by PyDAQ I think?
        # data is a buffer created with ctypes.create_string_buffer
        data.value = (channel + '_sim').encode('utf-8')
        return 0

def DAQmxGetDevCOPhysicalChans(channel, buffer, bufferSize):
    if (buffer is None) or (bufferSize == 0):
        if channel == 'PXI1Slot2': return 0     # hardcoded for my system
        else:                      return 1
    return 0

def DAQmxCreateTask(name, taskHandle):
    return 0

def DAQmxResetDevice(deviceName):
    return 0

def DAQmxGetSysNIDAQMajorVersion(major):
    major = 100
    return 0

def DAQmxGetSysNIDAQMinorVersion(minor):
    minor = 0
    return 0

def DAQmxGetSysNIDAQUpdateVersion(patch):
    path = 0
    return 0
