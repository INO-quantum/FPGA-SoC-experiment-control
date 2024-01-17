////////////////////////////////////////////////////////////////////////////////////////////////////
// simple-server.cpp
// a simple server class which allows to create easily client and server applications
// created 02/06/2018 by Andi
// compiled with Visual Studio Express 2013 and g++
// tested with Windows 7, Ubuntu 18.04 LTS and Petalinux 2017.4
////////////////////////////////////////////////////////////////////////////////////////////////////

#include "simple-server.h"				// simple server header

#ifdef _WINDOWS
// link with WS2_32.lib
// note: this pragma is compiler specific and works with Visual Studio, link explicitely otherwise
#pragma comment(lib,"WS2_32.lib")
#endif

const char simple_server::localhost[]  = "localhost";
const char simple_server::localhost2[] = "127.0.0.1";

////////////////////////////////////////////////////////////////////////////////////////////////////
// helper
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifndef _WIN32

// sleeping time in ms
void sleep_ms(unsigned long ms) {
	struct timespec ts;
	ts.tv_sec = ms / 1000;
	ts.tv_nsec = (ms % 1000) * 1000000000;
	nanosleep(&ts, NULL);
}

// reset terminal
void conio::reset(void)
{
	tcsetattr(0, TCSANOW, &old_attributes);
}

// init terminal
void conio::init(void)
{
	struct termios new_attributes;

	tcgetattr(0, &old_attributes);
	new_attributes = old_attributes;
	new_attributes.c_lflag &= ~ICANON;
	new_attributes.c_lflag &= ~ECHO;
	new_attributes.c_lflag &= ~ISIG;
	new_attributes.c_cc[VMIN] = 0;
	new_attributes.c_cc[VTIME] = 0;

	// register cleanup handler, and set the new terminal mode
	//atexit(reset);
	//cfmakeraw(&new_termios);
	tcsetattr(0, TCSANOW, &new_attributes);
}

// returns nonzero if keyboard pressed
int conio::kbhit(void)
{
	struct timeval tv = { 0L, 0L };
	fd_set fds;
	FD_ZERO(&fds);
	FD_SET(0, &fds);
	return select(1, &fds, NULL, NULL, &tv);
}

// get keyboard key (<0 on error)
int conio::getch(void)
{
	int r;
	unsigned char c;
	if ((r = read(0, &c, sizeof(c))) < 0) {
	return r;
	} else {
	return c;
	}
}


#endif

// gets length of '\0'-terminated string, allocates memory and copies string
// returns allocated memory or NULL on error
char *copy_string(const char *str) {
	int num;
	for (num = 0; str[num] != '\0'; ++num);
	++num; // '\0'
	char *n = new char[num];
	if (n != NULL) {
		char *p = n;
		for (int i = 0; i < num; ++i) *p++ = str[i];
	}
	return n;
}

////////////////////////////////////////////////////////////////////////////////////////////////////
// single-linked list of large data to be sent by client
////////////////////////////////////////////////////////////////////////////////////////////////////

send_data::send_data(void *data, int num, int sent){
	next = NULL;
	this->data = data;
	this->num = num;
	this->sent = sent;
}

send_data::~send_data() {
#ifdef _DEBUG
	assert(next == NULL);			// remove from list manually!
	assert(data == NULL);			// call reset_data manually!
#endif
}

////////////////////////////////////////////////////////////////////////////////////////////////////
// class client info
////////////////////////////////////////////////////////////////////////////////////////////////////

client_info::client_info(const char *IP_address, const char *port, unsigned int flags) {
	this->next = NULL;
	this->socket = INVALID_SOCKET;
	this->IP_address = NULL;
	this->port_str = NULL;
	this->port_ushort = 0;
	this->flags = flags;
	this->IP_address = copy_string(IP_address);
	set_port(port);
	client_data = NULL;
}

client_info::client_info(const char *IP_address, unsigned short port, unsigned int flags) {
	this->next = NULL;
	this->socket = INVALID_SOCKET;
	this->IP_address = NULL;
	this->port_str = NULL;
	this->port_ushort = 0;
	this->flags = flags;
	this->IP_address = copy_string(IP_address);
	set_port(port);
	client_data = NULL;
}

client_info::~client_info() {
#ifdef _DEBUG
	assert(next == NULL);								// client must have been removed from list!
	assert(client_data == NULL);						// onDisconnect must free client_data!
	assert(post.is_empty());							// all sending of data must have been terminated manually!
#endif
	if (socket != INVALID_SOCKET) {						// close socket when open
		CLOSESOCKET(socket);
		socket = INVALID_SOCKET;
	}
	if (IP_address != NULL) {							// free IP address (allocate with 'new')
		delete[] IP_address;
		IP_address = NULL;
	}
	if (port_str != NULL) {								// free port (allocate with 'new')
		delete[] port_str;
		port_str = NULL;
		port_ushort = 0;
	}
}

