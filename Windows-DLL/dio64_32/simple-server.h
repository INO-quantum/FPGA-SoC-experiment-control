////////////////////////////////////////////////////////////////////////////////////////////////////
// simple-server.h
// a simple server class which allows to create easily client and server applications
// created 02/06/2018 by Andi
// compiled with Visual Studio Express 2013 and g++
// tested with Windows 7, Ubuntu 18.04 LTS and Petalinux 2017.4
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifndef SIMPLE_SERVER_HEADER
#define SIMPLE_SERVER_HEADER

#include <stdio.h>
#include <stdlib.h>

#ifdef _WIN32				// WINDOWS

// following defines are needed if windows.h is included
// this prevents winsock.h to be included in windows.h which defines the older version of Winsock (1)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

#include <windows.h>			// windows default definitions
#include <memory.h>			// memset
#include <conio.h>			// kbhit(), getch()

#define THREAD_HANDLE			HANDLE
#define INVALID_THREAD			NULL
#define ZEROMEMORY(address, size)	memset(address, 0, size)
#define THREAD_ENTRY(func, param)	DWORD WINAPI func(param)
#define RETURN_FROM_THREAD(exit_code)	return(exit_code)
#define THREAD_JOIN(handle, res, err)	err = pthread_join(handle, &res);
#define SLEEP(ms)			Sleep(ms)
#define CONIO_INIT
#define CONIO_KBHIT			kbhit
#define CONIO_GETCH			_getch
#define CONIO_RESET

#else					// LINUX

#include <sys/types.h>
#include <unistd.h>
#include <string.h>			// memset, strcmp
#include <pthread.h>			// POSIX threads
#include <errno.h>			// ETIMEDOUT
#include <time.h>			// nanosleep
// required additionally for kbhit() and getch()
#include <stdlib.h>
#include <sys/select.h>
#include <termios.h>			

#define DWORD				unsigned long
#define THREAD_HANDLE			pthread_t	// this is actually thread ID but used as a windows handle
#define INVALID_THREAD			0
#define ZEROMEMORY(address, size)	memset(address, 0, size)
#define THREAD_ENTRY(func, param)	void * func(param)
#define RETURN_FROM_THREAD(exit_code)	return((void*)((long)exit_code)) // without (long) get warning "-Wint-to-pointer-cast"
#define SLEEP(ms)			sleep_ms(ms)
#define CONIO_INIT			conio::init
#define CONIO_KBHIT			conio::kbhit
#define CONIO_GETCH			conio::getch
#define CONIO_RESET			conio::reset

#endif


// general macros and includes

#ifdef _DEBUG
#include <stdlib.h>			// NULL
#include <stdio.h> 			// printf for testing
#include <assert.h>			// assert macro
#endif

//#include <memory>			// std::shared_ptr, weak_ptr and std::make_shared
#include "list.h"			// single linked list of clients


// cross-platform socket definitions

#ifdef _WIN32				// WINDOWS

#ifndef _WINSOCK_DEPRECATED_NO_WARNINGS
#define _WINSOCK_DEPRECATED_NO_WARNINGS
#endif

#include <winsock2.h>			// windows socket definitions in WS2_32.lib
#include <ws2tcpip.h>			// winsock 2 definitions
#include <iphlpapi.h>			// ip helper function, include windock2.h before this

#define CLOSESOCKET(socket)		closesocket(socket)
#define GETSOCKNAME(socket, addr, len)	getsockname(socket, (sockaddr *)addr, (int *)len)
#define ACCEPT(socket, addr, len)	accept(socket, (SOCKADDR *)addr, (int *)len)

#else					// LINUX

#include <sys/socket.h>
#include <netinet/in.h>			// struct sockaddr_in
#include <netdb.h>			// getaddrinfo
#include <arpa/inet.h>			// inet_ntoa

#define SOCKET		int
#define INVALID_SOCKET	-1
#define SOCKET_ERROR	-1
#define CLOSESOCKET(socket)		close(socket)
#define GETSOCKNAME(socket, addr, len)	getsockname(socket, (sockaddr *)addr, (socklen_t *)len)
#define ACCEPT(socket, addr, len)	accept(socket, (sockaddr *)addr, (socklen_t *)len)

// class emulating kbhit() and getch()
// requires <stdlib.h>, <string.h>, <unistd.h>, <sys/select.h>, <termios.h>
// if used create static member in cpp file: struct termios conio::old_attributes;
class conio {
private:
	static struct termios old_attributes;
public:
	static void reset(void);	// reset console
	static void init(void);		// init console
	static int kbhit(void);		// returns nonzero if keyboard pressed
	static int getch(void);		// get keyboard key (<0 on error)
};

#endif

// error codes
// special error codes must be within SERVER_ERROR + [0,0x0ff], others start with SERVER_ERROR + 0x100
#define SERVER_ERROR			0x0C00			// simple_server error codes start with this
#define SERVER_SEND_PENDING		(SERVER_ERROR + 0x5A)	// SendData could not send all data in one package, 
								// onSendFinished() will be called when finished or error.
#define SERVER_WAIT_TIMEOUT		(SERVER_ERROR + 0x20)	// waiting timeout

#define ETHERNET_MSS			1460				// Ethernet max. segement size in bytes = max. payload/frame
#define RECV_BUFLEN			512				// length of receive buffer in bytes

#define CLIENT_FLAG_CLIENT		0				// client created with connect
#define CLIENT_FLAG_SERVER		1				// server created with listen

// single-linked list of large data to be sent by client
class send_data {
	friend single_linked_list<send_data>;		// allow single_linked list to access 'next'
private:
	send_data *next;
	void *data;
	int num;
	int sent;

public:
	send_data(void *data, int num, int sent);
	~send_data();

