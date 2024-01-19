APP = fpga-server

# Add any other object files to this list below
APP_OBJS = fpga-server.o
APP_OBJS += simple-server.o

all: build

build: $(APP)

clean:
	rm -f $(APP) *.o

$(APP): $(APP_OBJS)
	$(CXX) -o $@ $(APP_OBJS) $(LDFLAGS) $(LDLIBS) -pthread