// set port unsigned short converted into string or vice versa
// returns true if ok, otherwise error
// input string is copied and can be freed after function returns
bool client_info::set_port(unsigned short port) {
	static const char port_format_out[] = "%05hu"; // hu = unsigned short
	int num, i;
	// allocate memory
	if (port_str != NULL) {
		delete[] port_str;
	}
#ifdef _WIN32
	// todo: carefully check code for linux and windows! maybe make a wrapper macro?
	num = _scprintf(port_format_out, port);
	if (num > 0) {
		port_str = new char[num + 1];
		if (port_str != NULL) {
			// generate port_str, returns number of bytes without '\0'
			i = sprintf_s(port_str, num + 1, port_format_out, port);
			if (i == num) {
				// set port_ushort
				port_ushort = port;
				// success
				return true;
			}
		}
	}
#else
	// count number of bytes without '\0'
	num = snprintf(NULL, 0, port_format_out, port);
	if (num > 0) {
		port_str = new char[num + 1];
		if (port_str != NULL) {
			// generate port_str, returns number of bytes without '\0'
			//i = sprintf_s(port_str, num + 1, port_format_out, port);
			i = snprintf(port_str, num + 1, port_format_out, port);
			if (i == num) {
				// set port_ushort
				port_ushort = port;
				// success
				return true;
			}
		}
	}
#endif
	// error
	port_ushort = 0;
	return false;
}
bool client_info::set_port(const char *port) {
	static const char port_format_in[] = "%hu"; // hu = unsigned short
	if (port != NULL) {
		// copy port into port_str including '\0'
		this->port_str = copy_string(port);
		if (this->port_str != NULL) {
			// set port_ushort
			//int num = sscanf_s(port, port_format_in, &port_ushort);
			int num = sscanf(port, port_format_in, &port_ushort);
			if (num == 1) {
				// success
				return true;
			}
		}
	}
	// error
	port_ushort = 0;
	return false;
}

// set and get port to which socket is bound
// returns 0 on error
// note: this is useful for a server if port number 0 (random port) was used in listen
unsigned short client_info::update_port(void) {
	unsigned short port;
	sockaddr_in addr;
	ZEROMEMORY(&addr, sizeof(addr));
	//addr.sin_family = AF_INET;
	//addr.sin_addr.s_addr = htonl(INADDR_ANY);
	//addr.sin_port = 0;
	int num = sizeof(addr);
	if (GETSOCKNAME(socket, &addr, &num) != SOCKET_ERROR) {
		port = ntohs(addr.sin_port);
		// set port converted into string
		if (set_port(port)) {
			// success
			return port;
		}
	}
	return 0;
}

// set/get and close socket
void client_info::set_socket(SOCKET socket) { 
#ifdef _DEBUG
	assert(this->socket == INVALID_SOCKET);	// socket must be unused
#endif
	this->socket = socket; 
};

void client_info::close_socket(void) {
	if (socket != INVALID_SOCKET) {
		CLOSESOCKET(socket);
		socket = INVALID_SOCKET;
	}
}

// returns type of client
bool client_info::is_client(void) { return ((flags & CLIENT_FLAG_SERVER) == CLIENT_FLAG_CLIENT); };
bool client_info::is_server(void) { return ((flags & CLIENT_FLAG_SERVER) == CLIENT_FLAG_SERVER); };

// returns true if local IP_address
bool client_info::is_local(void) {
	// we check against localhost and localhost2 since I dont know if its always the same.
	// on Petalinux it was localhost2, so I check it first
	if(strcmp(IP_address, simple_server::localhost2) != 0) {
		if(strcmp(IP_address, simple_server::localhost) != 0) {
			return false;
		}
	}
	return true;
}

////////////////////////////////////////////////////////////////////////////////////////////////////
// constructor and destructor
////////////////////////////////////////////////////////////////////////////////////////////////////

simple_server::simple_server() {
	timeout = 0;
	thread = INVALID_THREAD;
	startup = false;
	running = true;
	error = 0;
}

simple_server::~simple_server() {
	clients.deleteAll();
	timeout = 0;
	thread = INVALID_THREAD;
	startup = false;
	running = false;
	error = 0;
}

////////////////////////////////////////////////////////////////////////////////////////////////////
// socket functions
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x100 + c)

