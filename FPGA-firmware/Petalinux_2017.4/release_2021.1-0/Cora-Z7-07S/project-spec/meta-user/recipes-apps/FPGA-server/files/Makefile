APP = FPGA-server

# Add any other object files to this list below
APP_OBJS = FPGA-server.o
APP_OBJS += simple-server.o

all: build

build: $(APP)

clean:

$(APP): $(APP_OBJS)
	$(CXX) $(LDFLAGS) -o $@ $(APP_OBJS) $(LDLIBS) -pthread
