"""
moglabs device class
Simplifies communication with moglabs devices

Compatible with both python2 and python3

v1.2: Fixed Unicode ambiguities, added explicit close(), fixed USB error in recv_raw()
v1.1: Made compatible with both python2 and python3
v1.0: Initial release

(c) MOGLabs 2016--2021
http://www.moglabs.com/
"""
import time
import socket
import serial
import select
from struct import unpack
from collections import OrderedDict
import six
CRLF = b'\r\n'

# Handles communication with devices
class MOGDevice(object):
    def __init__(self,addr,port=None,timeout=1,check=True):
        assert len(addr), 'No address specified'
        self.dev = None                        
        
        # is it a COM port?
        if addr.startswith('COM') or addr == 'USB':
            if port is not None: addr = 'COM%d'%port
            addr = addr.split(' ',1)[0]
            self.connection = addr
            self.is_usb = True
        else:
            if not ':' in addr:
                if port is None: port=7802
                addr = '%s:%d'%(addr,port)
            self.connection = addr
            self.is_usb = False
        self.reconnect(timeout,check)

    def __repr__(self):
        """Returns a simple string representation of the connection"""
        return 'MOGDevice("%s")'%self.connection
    
    def close(self):
        """Close any active connection. Can be reconnected at a later time"""
        if self.connected():
            self.dev.close()
            self.dev = None
    
    def reconnect(self,timeout=1,check=True):
        """Reestablish connection with unit"""
        # close the handle if open - this is _required_ on USB
        self.close()
        if self.is_usb:
            try:
                self.dev = serial.Serial(self.connection, baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=timeout, writeTimeout=0)
            except serial.SerialException as E:
                raise RuntimeError(E.args[0].split(':',1)[0])
        else:
            self.dev = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.dev.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.dev.settimeout(timeout)
            addr, port = self.connection.split(':')
            self.dev.connect((addr,int(port)))
        # check the connection?
        if check:
            try:
                self.info = self.ask('info')
            except Exception as E:
                raise RuntimeError('Device did not respond to query')
    
    def connected(self):
        """Returns True if a connection has been established, but does not validate the channel is still open"""
        return self.dev is not None
        
    def _check(self):
        """Assers that the device is connected"""
        assert self.connected(), 'Not connected'
                 
    def versions(self):
        """Returns a dictionary of device version information"""
        verstr = self.ask('version')
        if verstr == 'Command not defined':
            raise RuntimeError('Incompatible firmware')
        # does the version string define components?
        vers = {}
        if ':' in verstr:
            # old versions are LF-separated, new are comma-separated
            tk = ',' if ',' in verstr else '\n'
            for l in verstr.split(tk):
                if l.startswith('OK'): continue
                n,v = l.split(':',2)
                v = v.strip()
                if ' ' in v: v = v.rsplit(' ',2)[1].strip()
                vers[n.strip()] = v
        else:
            # just the micro
            vers['UC'] = verstr.strip()
        return vers

    def cmd(self,cmd):
        """Send the specified command, and check the response is OK. Returns response in Unicode"""
        resp = self.ask(cmd)
        if resp.startswith('OK'):
            return resp
        else:
            raise RuntimeError(resp)
        
    def ask(self,cmd):
        """Send followed by receive, returning response in Unicode"""
        # check if there's any response waiting on the line
        self.flush()
        self.send(cmd)
        resp = self.recv().strip()
        if resp.startswith('ERR:'):
            raise RuntimeError(resp[4:].strip())
        return resp
        
    def ask_dict(self,cmd):
        """Send a request which returns a dictionary response, with keys and values in Unicode"""
        resp = self.ask(cmd)
        # might start with "OK"
        if resp.startswith('OK'): resp = resp[3:].strip()
        # expect a colon in there
        if not ':' in resp: raise RuntimeError('Response to '+repr(cmd)+' not a dictionary')
        # response could be comma-delimited (new) or newline-delimited (old)
        splitchar = ',' if ',' in resp else '\n'
        # construct the dict (but retain the original key order)
        vals = OrderedDict()
        for entry in resp.split(splitchar):
            key, val = entry.split(':')
            vals[key.strip()] = val.strip()
        return vals
        
    def ask_bin(self,cmd):
        """Send a request which returns a binary response, returned in Bytes"""
        self.send(cmd)
        head = self.recv_raw(4)
        # is it an error message?
        if head == b'ERR:': raise RuntimeError(self.recv().strip())
        datalen = unpack('<L',head)[0]
        data = self.recv_raw(datalen)
        if len(data) != datalen: raise RuntimeError('Binary response block has incorrect length')
        return data
    
    def send(self,cmd):
        """Send command, appending newline if not present"""
        if hasattr(cmd,'encode'):  cmd = cmd.encode()
        if not cmd.endswith(CRLF): cmd += CRLF
        self.send_raw(cmd)
    
    def has_data(self,timeout=0):
        """Returns True if there is data waiting on the line, otherwise False"""
        self._check()
        if self.is_usb:
            try:
                if self.dev.inWaiting(): return True
                if timeout == 0: return False
                time.sleep(timeout)
                return self.dev.inWaiting() > 0
            except serial.SerialException: # will raise an exception if the device is not connected
                return False
        else:
            sel = select.select([self.dev],[],[],timeout)
            return len(sel[0])>0
        
    def flush(self,timeout=0,buffer=256):
        self._check()       
        dat = ''
        while self.has_data(timeout):
            chunk = self.recv(buffer)
            # handle the case where we get binary rubbish and prevent TypeError
            if isinstance(chunk,six.binary_type) and not isinstance(dat,six.binary_type): dat = dat.encode()
            dat += chunk
        return dat
    
    def recv(self,buffer=256):
        """Receive a line of data from the device, returned as Unicode"""
        self._check()
        if self.is_usb:
            data = self.dev.readline(buffer)
            if len(data):
                while self.has_data(timeout=0):
                    segment = self.dev.readline(buffer)
                    if len(segment) == 0: break
                    data += segment
            if len(data) == 0: raise RuntimeError('Timed out')
        else:
            data = b''
            while True:
                data += self.dev.recv(buffer)
                timeout = 0 if data.endswith(CRLF) else 0.1
                if not self.has_data(timeout): break
        try:
            # try to return the result as a Unicode string
            return data.decode()
        except UnicodeDecodeError:
            # even though we EXPECTED a string, we got raw data so return it as bytes
            return data
    
    def send_raw(self,cmd):
        """Send, without appending newline"""
        self._check()
        if self.is_usb:
            return self.dev.write(cmd)
        else:
            return self.dev.send(cmd)
    
    def recv_raw(self,size):
        """Receive exactly 'size' bytes"""
        self._check()
        parts = []
        tout = time.time() + self.get_timeout()
        while size > 0:
            if self.is_usb:
                chunk = self.dev.read(min(size,0x2000))
            else:
                chunk = self.dev.recv(min(size,0x2000))
            if time.time() > tout:
                raise DeviceError('timed out')
            parts.append(chunk)
            size -= len(chunk)
        buf = b''.join(parts)
        return buf
        
    def get_timeout(self):
        """Return the connection timeout, in seconds"""
        self._check()
        if self.is_usb:
            return self.dev.timeout
        else:
            return self.dev.gettimeout()
            
    def set_timeout(self,val = None):
        """Change the timeout to the specified value, in seconds"""
        self._check()
        old = self.get_timeout()
        if val is not None:
            if self.is_usb:
                self.dev.timeout = val
            else:
                self.dev.settimeout(val)
            return old

        
def load_script(filename):
    """Loads a script of commands for line-by-line execution, removing comments"""
    with open(filename,"rU") as f:  # open in universal mode
        for linenum, line in enumerate(f):
            # remove comments
            line = line.split('#',1)[0]
            # trim spaces
            line = line.strip()
            if len(line) == 0: continue
            # for debugging purposes it's helpful to know which line of the file is being executed
            yield linenum+1, line