// connects to given IP_address and port
// returns socket if ok or INVALID_SOCKET on error
// note: if IP_address = NULL connects to INADDR_ANY = "localhost"
SOCKET _connect(const char *IP_address, const char *port) {
	SOCKET c = INVALID_SOCKET;
	struct addrinfo *result = NULL, *ptr = NULL;
	struct addrinfo ai;
	// init address information structure
	ZEROMEMORY(&ai, sizeof(ai));
	ai.ai_family = AF_INET;						// use IPv4 or IPv6 adress family
	ai.ai_socktype = SOCK_STREAM;				// streaming socket
	ai.ai_protocol = IPPROTO_TCP;				// TCP protocol

	// Resolve the server address and port
	if (getaddrinfo(IP_address, port, &ai, &result) == 0)
	{
		// attempt to connect to the first address returned by the call to getaddrinfo
		ptr = result;

		// Create a SOCKET for connecting to server
		SOCKET c;
		if ((c = socket(ptr->ai_family, ptr->ai_socktype, ptr->ai_protocol)) != INVALID_SOCKET)
		{
			// connect to server
			if (::connect(c, ptr->ai_addr, (int)ptr->ai_addrlen) != SOCKET_ERROR) 
			{
				// free adress info structure returned by getaddrinfo
				freeaddrinfo(result);
				return c;
			}
			// error connecting to server
			CLOSESOCKET(c);
			c = INVALID_SOCKET;
		}
		// free adress info structure returned by getaddrinfo
		freeaddrinfo(result);
	}
	return c;
}

// listens at IP_address and port for maximum maxclients clients
// returns socket if ok, otherwise INVALID_SOCKET
// notes: 
// - specify IP_address only when several network cards are available. normally give IP_address = INADDR_ANY = NULL.
// - if port = NULL listens at next free port
SOCKET _listen(const char *IP_address, const char *port, int maxclients)
{
	if (maxclients > 0) {
		// init addressinfo structure
		struct addrinfo *result = NULL, ai;
		ZEROMEMORY(&ai, sizeof(ai));
		ai.ai_family = AF_INET;						// IPv4 adress family
		ai.ai_socktype = SOCK_STREAM;				// streaming socket
		ai.ai_protocol = IPPROTO_TCP;				// TCP protocol
		ai.ai_flags = AI_PASSIVE;					// use bind in following calls

		// resolve the local address and port to be used by the server
		if (getaddrinfo(IP_address					//0=INADDR_ANY=0.0.0.0
			, port == NULL ? "0" : port				//local port adress. "0" if next free port should be used.
			, &ai, &result) == 0) 
		{
			// create server socket to listen for client connections
			SOCKET s = socket(result->ai_family, result->ai_socktype, result->ai_protocol);
			if (s != INVALID_SOCKET)
			{
				// Setup the TCP listening socket
				if (bind(s, result->ai_addr, (int)result->ai_addrlen) != SOCKET_ERROR)
				{
					// listen on specified socket
					// note: max. number of clients = SOMAXCONN
					if (::listen(s, maxclients) != SOCKET_ERROR)
					{
						/* read SO_LINGER option
						struct linger ln;
						unsigned int len = sizeof(ln);
						int err = getsockopt(s, SOL_SOCKET, SO_LINGER, &ln, &len);
						if(err == 0) {
							printf("server: linger active = %d, seconds = %d\n", ln.l_onoff, ln.l_linger);
						} else printf("server: getsockopt failed with error %d\n", err);
						*/
						// free adress info structure returned by getaddrinfo
						freeaddrinfo(result);
						// return listening socket
						return s;
					}
				}
				// close socket
				CLOSESOCKET(s);
				s = INVALID_SOCKET;
			}
			// free adress info structure returned by getaddrinfo
			freeaddrinfo(result);
		}
	}
	// an error occurred
	return INVALID_SOCKET;
}

////////////////////////////////////////////////////////////////////////////////////////////////////
// client functions
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x110 + c)

// creates a client and connects to given IP address and port
// returns 0 if ok, otherwise error code
// note: if IP_address = NULL connects to INADDR_ANY = "localhost"
int simple_server::connect(const char *IP_address, const char *port)
{
	int err = 0;
	if (port == NULL) err = ERROR(0x0);
	else {
		// create client_info: IP_address and port are copied.
		client_info *client = new client_info(IP_address == NULL ? localhost : IP_address, port, CLIENT_FLAG_CLIENT);
		if (client == NULL) err = ERROR(0x1);
		else {
			SOCKET c = _connect(IP_address, port);
			if (c == INVALID_SOCKET) err = ERROR(0x2);
			else
			{
				// successfully connected to server: add to list of clients
				client->set_socket(c);
				clients.add(client);
				return 0;
			}
			delete client;
		}
	}
	// return error code
	return err;
}

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x120 + c)
	