	void *get_data(void) { return data; };	// get data
	void *get_reset_data(void) { void *d = data; data = NULL; return d; }; // get and reset data
	int get_num(void) { return num; };		// get number of bytes to be sent
	int get_sent(void) { return sent; };	// get number of bytes already sent
	int get_remaining(void) { return (num - sent); };	// get number of remaining bytes to be sent

	int update(int sent_next) { sent += sent_next; return (num - sent); };	// adds sent_next to sent and returns remaining bytes to be sent
};


// client information stored in single-linked list
class client_info {
	friend single_linked_list<client_info>;		// allow single_linked list to access 'next'

private:
	client_info *next;							// pointer to next client or NULL
	SOCKET socket;								// client socket
	char *IP_address;							// IP address of client
	char *port_str;								// port string of client
	unsigned short port_ushort;					// port ushort of client
	unsigned int flags;							// see CLIENT_FLAG_ constant
	single_linked_list<send_data> post;			// list of data to be sent

	// copy port in string and ushort form. returns true on success.
	bool set_port(unsigned short port);
	bool set_port(const char *port);

public:
	void *client_data;				// application specific data. free in onDisconnect.

	// constructor with IP_address and port copied and destructor
	client_info(const char *IP_address, const char *port, unsigned int flags);
	client_info(const char *IP_address, unsigned short port, unsigned int flags);
	~client_info();

	// returns type of client
	bool is_client(void);
	bool is_server(void);
	bool is_local(void);				// returns true if local IP_address

	// set/get and close socket
	void set_socket(SOCKET socket);
	SOCKET get_socket(void) { return socket; };
	void close_socket(void);

	// get IP address and port
	char *get_IP_address(void) { return IP_address;	};
	char *get_port_str(void) { return port_str;	};
	unsigned short get_port_ushort(void) { return port_ushort; };

	// set and get port to which socket is bound
	unsigned short update_port(void);

	// data sending
	bool is_sending(void) { return (!post.is_empty()); };
	void add_post(send_data *next) { post.add(next); };
	send_data *get_post(void) { return post.get_first(); };
	bool remove_post(send_data *next) { return post.deleteEntry(next); };
	void empty_post(void) { post.deleteAll(); };
};

class simple_server {
private:
	DWORD timeout;						// timeout in ms onTimeout is called
	THREAD_HANDLE thread;					// thread handle
	volatile int error;					// error code of Shutdown
	volatile bool startup;					// true after startup is finished
	volatile bool running;					// true while server is running

	// private helper functions
	int AcceptClient(client_info *server);			// accept client if onConnect() returns true
	int ReceiveData(client_info *&client, char *buffer, int length); // receives data from client
	int SendNextData(client_info *client);			// send next data to client
#ifdef USE_LINK
	int ThreadCom(client_info *client, void *data, int num); // received num bytes of data from a thread
#endif

	// server loop
	int SelectLoop(void);

	// server thread start routine
	static THREAD_ENTRY(server_thread,class simple_server *info);

protected:
	// list of clients
	single_linked_list<client_info> clients;

	// client functions
	// note: typical use in onStartup to create a client (connect) or server (listen)
	int connect(const char *IP_address, const char *port);			// creates a client and connects to given IP address and port
	int listen(const char *IP_address, const char *port, int maxclients);	// creates server and listens at IP_address and port for maximum maxclients clients

	// send data
	int SendData(client_info *client, void *data, int *num);		// send num bytes of data to client

	// application specific server/client events
	// notes: 
	// - all exectued by server thread
	// - call Shutdown() or thread_Shutdown() to quit server
	virtual void onStartup(void) = 0;					// server startup
	virtual bool onConnect(client_info *c) = 0;				// client has connected to server. return true to accept client.
	virtual void onTimeout(void) = 0;					// called every timeout ms. use for timing
	virtual void onData(client_info *c, void *data, int num) = 0; 		// received num>0 bytes of data from client/server
	virtual void onSendFinished(client_info *client, void *data, int num, int sent, int error) = 0;	// sending of large data finished
	virtual void onDisconnect(client_info *c) = 0; 				// client disconnected
	virtual void onShutdown(int error) = 0;					// server shutdown with error code (0=ok)

	// shutdown of server thread with given error code.
	int shutdown(int error);

public:
	// static member
	static const char localhost[];						// name "localhost"
	static const char localhost2[];						// name "127.0.0.1"

	// constructor and destructor
	simple_server();
	~simple_server();

	// info functions
	// note: not thread safe but for most cases should not matter
	bool is_running(void) { return running; };				// returns true if server thread is running
	DWORD get_timeout(void) { return timeout; };				// returns timeout in ms

	// start or stop server thread
	// all return 0 if ok, otherwise error code
	// note: called from master thread
	int thread_start(DWORD timeout);				// starts new server thread with timeout in ms onTimeout is called
	int thread_shutdown(DWORD timeout);				// shutdown server and wait for its termination
	int thread_wait_shutdown(void);					// wait until server terminates
	int thread_wait_startup(unsigned poll_ms);			// wait until server startup

	// inter-thread communication
	// these functions can be called from other threads
	static client_info * thread_connect(const char *IP_address, const char *port); // connect to IP_address:port

	static int thread_send(client_info *client, void *data, int num, int timeout_ms);// send num bytes of data to client
	static int thread_recv(client_info *client, char *buffer, int length);		// receive data from client

	static int thread_disconnect(client_info *client);		// disconnect client

	static int thread_wait_send(SOCKET s, int timeout_ms); 		// waits until last sending of data is finished
	static int thread_wait_recv(SOCKET s, int timeout_ms); 		// waits until data is available

};


#endif // SIMPLE_SERVER_HEADER
