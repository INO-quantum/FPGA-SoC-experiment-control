APP = FPGA-test

# Add any other object files to this list below
APP_OBJS = FPGA-test.o
APP_OBJS += data_xy.o
#APP_OBJS += USB.o

# to include libusb see:
# https://forums.xilinx.com/t5/Embedded-Linux/PetaLinux-2019-need-to-support-on-adding-libusb/td-p/1010540
#+LIBUSB_CFLAGS = $(shell pkg-config --cflags libusb-1.0)
#+LIBUSB_LIBS = $(shell pkg-config --libs libusb-1.0)
#+CFLAGS = $(LIBUSB_CFLAGS) $(WARNINGS)
#+LDFLAGS = $(LIBUSB_LIBS)
#still does not work. most likely just use -L/libs -llibusb but does not work either.

all: build

build: $(APP)

clean:

#$(APP): $(APP_OBJS)
#	$(CXX) $(LDFLAGS) -o $@ $(APP_OBJS) $(LDLIBS) 

#$(APP): $(APP_OBJS)
#	$(CXX) $(LDFLAGS) $(LDFLAGS) -o $@ $(APP_OBJS) $(LDLIBS) $(LDFLAGS) 

$(APP): $(APP_OBJS)
	$(CXX) $(LDFLAGS) -o $@ $(APP_OBJS) $(LDLIBS)