// creates server and listens at IP_address and port for maximum maxclients clients
// returns 0 if ok, otherwise error code
// notes: 
// - specify IP_address only when several network cards are available. normally give IP_address = INADDR_ANY = NULL.
// - if port = NULL listens at next free port. the port of the client_info is updated with the true port number. 
//   do not give port = "0", otherwise true port is not updated.
// - if is_thread_com = true the server is a thread communication server with other threads
int simple_server::listen(const char *IP_address, const char *port, int maxclients)
{
	int err = 0;
	// create client_info of server: IP_address and port are copied if not NULL.
	client_info *server = server = new client_info(IP_address == NULL ? localhost : IP_address, port, CLIENT_FLAG_SERVER);
	if (server == NULL) err = ERROR(0x0);
	else {
		SOCKET s = _listen(IP_address, port, maxclients);
		if (s == INVALID_SOCKET) err = ERROR(0x1);
		else {
			// set server socket
			// cleanup of socket is done in delete server.
			server->set_socket(s);
			// update port if it was NULL. 
			// note: this works only after bind and requires socket to be set.
			if (port == NULL) {
				unsigned short port = server->update_port();
				if (port == 0) err = ERROR(0x2);
			}
			if (!err) {
				// add server to list of clients
				this->clients.add(server);
				return 0;
			}
		}
		// close socket and delete server
		delete server;
	}
	// return error code
	return err;
}


////////////////////////////////////////////////////////////////////////////////////////////////////
// private helper functions
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x130 + c)

// accept client if onConnect() returns true
// returns 0 if ok, otherwise error code
int simple_server::AcceptClient(client_info *server) {
	int err = 0;
	SOCKET socket;
	// in order to get client IP and port we need to accept client first
	// if onClient() returns false client connection is closed afterwards
	sockaddr_in	cla;				// client address
	int ncla = sizeof(cla);				// length of client adress
	if ((socket = ACCEPT(server->get_socket(), &cla, &ncla)) == INVALID_SOCKET) err = ERROR(0x1);
	else {
		// create client_info of new client with IP_address (copied) and port
		client_info *client = new client_info(inet_ntoa(cla.sin_addr), (int)ntohs(cla.sin_port), CLIENT_FLAG_CLIENT);
		if (client == NULL) err = ERROR(0x0);
		else {
			// set client socket
			client->set_socket(socket);
			// check if client should be accepted
			if(onConnect(client)) {
				// client accepted: add to list of clients
				clients.add(client);
				// all ok
				return 0;
			}
			// delete client if not accepted
			// this also closes socket and releases all allocated resources
			delete client;
		}
	}
	// an error occurred
	return err;
}

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x140 + c)

// receives data from client
// returns 0 if ok, otherwise error code
// note: the receive data size is limited to the package size, so larger data size is received in several packages
//       your application must properly check and handle this situation.
int simple_server::ReceiveData(client_info *&client, char *buffer, int length) {
	int err = 0, num;
	// read data from client, leave 1 byte free for '\0'
	if ((num = recv(client->get_socket(), buffer, length - 1, 0)) == 0)
	{
		printf("server: received 0 data from client! buffer = %d bytes\n", length);
		// no data = client terminated connection
		onDisconnect(client);
		// close socket and remove from list of clients
		clients.deleteEntry(client);
		client = NULL;
	}
	else if (num > 0)
	{
		printf("server: received %d bytes from client %s:%s\n", num, client->get_IP_address(), client->get_port_str());
		{
			// normal data
			// ensure there is a '\0' at end of data (even if data is not a string)
			// Andi: removed since this might corrupt data!?
			// buffer[num] = '\0';

			// data available
			onData(client, buffer, num);
		}
	}
	else
	{
		printf("server: receive failed!\n");
		// receive failed
		err = ERROR(0x3);
	}
	return err;
}

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x150 + c)

// send num bytes of data to client
// returns 0 if ok, otherwise error code
// notes:
// - returns SERVER_SEND_PENDING when data could not be send or if other data has to be sent before.
//   num will be updated to the actual number of bytes sent (can be 0).
//   server will send remaining data later using SendNextData() and data must remain valid!
//   when sending is finished onSendFinished() will be called with data, number of sent bytes and error code.
// - if returns with error or 0 onSendFinished() will not be called and data can be deleted immediately.
// - data must be deleted from caller when returns other than SERVER_SEND_PENDING,
//   when SERVER_SEND_PENDING is returned data must be deleted by onSendFinished().
int simple_server::SendData(client_info *client, void *data, int *num) {
	int err = 0;
	if (client == NULL || data == NULL || (num == 0)) err = ERROR(0x0);
	else if ((*num <= 0) || (client->is_server())) err = ERROR(0x1);
	else { 
		int num_sent;
		if (client->is_sending()) {
			num_sent = 0;
		}
		else {
			num_sent = send(client->get_socket(), (char*)data, *num, 0);
			if (num_sent == SOCKET_ERROR) err = ERROR(0x2);
		}
		if ((!err) && (num_sent != *num)) {
			// less bytes sent: 
			// create send_data and insert into list of data to be sent later
			send_data *batch = new send_data(data, *num, num_sent);
			if (batch == NULL) err = ERROR(0x3);
			else {
				client->add_post(batch);
				// return number of sent data (can be 0) and SERVER_SEND_PENDING
				*num = num_sent;
				err = SERVER_SEND_PENDING;
			}
		}
	}
	return err;
}

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x160 + c)

// send next data to client
// returns 0 if ok, otherwise error code
// note: if sending of data is finished or an error occurred calls onSendFinished
int simple_server::SendNextData(client_info *client) {
	int err = 0;
	if (client == NULL) err = ERROR(0x0);
	else {
		send_data *batch = client->get_post();
		if (batch == NULL) err = ERROR(0x1);
		else {
			int remaining = batch->get_remaining();
			int num_sent = send(client->get_socket(), (char*)batch->get_data(), remaining, 0);
			if (num_sent == SOCKET_ERROR) {
				// error sending of data
				err = ERROR(0x2);
			}
			else if (num_sent != remaining) {
				// less bytes sent: continue sending of data 
				remaining = batch->update(num_sent);
			}
			else {
				// sending of data finished
				remaining = batch->update(num_sent);
#ifdef _DEBUG
				if (remaining != 0) err = ERROR(0x3);
#endif
			}
			if ((remaining == 0) || err) {
				// send onSendFinished if finished or an error
				// onSendFinished() must delete data!
				onSendFinished(client, batch->get_reset_data(), batch->get_num(), batch->get_sent(), err);
				client->remove_post(batch);
				delete batch;
			}
		}
	}
	return err;
}


////////////////////////////////////////////////////////////////////////////////////////////////////
// server loop
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x1A0 + c)

// process client or server requests using select
// returns 0 if ok, otherwise error code
int simple_server::SelectLoop(void)
{
	int err = 0;						// error code, 0=ok
	int num = 0;						// counts sockets
	fd_set fdr, fdw;					// read/write, file descriptor set for select()
	char buf[RECV_BUFLEN];				// data buffer
	struct timeval timeout;				// timeout structure for select
	client_info *c, *next;				// client info

	// repeat until shutdown is called, i.e if running is set to false
	// if an error occures break is called
	while (running)
	{
		// note: sets and timeout must be always initialized

		// init timeout structure for select
		timeout.tv_sec = (long)(this->timeout / 1000);
		timeout.tv_usec = (long)(this->timeout % 1000) * 1000;

		// init set
		FD_ZERO(&fdr);
		FD_ZERO(&fdw);
		num = 0;

		// add all server and client sockets
		c = clients.get_first();
		while (c != NULL)
		{
			// receive data
			FD_SET(c->get_socket(), &fdr);
			if (c->is_sending()) {
				// send data
				FD_SET(c->get_socket(), &fdw);
			}
			// get largest socket
			if (num < (int)c->get_socket()) num = (int)c->get_socket();
			// next client
			c = clients.get_next(c);
		}

		// wait until new data available in file descriptor set or timeout
		// timeout ensures that on program termination the server shuts down within this time
		num = select(num + 1//largest socket+1
			, &fdr//read
			, &fdw//write
			, NULL//exception
			, &timeout//timeout
			);
		if (num == SOCKET_ERROR)
		{
			// select failed (e.g. when neither client nor server)
			err = ERROR(0x1);
			break;
		}

		// check if a server or client socket is set
		c = clients.get_first();
		while (c != NULL)
		{
			// next client
			// note: if client disconnects ReceiveData deletes c and removes from list (and c=NULL)
			//       thats why we need to get next before ReceiveData is called
			next = clients.get_next(c);
			// check if we should send data
			if (FD_ISSET(c->get_socket(), &fdw)) {
				// send next data
				err = SendNextData(c);
				if (err) break;
			}
			// check if we should receive data (also multiple are possible)
			if (FD_ISSET(c->get_socket(), &fdr)) {
				if (c->is_server()) {
					// server socket is set
					// accept client if onConnect() returns true
					err = AcceptClient(c);
				}
				else {
					// client socket is set
					err = ReceiveData(c, buf, RECV_BUFLEN);
				}
				if (err) break;
			}
			c = next;
		}
		if (err) break;
		if (num == 0) {
			// timeout
			onTimeout();
		}

	}// next select loop

	// return error code of loop or given by Shutdown(), 0=ok
	return (err != 0) ? err : error;
}

////////////////////////////////////////////////////////////////////////////////////////////////////
// server thread starting routine
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x1B0 + c)

// server thread entry
// returns 0 if ok, otherwise error code
THREAD_ENTRY(simple_server::server_thread, class simple_server *info)
{
	int err = 0;					// error code, 0=ok
	client_info *next, *client;
	if (info == NULL) err = ERROR(0x0);
	else {
		// server thread is running
		// here typically listen() or connect() are called
		// or/and init_thread_com() might be called if data should be sent from another thread
		// on error Shutdown(error) was called which we check in SelectLoop afterwards 
		info->onStartup();
		info->startup = true;  			// startup is done, SelectLoop is running

		// process client requests
		err = info->SelectLoop();

		// disconnect clients
		client = info->clients.get_first();
		while (client != NULL) {
			next = info->clients.get_next(client);
			// empty list of send_data structures
			client->empty_post();
			if (client->is_server()) {
				// close server socket before onShutdown such that connected clients can disconnect
				client->close_socket();
			}
			else {
				// close and delete the client sockets if open, this happens if an error ocurred or running = false
				info->onDisconnect(client);
				info->clients.deleteEntry(client);
			}
			client = next;
		}

		// shutdown of server: cleanup all resources
		// note: after onShutdown info might become invalid at any time!
		//       simple_server class is cleaned up by master thread after onShutdown is called.
		info->onShutdown(err);
		info = NULL;
	}
	// return error code, 0=ok
	RETURN_FROM_THREAD(err);
}


////////////////////////////////////////////////////////////////////////////////////////////////////
// start or stop server thread
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x1C0 + c)

// starts new server thread with timeout in ms onTimeout is called
// returns 0 if ok, otherwise error code
// notes: 
// - thread will start execution at server_thread and gets pointer to simple_server (i.e. inherited) class.
// - ownership of simple_server object remains on master thread (caller of StartThread), so only this is allowed to delete it.
//   however, the master thread has to call thread_Shutdown() before deleting simple_server object.
// - if returns 0 thread is started and onShutdown is guaranteed to be called before thread terminates
//   use onShutdown to cleanup any allocated resources.
// - if thread has successfully started it calls onStartup where you can do any initialization like:
//   a server would call listen() to start listening for clients.
//   a client would call connect() to connect to a server.
// - application specific data can be added in inherited class and can be accessed in any of the on.. function.
//   it can be cleaned up in onShutdown or by master thread.
// - timeout can be changed later from the on... functions if needed.
int simple_server::thread_start(DWORD timeout)
{
	int err = 0;

	if ((thread != INVALID_THREAD) || (!clients.is_empty())) err = ERROR(0x0); // server already running?
	else {
		this->timeout = timeout;
		// startup server thread
#ifdef _WIN32
		DWORD id = 0;
		thread = CreateThread(	NULL,					// security attributes
					0,					// stack size,0=default
					(LPTHREAD_START_ROUTINE)server_thread,	// thread starting address
					(LPVOID)this,				// parameters
					0,					// creation flags
					&id					// thread ID (unused)
					);
		if (thread == INVALID_THREAD) {
			// error
			err = ERROR(0x1);
		}
		else {
#else
		err = pthread_create(	&thread, 				// thread id (used as handle)
					NULL, 					// flags
					(void*(*)(void*))server_thread, 	// thread starting address
					(void *)this				// parameters
					);
		if (err != 0) { 
			// error
			thread = INVALID_THREAD; 
			err = ERROR(0x1);
		} else { 
#endif
			// succeeded
			return 0;
		}
	}
	return err;
}


#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x1D0 + c)

// shutdown of server or client thread
// returns 0 if ok, otherwise error code
// note: this should be safe to be called from another thread since server thread only reads 'running'
//       and we only set it to false but never back to true. 
//       todo: but might need a memory barrier otherwise might be lost or updated only later?
int simple_server::shutdown(int error)
{
	if (running) {
		running = false;					// this stops SelectLoop()
		this->error = error;					// save error code
	}
	return 0;
}

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x200 + c)

// shutdown server and wait for its termination
// if thread does not terminate after timeout ms thread is killed.
// if timeout == 0 returns without waiting for thread to terminate.
// returns 0 if ok, otherwise error code or exit code of thread.
int simple_server::thread_shutdown(DWORD timeout) {
	int err = 0;
	// start shutdown of thread
	err = shutdown(0);
	if (timeout != 0) {
		// regardless if error wait until thread is terminated
#ifdef _WIN32
		DWORD result = WaitForSingleObject(thread, timeout);
		if (result == WAIT_TIMEOUT) {
			// thread still running after timeout ms: kill thread.
			err = ERROR(0x0);
			TerminateThread(thread, err);
		}
		else {
			// thread terminated: get exit code
			DWORD exitCode = 0;
			GetExitCodeThread(thread, &exitCode);
			err = (int)exitCode;
		}
#else
		void *exitCode;
		struct timespec ts;
		if (clock_gettime(CLOCK_REALTIME, &ts) == -1) err = ERROR(0x1);
		else {
			ts.tv_sec += timeout/1000;
			err = pthread_timedjoin_np(thread, &exitCode, &ts);
			if(err == 0) {
				// all ok, return exit code of thread
				err = (long)exitCode;	// (long) avoids an error message
			}
			else if(err == ETIMEDOUT) {
				// timeout
				printf("thread_shutdown: timeout!\n");
			}
			else {
				printf("thread_shutdown: error %d (0x%X)\n", err, err);
				err = ERROR(0x2);
			}
		}
#endif
	}
	return err;
}

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x210 + c)

// wait until server terminates
// returns exit code of thread or error code of pthread_join
// called from master thread
// todo: Windows version
int simple_server::thread_wait_shutdown(void) {
	int err = 0;
	void *exitCode;
	err = pthread_join(thread, &exitCode);
	if(err == 0) {
		// all ok, return exit code of thread
		err = (long)exitCode;	// (long) avoids an error message
	}
	return err;
}

#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x220 + c)

// wait until server startup, polls every poll_ms ms state of server.
// returns 0 if server is running, otherwise error code of server.
// called from master thread
// note: we simply wait for server startup flag to be set (using polling).
//       if server shutdown due to error it sets startup flag after 'error' and 'running'.
// todo: is there a better way maybe using select and creating a file descriptor as 'event'?
int simple_server::thread_wait_startup(unsigned poll_ms) {
	int err = 0;
	while(running && (!startup)) {
		SLEEP(poll_ms);
	}
	if(!running) {
		err = (error != 0) ? error : ERROR(0x0); 
	}
	return err;
}

////////////////////////////////////////////////////////////////////////////////////////////////////
// inter-thread communication
// these functions can be called from other threads
////////////////////////////////////////////////////////////////////////////////////////////////////


#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x330 + c)

// connect to given IP_address:port
// if IP_address == NULL connects to local server
// returns client which can be used with thread_ functions
// returns NULL on error
client_info *simple_server::thread_connect(const char *IP_address, const char *port) {
	// create client used for the communication
	client_info *client = new client_info(IP_address == NULL ? localhost : IP_address, port, CLIENT_FLAG_CLIENT);
	if (client != NULL) {
		// connect client to remote server
		SOCKET s = _connect(IP_address == NULL ? localhost : IP_address, port);
		if (s != INVALID_SOCKET) {
			// save client socket
			client->set_socket(s);
			// connection established
			return client;
		}
		delete(client);
	}
	return NULL;
}


#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x340 + c)

// send num bytes of data to client
// returns 0 if ok, otherwise error code, SERVER_WAIT_TIMEOUT on timeout.
// notes:
// - use client returned by thread_connect
// - specify timeout_ms > 0 to stop sending data after timeout_ms in ms.
// - thread is blocked until all data is sent or timeout, data can be deleted after returns.
// - overall time might be longer than timeout_ms.
int simple_server::thread_send(client_info *client, void *data, int num, int timeout_ms) {
	int err = 0;
	if ((client == NULL) || (data == NULL) || (num <= 0))  err = ERROR(0x0);
	else {
		int num_sent = 0;
		SOCKET s = client->get_socket();
		char *p = reinterpret_cast<char*>(data);
		for(int remaining = num; (remaining > 0) && (err == 0); remaining -= num_sent, p += num_sent) {
			num_sent = send(s, p, remaining, 0);
			//printf("thread_send: sent %d/%d bytes to client %s:%s\n", num_sent, num, client->get_IP_address(), client->get_port_str());
			if (num_sent == SOCKET_ERROR) err = ERROR(0x1);
			else if(num_sent != remaining) {
				// wait until sending data is possible again (maximum timeout_ms)
				err = thread_wait_send(s, timeout_ms);
			}
		}
	}
	return err;
}


#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x350 + c)

// receives data from client
// returns number of bytes received, otherwise error
// notes: 
// - this blocks until data is available. if you want to wait with timeout call wait_recv before
// - the receive data size is limited to the package size, so larger data size is received in several packages
//   your application must properly check and handle this situation.
int simple_server::thread_recv(client_info *client, char *buffer, int length) {
	int num;
	// read data from client, leave 1 byte free for '\0'
	if ((num = recv(client->get_socket(), buffer, length - 1, 0)) == 0)
	{
		// no data = client terminated connection
		//printf("thread_recv: received 0 data from client! (disconnected?)\n");
	}
	else if (num > 0)
	{
		//printf("thread_recv: received %d bytes from client %s:%s\n", num, client->get_IP_address(), client->get_port_str());
		// normal data
		// ensure there is a '\0' at end of data (even if data is not a string)
		buffer[num] = '\0';
	}
	else
	{
		// receive failed
		//printf("thread_recv: receive failed!\n");
	}
	return num;
}


#ifdef ERROR 
#undef ERROR 
#endif 
#define ERROR(c)	(SERVER_ERROR + 0x350 + c)

// disconnect client
// returns 0 if ok, otherwise error code
int simple_server::thread_disconnect(client_info *client) {
	int err = 0;
	if (client == NULL)  err = ERROR(0x0);
	else {
		// closes socket which will automatically disconnect client
		client->close_socket();
		// success
		return 0;
	}
	return err;
}

#ifdef ERROR
#undef ERROR
#endif
#define ERROR(c)	(SERVER_ERROR + 0x370 + c)

// waits until last sending of data is finished on given socket
// give timeout_ms > 0 if waiting should be terminated after timeout_ms in ms.
// returns 0 on success, otherwise error code. SERVER_WAIT_TIMEOUT on timeout.
// on success new data can be sent with thread_send
int simple_server::thread_wait_send(SOCKET s, int timeout_ms) {
	int num, err = 0;
	fd_set fdw;					// write file descriptor
	struct timeval *timeout = NULL;			// timeout structure for select

	// init timeout structure for select
	if(timeout_ms > 0) {
		timeout = new struct timeval;
		timeout->tv_sec = (long)(timeout_ms / 1000);
		timeout->tv_usec = (long)(timeout_ms % 1000) * 1000;
	}

	// init set
	FD_ZERO(&fdw);
	FD_SET(s,&fdw);

	// wait until socket is ready to send new data or timeout
	num = select(s + 1,		// largest socket + 1
		NULL,			// read
		&fdw,			// write
		NULL,			// exception
		timeout			// timeout or NULL
		);

	// check result
	if (num == SOCKET_ERROR) err = ERROR(0x1);
	else if (num == 0) err = SERVER_WAIT_TIMEOUT;
	else if (num == 1) {
		if (!FD_ISSET(s, &fdw)) err = ERROR(0x2);
	}
	else err = ERROR(0x3);

	if(timeout) delete timeout;
	
	return err;
}

#ifdef ERROR
#undef ERROR
#endif
#define ERROR(c)	(SERVER_ERROR + 0x380 + c)

// waits until data is available on given socket
// give timeout_ms > 0 if waiting should be terminated after timeout_ms in ms.
// returns 0 on success, otherwise error code. SERVER_WAIT_TIMEOUT on timeout.
// on success data can be received with thread_ReceiveData
int simple_server::thread_wait_recv(SOCKET s, int timeout_ms) {
	int num, err = 0;
	fd_set fdr;					// read file descriptor
	struct timeval *timeout = NULL;			// timeout structure for select

	// init timeout structure for select
	if(timeout_ms > 0) {
		timeout = new struct timeval;
		timeout->tv_sec = (long)(timeout_ms / 1000);
		timeout->tv_usec = (long)(timeout_ms % 1000) * 1000;
	}

	// init set
	FD_ZERO(&fdr);
	FD_SET(s,&fdr);

	// wait until data is available on socket or timeout
	num = select(s + 1,		// largest socket + 1
		&fdr,			// read
		NULL,			// write
		NULL,			// exception
		timeout			// timeout or NULL
		);

	// check result
	if (num == SOCKET_ERROR) err = ERROR(0x1);
	else if (num == 0) err = SERVER_WAIT_TIMEOUT;
	else if (num == 1) {
		if (!FD_ISSET(s, &fdr)) err = ERROR(0x2);
	}
	else err = ERROR(0x3);

	if(timeout) delete timeout;
	
	return err;
}


